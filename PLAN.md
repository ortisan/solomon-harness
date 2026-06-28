# PLAN — memory resilience: reconnect/fallback (#37) + write-through mirror (#35)

Delivers #37 (lead) and #35 in one branch. Both edit
`solomon_harness/tools/database_client.py`. #37 lands first; #35 layers on it.

## Problem statement

- #37: the memory client holds one long-lived SurrealDB connection. When it drops
  mid-session it never reconnects and never falls back to SQLite (fallback exists only at
  construction, `__init__` ~146-248). Writes then raise forever; `get_latest_activity`
  (~1283-1330) swallows the error and returns `None`, masking it so `/solomon-loop`
  resumes wrong. Proven by the v0.3.0 incident (container recreated at 22:14).
- #35: even with reconnect, a true outage loses writes. Make every write durable by
  mirroring it to a human-readable `.md` on every call and reconciling on recovery.

## Proposed change and the boundary it touches

Every public method in `DatabaseClient` already has a `surrealdb` branch and a `sqlite`
branch. The fix keeps that structure and adds resilience around it.

#37:
- Store the surreal connection params on `self` (url, username, password, namespace,
  database) and extract the connect sequence into `_connect_surreal()` so it can be re-run.
- `_run_surreal(query, params=None)`: wraps `self.db.query`; on a transport/connection
  error (websocket closed / "no close frame" / `ConnectionError` / OSError-family) raise
  `_ConnectionLost`; on any other error re-raise unchanged (a query/data error must NOT
  trigger reconnect or fallback).
- `@_resilient` decorator on each public read/write: on `_ConnectionLost`, attempt exactly
  one bounded reconnect; if it succeeds re-run the method; if it fails (or the retry still
  loses the connection) call `_activate_sqlite_fallback()` (set `backend="sqlite"`, ensure
  the SQLite db is initialized, emit a loud warning + the divergence note) and re-run the
  method, which now takes its own sqlite branch.
- In each surreal branch, replace `self.db.query(...)` with `self._run_surreal(...)` and add
  `except _ConnectionLost: raise` ahead of the existing `except Exception` so the decorator
  sees it. In `get_latest_activity` (and any read that swallows), let `_ConnectionLost`
  propagate instead of returning `None`; a true empty store still returns `None`.

#35 (after #37):
- A mirror module: `_mirror_write(kind, record_id, fields)` writes
  `.solomon/memory-mirror/<kind>/<record_id>.md` (frontmatter `id, kind, created_at,
  synced`) and is called by every write method around the DB attempt; stamp `synced: true`
  on DB success, `synced: false` when the DB write could not be applied (fallback/outage).
  A mirror-write failure is loud (never swallowed).
- Client-minted stable id `<kind>-<utc>-<shortuuid>` used as the filename AND the SurrealDB
  RecordID; convert INSERT-based writes (e.g. `log_decision`) to `_rid` + UPSERT so replay
  is a deterministic UPSERT (idempotent). `save_memory`/`log_issue`/`save_session` already
  UPSERT.
- `reconcile()`: scan `synced: false` mirror files, replay each to the DB idempotently,
  flip to `synced: true`; tolerate a mid-run drop (partial reconcile); report counts.
- Wire reconcile into `memory-up` / SessionStart and a new `solomon-harness memory sync`;
  surface the pending count in `healthcheck` / `memory status`.

Boundary: the resilience + mirror live entirely inside `DatabaseClient`; `MemoryService`
and the MCP server inherit them unchanged.

## Target files

- `solomon_harness/tools/database_client.py` (resilience + mirror + reconcile)
- `tests/test_database_client.py` (extend) + a new mirror/reconnect test module
- `solomon_harness/cli.py` (`memory sync` subcommand), `solomon_harness/memory.py` (invoke
  reconcile on memory-up), `solomon_harness/healthcheck.py` (pending-count check)
- `docs/adr/0002-memory-resilience-model.md` (new)

## Edge cases as observable outcomes

- Connection drops, server reachable -> exactly one reconnect, write succeeds, no raise.
- Connection drops, server unreachable -> one reconnect attempt, then SQLite fallback;
  write persisted; no raise; bounded (no hang).
- `get_latest_activity` on a broken connection -> reconnect/fallback returns real activity
  or raises a distinct connection error; NEVER silent `None`. True empty -> `None`.
- A genuine query/data error -> no reconnect, no fallback, surfaced as before.
- Every write -> a mirror `.md` exists; `synced: true` when DB applied, else `false`.
- `reconcile()` replays pending once (idempotent UPSERT; no duplicates); partial reconcile
  leaves the rest pending; `memory status` reports the pending count.

## TDD breakdown (one commit each, Red -> Green)

#37:
1. Fake-connection test: a write after a simulated drop reconnects once and returns a
   non-null id without raising. Implement `_run_surreal` + `_connect_surreal` + `_resilient`.
2. Fake-connection test: write with an unreachable server falls back to SQLite (no raise,
   bounded). Implement `_activate_sqlite_fallback` + decorator fallback path.
3. Read test: `get_latest_activity` does not return `None` on a broken connection (real data
   or distinct error); a true empty still returns `None`. Fix the read branches.
4. Negative-space test: a query/data error does not trigger reconnect/fallback.

#35:
5. Mirror test: every write produces `.solomon/memory-mirror/<kind>/<id>.md` with the right
   frontmatter; `synced: true` on success, `false` on outage; mirror-write failure is loud.
   Implement `_mirror_write` + client-minted ids + UPSERT conversion.
6. Reconcile test: replays `synced: false` once (idempotent), partial-reconcile leaves the
   rest pending, reports counts. Implement `reconcile()`.
7. Wiring test: `solomon-harness memory sync` runs reconcile; `healthcheck` reports the
   pending count. Implement CLI + healthcheck.

## STRIDE notes

- The reconnect trigger must be scoped to transport/connection exceptions, never query/data
  errors (avoid masking a real bug and avoid retry amplification).
- Reconnect is a single bounded attempt with a connect timeout + overall deadline, so a
  half-open socket can never reproduce the original indefinite hang.
- A SQLite fallback emits a loud warning + metric so the SurrealDB/SQLite divergence is
  visible; #35's mirror + reconcile is the durable reconciliation of that divergence.
- Mirror files are local gitignored state under `.solomon/`; no secrets added.

## Verification criteria

- `python -m unittest discover -s tests` green (incl. the new fake-drop and mirror tests),
  hermetic (no real Docker; simulate the drop with a fake/monkeypatched connection).
- `ruff check solomon_harness tests` clean.
- Manual: with the backend stopped mid-run, a write does not raise, a mirror `.md` appears
  with `synced: false`, and `solomon-harness memory sync` after restart replays it once.
