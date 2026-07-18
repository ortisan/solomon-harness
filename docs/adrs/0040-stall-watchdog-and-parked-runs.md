# ADR-0040: Stall watchdog and parked runs for the headless engine

- Status: accepted
- Date: 2026-07-17
- Deciders: loop_engineer, software_architect
- Issue: #353 (epic #341 packages 2 and 4)

## Context and problem statement

A headless `/solomon-*` run that wedges holds the single-driver lock indefinitely: `LoopLock.is_stale` treats a live same-host process as never stale, so a frozen engine (a decision card with no human, an MCP deadlock, a network stall) blocks every future run until the process is killed by hand. Project memory records this exact incident. There was no wall-clock bound on the engine subprocess for the default `claude` engine.

## Decision drivers

- The lock must always be released; a hung child cannot be allowed to hold it forever.
- A transient stall should not lose the run's state; a persistent stall needs human triage, not a silent failure and re-pick.
- The human review gate and the claim-safety invariants must be untouched.

## Considered options

- A machine-global daemon owning run lifecycles (compozy's model) — rejected: the harness is deliberately daemonless (the host tool is the loop).
- A single flat wall-clock timeout — insufficient: a slow-but-alive run and a fast wedge need different bounds.
- Nested time budgets plus a bounded park (chosen).

## Decision outcome

A `StallMonitor` (`solomon_harness/loop_watchdog.py`) wraps the engine subprocess with three nested budgets — idle 3m, child backstop 6m, terminal cap 45m (overridable in the `.agent/config.json` loop block via `stall_idle_seconds`/`stall_backstop_seconds`/`stall_terminal_seconds`) — and kills the process (terminate then kill) when idle or terminal is exceeded. The streaming (cost-capture) path feeds `mark_activity` from its output loop so idle detection sees progress; the plain path bounds via `subprocess.run(timeout=terminal_cap)`. The kill signals the whole process group (`start_new_session=True` + `os.killpg`), so a descendant that inherited the output pipe cannot keep it open and wedge the reader — without that, killing only the direct child leaves the blocking read without EOF and the run never reaches its `finally`. On a stall of a `start` run, the engine is retried once from a fresh attempt; a second stall records the run as `parked` (a new `loop_runs` status, added to the closed vocabulary alongside `skipped` under ADR-0039's OVERWRITE migration), keeps the claim and worktree for human triage, and sends no success notification. The kill fires on the watchdog's own thread while the main thread blocks on the read/wait inside the `try`; once the group dies the read returns and normal control flow reaches the `finally`, which releases the lock.

### Consequences

- Positive: the hung-run-holds-the-lock incident is closed; a persistent stall is preserved for triage instead of silently failing and being re-picked.
- Negative: the plain path has no idle detection (terminal cap only); a parked claim relies on the claim TTL as its backstop against a permanent hold.
- Follow-ups: worktree-reset-before-retry (compozy's exact clean-retry) is deferred; the terminal cap is the primary safety net today.

## More information

Adapted from the compozy benchmark (nested stall watchdogs, park-don't-fail). Shipped with epic #341 packages 2 and 4. Enforced by `tests/test_loop_watchdog.py` and `tests/test_workflows.py::TestRunStageStallParking`.
