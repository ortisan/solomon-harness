# PLAN — Issue #42: loop-engineering safety floor (single-driver lock, portable gate, run-log, session digest)

Branch: `feature/loop-safety-floor` (based on `main`; no `develop` branch exists). Phase 0 of the loop-engineering roadmap in `docs/loop-engineering.md`. This PLAN documents work already implemented on the branch and now delivered to review.

## Problem statement

Loop engineering turns the harness into a system that advances work on a cadence. Run on a cadence, two drivers on one repository corrupt shared state: a documented incident saw two `/solomon-loop` drivers produce premature merges that bypassed the human review gate, flip `core.bare=true`, and leave a stray `core.worktree` in the shared config (the residual git-config mode is tracked separately in #38). A safe cadence requires that exactly one driver mutate a repository at a time and that merge/release stays human-gated. See #42 acceptance criteria.

## Proposed change and the boundary it touches

Add a single-driver safety floor enforced in the portable `run_stage` seam (so it binds both Claude Code and the Gemini CLI), backed by an advisory lock anchored at the git common directory, an autonomy policy that keeps merge/release permanently human-gated, and an auditable run-log. The boundary touched is the harness run seam (`workflows.py`), the memory client (a new `loop_runs` ledger), and two new single-concern modules (`loop_lock.py`, `loop_log.py`), plus a session digest. No change to the agent definitions or the GitHub layer; the host tool remains the model loop (constraint C1 — the reverted self-hosted LLM loop must not return).

## Target files (diff fence)

New:
- `solomon_harness/loop_lock.py` — advisory single-driver lock (JSON lockfile at the git common dir, TTL/heartbeat staleness, dead-pid reclaim).
- `solomon_harness/loop_log.py` — render the chronological run/decision/handoff feed.
- `solomon_harness/digest.py` — session-start board digest + enumerated resume card.
- `tests/test_loop_lock.py`, `tests/test_loop_run.py`, `tests/test_digest.py`.

Edited:
- `solomon_harness/workflows.py` — portable gate in `run_stage`: acquire/release the lock for `LOCKED_STAGES` (loop/start/review/release), autonomy policy (L1 report-only, L2 allows start, L3 still blocks release), kill-switch.
- `solomon_harness/tools/database_client.py` — `loop_runs` ledger (`save_loop_run`/`list_loop_runs`).
- `solomon_harness/cli.py` — `solomon-harness log`, `loop-lock status|release`.
- `.claude/settings.json` — PreToolUse `loop-guard` hook (defense-in-depth, fails open).
- `docs/loop-engineering.md`, `docs/solomon-workflow.md`, `.claude/commands/solomon-loop.md`, `.gemini/commands/solomon-loop.toml`, `README.md`.

## Edge cases (observable outcomes)

- A second driver on any linked worktree is refused while a live driver holds the lock (one lockfile at the common dir).
- A stale lock (heartbeat past the 1800s TTL, or a dead pid on the same host) is reclaimed automatically by the next driver.
- The concurrency guard is the lockfile, never a run-log row count — under the per-worktree SQLite fallback a cross-worktree count is invisible.
- `release` is refused even at the highest autonomy level; the kill-switch blocks every mutating stage until cleared.
- The session digest degrades cleanly when the DB is unreachable or empty (never blocks session start).

## TDD breakdown (red/green, one commit each — as delivered)

1. `loop_lock`: lock path anchors at the git common dir across linked worktrees; non-git dir falls back to `.solomon`. (`test_loop_lock`)
2. `loop_lock`: held lock blocks a second acquirer; stale-by-TTL and dead-pid locks are reclaimed.
3. `loop_runs` ledger: save and list newest-first with a cap. (`test_loop_run`)
4. run-log feed: merge runs/decisions/handoffs newest-first and render each kind. (`test_loop_run`)
5. `run_stage`: mutating stage acquires/releases the lock; a foreign lock blocks it; non-mutating stage ignores it. (`test_workflows`)
6. autonomy policy: L1 blocks mutation, L2 allows start, L3 still blocks release, kill-switch blocks everything. (`test_workflows`)
7. session digest: full/empty/broken-DB/capped-issue-list. (`test_digest`)

## STRIDE notes

This change is a concurrency-control and authorization surface. Tampering/Elevation: the lock bounds *who* may drive; merge/release remain human-gated so automation cannot self-approve. Denial of service: a crashed driver must not wedge the repo — hence TTL/dead-pid reclaim and `loop-lock release`. Auditability: the lockfile holder and the `loop_runs` ledger are plain/readable so a human can see who drove and when.

## Verification criteria

- `uv run python -m unittest tests.test_loop_lock tests.test_loop_run tests.test_digest tests.test_workflows` is green (38 tests pass).
- `solomon-harness loop-lock status` reports the holder/staleness; `solomon-harness log` renders the feed.
- ADR-0001 records the single-driver concurrency decision and is linked in the PR.
- Merge/release still require explicit human approval.
