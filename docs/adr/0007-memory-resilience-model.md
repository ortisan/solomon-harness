# ADR-0007: Memory resilience model — reconnect-then-fallback and a write-through mirror

- Status: accepted
- Date: 2026-06-28
- Deciders: software_architect, software_engineer, sre, product_owner
- Issue: #37, #35

## Context and problem statement

The project memory (`solomon_harness/tools/database_client.py`) is SurrealDB-primary with a
SQLite fallback, but the fallback is chosen only once, at construction. `MemoryService` holds
one `DatabaseClient` for the life of the MCP server, so the SurrealDB connection is
long-lived. When that connection drops mid-session — as during the v0.3.0 release, when the
shared SurrealDB container was recreated at 22:14 — the client neither reconnects nor falls
back: every write raises indefinitely and `get_latest_activity` silently returns `None`,
masking the failure so `/solomon-loop` can resume from the wrong point. Durable, auditable
memory is the harness's core promise, and it broke silently. We need the memory layer to
survive a mid-session backend drop and to never silently lose a lifecycle record.

## Decision drivers

- Durability: a memory write must not be lost because the backend is momentarily unavailable.
- No silent wrong results: a broken read must never be indistinguishable from an empty store.
- Bounded behavior: recovery must never reintroduce the indefinite hang that started this.
- Reviewability and simplicity: keep the existing per-method surreal/sqlite structure;
  no new runtime dependency.

## Considered options

- Reconnect handling: do nothing (status quo) vs reconnect-once vs unbounded retry.
- Mid-session fallback: none vs fall back to the method's existing SQLite branch.
- Durability buffer: none vs on-failure-only outbox vs **write-through markdown mirror**.
- Idempotent replay: blind INSERT (duplicates on replay) vs client-minted id + UPSERT.

## Decision outcome

Two layers, delivered as #37 (connection resilience, lands first) then #35 (durable mirror).

1. Connection resilience (#37): route every SurrealDB query through `_run_surreal`, which
   raises a typed `_ConnectionLost` only on transport/connection faults (never on a
   query/data error). A `_resilient` decorator on each public method, on `_ConnectionLost`,
   attempts exactly one bounded reconnect (connect timeout + overall deadline); if that
   fails it activates the SQLite fallback (loud warning) and re-dispatches to the method's
   own SQLite branch. Reads stop masking: a broken connection reconnects/falls back or
   raises a distinct connection error — a true empty store still returns `None`.

2. Write-through mirror (#35): every write also writes a human-readable Markdown mirror to
   `.solomon/memory-mirror/<kind>/<id>.md` (frontmatter `id, kind, created_at, synced`),
   stamped `synced: true` on DB success and `synced: false` on outage; the write never
   raises solely because the DB is down. `reconcile()` replays `synced: false` records to
   the DB idempotently. It runs automatically at memory-up / SessionStart (best-effort and
   bounded: it reuses the bounded connect and never blocks or fails the hook) and on demand
   via `solomon-harness memory sync`. Recovery happens at that boundary, not mid-process: a
   client that has already fallen back to SQLite mid-session keeps serving from SQLite for
   the rest of that process and does not re-probe SurrealDB; its pending records are
   replayed at the next memory-up / SessionStart or a manual sync. The pending count is
   surfaced in `healthcheck`. Records carry a client-minted stable id used as the SurrealDB
   RecordID, so replay is a deterministic UPSERT (no duplicates); INSERT-based writes are
   converted to UPSERT.

Chosen because reconnect-once-then-fallback satisfies durability and bounded behavior with
the least change (the SQLite branch already exists per method), and the write-through mirror
(over an on-failure outbox) gives a durable, auditable, human-readable record on every write
and a clean reconciliation of any SurrealDB/SQLite divergence the fallback creates.

### Consequences

- Positive: a mid-session backend drop no longer loses writes or masks reads; recovery of
  the durable mirror is automatic at the next memory-up / SessionStart (or a manual
  `memory sync`) and bounded; the audit trail is durable and human-readable.
- Negative: a mirror write on every call (kept < ~5 ms/record); a SQLite fallback can
  diverge from SurrealDB until reconcile runs (made visible by a loud warning + the pending
  count, and healed by reconcile).
- Follow-ups: the shared single-instance backend means any session bouncing it disrupts
  others — coordinate with the hermetic-test-backend work (#24/#29); retention/pruning of
  `synced: true` mirror files is a guard, not a full policy.

## More information

Implemented in `solomon_harness/tools/database_client.py` (resilience + mirror + reconcile),
wired through `cli.py` (`memory sync`), `memory.py` (memory-up), and `healthcheck.py`.
Recorded in the project memory via `save_decision` when the backend is available.
