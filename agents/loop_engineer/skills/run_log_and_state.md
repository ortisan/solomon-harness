---
name: run-log-and-state
description: Governs the loop_runs ledger, the merged decisions-and-handoffs activity feed in solomon_harness/loop_log.py, and the throughput and failure-rate aggregates that make an unattended loop auditable and resumable. Use when auditing what a headless loop did, adding a new ledger writer, or reconciling the failed-versus-failure status vocabulary.
---

# Run-Log and Loop State

A loop's own decisions must trace to a file on disk; this skill governs the run-log ledger and the activity feed that make an unattended loop auditable and resumable. A fresh-context tick should read where the last ticks stopped from durable state, not re-derive it.

## The ledger (`loop_runs`)

Each locked stage driven headless records one entry via `DatabaseClient.save_loop_run(stage, target, decision, status, session_id)` into the `loop_runs` table (SurrealDB primary — `DEFINE TABLE IF NOT EXISTS loop_runs SCHEMALESS`, client-minted id with an idempotent `UPSERT` and `created_at = time::now()` — with a SQLite fallback table). The exact write point is `_record_loop_run` in `solomon_harness/workflows.py`: it runs after the engine returns and only when the lock was acquired (`LOCKED_STAGES`, or an L3 `requires_lock` stage), writing `stage`, `target` (the joined stage args), `decision` (`ran /solomon-<stage>`), `status` (`ok` when the exit code is 0, else `failed`, or `skipped` when a zero-exit `start` changed nothing — ADR-0039), and `session_id` from the lock holder. It is best-effort — a logging failure never blocks a stage. Interactive `/solomon-*` sessions do not pass through `run_stage`, so they leave no automatic `loop_runs` row; their trail is the decisions and handoffs they log. `list_loop_runs(limit)` returns entries newest-first (`created_at DESC` on SurrealDB, rowid order on SQLite). The project memory is the single source of truth; any on-disk file is a convenience cache, never a competing record.

## The feed (`solomon_harness/loop_log.py`)

`gather_feed(db, last)` merges `loop_runs`, decisions (`list_decisions`), and handoffs (`list_handoffs`) into one chronological view; each source is fetched behind a guard that degrades to an empty list on error, so one broken source never hides the others. `format_feed` renders concise, emoji-free lines of the shape `<timestamp>  [<kind>]  <text>`, newest first. `solomon-harness log --last N` (default 20) is the read-only "what changed and why" surface that turns an opaque loop into an auditable one, reusing the durable store with no dual-write. The SessionStart digest (`solomon-harness run`) also surfaces the single most recent loop run beside the resume point, with a short timeout so a slow store cannot stall session start.

## Aggregates over the ledger

The MCP server exposes two SurrealDB-only aggregates: `loop_run_throughput(bucket, since)` (run counts per `time::group` bucket) and `loop_run_failure_rate(since)` (returns `total`, `failures`, `failure_rate`). One vocabulary trap to check before trusting the rate: `loop_run_failure_rate` counts rows whose `status = 'failure'`, while `run_stage` writes `failed` — reconcile the status vocabulary (or the query) before reading the number as the cadence's health, and keep any new writer consistent with whichever side wins.

## Filesystem-as-memory, alongside the contracts

Loop state lives in three durable places, read at the start of a tick and never carried in conversation history: handoff contracts in `.agents/solomon/state/handoffs/issue-<N>-<from>-to-<to>.md` (releases use `release-vX.Y.Z-to-done.md` in the same directory), the `loop_runs` ledger, and git history. Scan loops add one-line notes under `.agents/solomon/state/scan-runs/`, which is how "two consecutive runs found nothing" becomes a checkable stop condition without adding harness state to the project's tracked files. Do not introduce a freeform `TODO.md` as a second source of truth; it drifts from structured memory.

## Concurrency signal

The "another driver is running" warning derives from the lockfile (`loop_lock`), not from a `loop_runs` count, because under the SQLite fallback each worktree has a separate database and a cross-worktree count is invisible. The ledger answers "what happened"; only the lock answers "who is running now".

## Common pitfalls

- Writing a parallel on-disk run-log that can disagree with the memory rows under concurrent writes — keep memory authoritative.
- Deriving concurrency from row counts instead of the lockfile.
- Letting `save_loop_run` failures bubble up and abort a stage — the ledger is best-effort.
- Storing loop decisions only as opaque rows with no readable feed — `solomon-harness log` is what makes them reviewable.
- Expecting interactive sessions to appear in `loop_runs` — only the headless locked path writes there; audit interactive work through decisions and handoffs.
- Reading `loop_run_failure_rate` without checking the `failed` versus `failure` status vocabulary against what the writers record.

## Definition of done

- [ ] Every headless locked stage appends a `loop_runs` entry (stage, target, decision, status, session_id), best-effort, after the engine returns.
- [ ] `solomon-harness log --last N` renders loop runs, decisions, and handoffs newest-first, read-only, with per-source error isolation.
- [ ] Tick state is read from contracts + ledger + git, not conversation history; no competing `TODO.md`.
- [ ] The concurrency signal comes from the lockfile.
- [ ] Aggregates (`loop_run_throughput`, `loop_run_failure_rate`) use a status vocabulary consistent with the writers.
- [ ] Changes ship with covering tests in `tests/test_loop_run.py`.
