# Run-Log and Loop State

A loop's own decisions must trace to a file on disk; this skill governs the run-log ledger and the activity feed that make an unattended loop auditable and resumable. A fresh-context tick should read where the last ticks stopped from durable state, not re-derive it.

## The ledger (`loop_runs`)

Each driven mutating stage records one entry via `DatabaseClient.save_loop_run(stage, target, decision, status, session_id)` into the `loop_runs` table (SurrealDB primary, SQLite fallback). `run_stage` writes it best-effort after the engine returns, so a logging failure never blocks a stage. `list_loop_runs(limit)` returns them newest-first. The project memory is the single source of truth; any on-disk file is a convenience cache, never a competing record.

## The feed (`solomon_harness/loop_log.py`)

`gather_feed(db, last)` merges `loop_runs`, decisions, and handoffs into one chronological view; `format_feed` renders concise, emoji-free lines. `solomon-harness log [--last N]` is the read-only "what changed and why" surface that turns an opaque loop into an auditable one, reusing the durable store with no dual-write.

## Filesystem-as-memory, alongside the contracts

Loop state lives in three durable places, read at the start of a tick and never carried in conversation history: the handoff contracts in `.solomon/handoffs/issue-<N>-<from>-to-<to>.md`, the `loop_runs` ledger, and git history. Scan loops add a one-line note to `.solomon/scan-runs/<loop>-<date>.md`. Do not introduce a freeform `TODO.md` as a second source of truth — it drifts from the structured memory.

## Concurrency signal

The "another driver is running" warning derives from the lockfile (`loop_lock`), not from a `loop_runs` count, because under the SQLite fallback each worktree has a separate database and a cross-worktree count is invisible.

## Common pitfalls

- Writing a parallel on-disk run-log that can disagree with the memory rows under concurrent writes — keep memory authoritative.
- Deriving concurrency from row counts instead of the lockfile.
- Letting `save_loop_run` failures bubble up and abort a stage — the ledger is best-effort.
- Storing loop decisions only as opaque rows with no readable feed — `solomon-harness log` is what makes them reviewable.

## Definition of done

- [ ] Every driven mutating stage appends a `loop_runs` entry, best-effort.
- [ ] `solomon-harness log` renders loop runs, decisions, and handoffs newest-first, read-only.
- [ ] Tick state is read from contracts + ledger + git, not conversation history; no competing `TODO.md`.
- [ ] The concurrency signal comes from the lockfile.
- [ ] Changes ship with covering tests in `tests/test_loop_run.py`.
