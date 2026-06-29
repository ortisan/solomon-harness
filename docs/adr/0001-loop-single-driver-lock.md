# ADR-0001: Single-driver lock for the loop-engineering safety floor

- Status: accepted
- Date: 2026-06-28
- Deciders: software_architect
- Issue: #42

## Context and problem statement

The `/solomon-loop` workflow and the Phase 3 maintenance loops drive mutating
stages (loop, start, review, release, scan-arch, scan-dedup) that branch, push,
merge, and cut releases. Two drivers running
against one repository at the same time is a real, observed failure mode: a
documented concurrent-driver incident produced premature merges that bypassed the
review gate and flipped `core.bare=true` through worktree tooling, corrupting git
config. Phase 0 of the loop-engineering roadmap (`docs/loop-engineering.md`)
requires that nothing schedules itself until a single driver and an auditable
record are guaranteed.

Two hard constraints bound the solution. C1: the host tool is the model loop; a
self-hosted Python LLM loop was built and reverted and must not return, so this
floor adds coordination, not a runner. C5: the harness runs on both Claude Code
and the Gemini CLI, and Claude Code PreToolUse hooks do not exist on Gemini, so
any hard gate must also live in portable Python. A further fact constrains the
design: under the SQLite memory fallback each linked worktree gets its own
database, so any cross-worktree count is invisible.

## Decision drivers

- C2 — the review gate is sacred: concurrent drivers must be serialized so human
  approval before merge or release is never bypassed.
- C5 — dual host: enforcement of record must work identically on Claude Code and
  the Gemini CLI, not only where a host-specific hook fires.
- Auditability: the current driver and the loop's own decisions must be
  inspectable from a plain file on disk and from project memory.
- Liveness: a crashed or abandoned driver must not wedge the loop forever; a
  stale lock must be reclaimable automatically.
- Correctness under the SQLite fallback: the concurrency guard must not depend on
  a row count that the per-worktree database makes invisible.

## Considered options

- A single-driver advisory lockfile anchored at the git common directory, plus a
  portable gate in `run_stage`, a Claude-only defense-in-depth hook, and a
  `loop_runs` ledger in project memory.
- No lock: rely on human discipline and the advisory "Step 0" prose in the
  workflow markdown.
- An OS advisory lock (`flock`) on a local file.
- A database-row or heartbeat count in project memory used as the concurrency
  guard.
- A host-tool-only PreToolUse hook in Claude Code as the single enforcement
  point.

## Decision outcome

Chosen option: the single-driver advisory lockfile with a portable gate, a
defense-in-depth hook, and a separate audit ledger, because it is the only option
that satisfies C2 and C5 together while remaining live and auditable.

- The lock is a plain JSON file anchored at the git common directory
  (`<common>/solomon-loop.lock`, resolved by reading `.git` directly rather than
  shelling out to `git`), so every linked worktree of the repository contends on
  the same file. When the directory is not a git repository it falls back to
  `<root>/.solomon/loop.lock`. The JSON holder is itself the audit record. A
  live process on the same host is never stale, however long it holds the lock
  (a long stage is never reclaimed mid-run); only a dead same-host pid, or a
  cross-host lock past the TTL (1800s default, since a remote pid cannot be
  probed), is reclaimed. (`solomon_harness/loop_lock.py`.)
- The enforcement of record is the portable gate in `run_stage`
  (`solomon_harness/workflows.py`): for every stage in `LOCKED_STAGES`
  (`loop`, `start`, `review`, `release`, `scan-arch`, `scan-dedup`) — and, at L3,
  every stage `LoopPolicy.requires_lock` names — it acquires the lock before
  invoking the host engine and releases it in a `finally`. This is the enforcement
  of record for the headless cadence path (`solomon-harness dev`); because it is
  Python it holds identically on Claude Code and the Gemini CLI (C5). Interactive
  `/solomon-*` sessions do not acquire the lock — they are bounded by the human
  merge gate and the `loop-guard` hook, and operators run one at a time.
- A PreToolUse `loop-guard` hook in `.claude/settings.json` blocks `git push` /
  `gh pr merge` / `git merge` while another live driver holds the lock. This is
  Claude-only defense-in-depth that fails open; it is not the enforcement of
  record.
- The `loop_runs` ledger in `database_client.py` (`save_loop_run` /
  `list_loop_runs`, surfaced by `solomon-harness log` over
  `solomon_harness/loop_log.py`) is the single source of truth for the run-log.
  The concurrency guard is the lockfile, never a row count from this ledger,
  because the per-worktree SQLite fallback would make a cross-worktree count
  invisible.
- Recovery is manual when needed via `solomon-harness loop-lock status` and
  `solomon-harness loop-lock release`.

Rejected alternatives:

- No lock / human discipline: rejected. This is the status quo that produced the
  documented incident — premature merges bypassing the review gate and corrupted
  git config. Advisory prose is not an enforcement mechanism.
- OS advisory `flock` only: rejected. It gives no auditable holder (who is
  driving, since when) and no portable staleness/reclaim story, and the semantics
  are host- and filesystem-specific. The JSON holder and explicit TTL reclaim are
  the value being bought.
- A DB-row or heartbeat count as the guard: rejected. Under the SQLite fallback
  each worktree has its own database, so a cross-worktree count cannot see a
  second driver. The guard must be a shared on-disk artifact; the ledger is for
  audit, not concurrency.
- A host-tool-only Claude Code hook: rejected as the enforcement of record. It
  would not protect the Gemini CLI (C5), so it is kept only as defense-in-depth
  behind the portable `run_stage` gate.

### Consequences

- Positive: loop cadence becomes safe-by-construction for who drives — a second
  driver against the same repository is refused before it can touch git or the
  board, converting the documented race into impossible-by-construction in code
  rather than advisory prose. The holder and every driven stage are auditable
  from disk and from project memory. A crashed driver self-heals via TTL reclaim.
  The lock is the precondition every later loop-engineering phase depends on.
- Negative: a new advisory contract that all mutating entrypoints must route
  through `run_stage` to be protected; a direct shell invocation outside the
  harness is still only caught by the fail-open Claude-only hook. The TTL is a
  tuning trade-off: too short risks reclaiming a slow but live driver, too long
  delays recovery from a true crash. Two coordination artifacts (lockfile and
  ledger) now exist with deliberately distinct roles that must not be conflated.
- Scope: the lock bounds who drives, not whether a human approves. Human approval
  before merge or release is unchanged by this decision and remains mandatory.
- Follow-ups: a residual git-config corruption mode (the `core.bare` flip from
  worktree tooling) is not addressed by the lock; #38 will add a health check for
  it. Worktree hygiene and state GC remain Phase 4 work.

## More information

- Implementation: branch `feature/loop-safety-floor`; `solomon_harness/loop_lock.py`,
  the `run_stage` gate in `solomon_harness/workflows.py`, the `loop_runs` ledger
  in `solomon_harness/tools/database_client.py`, `solomon_harness/loop_log.py`,
  and the `loop-guard` PreToolUse hook in `.claude/settings.json`.
- Roadmap and hard constraints (C1, C2, C5): `docs/loop-engineering.md`,
  "Phase 0, as shipped".
- Tracking issue: #42. Follow-up health check for the git-config corruption mode:
  #38.
- This decision is also recorded in the project memory via `save_decision`.
