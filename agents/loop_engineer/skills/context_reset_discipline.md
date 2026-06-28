# Context-Reset Discipline

Treat every loop tick as disposable: start from the handoff contract and the run-log on disk, do exactly one bounded task, externalize all state before the tick ends, and halt at the human review gate. This is the Ralph-loop discipline (Geoffrey Huntley) adapted to the harness — statelessness is the intended contract, not a degradation to tolerate.

## The tick contract

- **Fresh context every tick.** Each `/solomon-loop` invocation starts clean and reads its bounded input from disk: the latest handoff contract (`get_latest_activity` -> `contract_path`) and the tail of the run-log (`solomon-harness log`). It never relies on conversation history carried across ticks.
- **One bounded task, then commit.** A tick advances exactly one stage and produces an independently reviewable unit. A tick that tries to do two things is wrong; bound the blast radius.
- **A checkable exit condition.** Each stage's success is objectively checkable (tests named, board column reached, PR state). For a merge or release tick the exit condition is literally "human approved" — self-gating may never substitute for `/solomon-review`.
- **Externalize before ending.** Before the tick ends, write the handoff contract, the `loop_runs` entry, and the git commit, so the next clean-context tick resumes from state, not memory.

## Why the reset is a feature

A long session degrades as the window fills with dead ends and stale file contents. Throwing the session away each tick and resuming from the filesystem + git keeps each tick sharp and makes resumption the normal path, not a recovery path. The raw infinite `while` loop, though, is forbidden here: cadence comes from a host primitive, one tick per interval, each under the single-driver lock — never a self-hosted runner.

## Common pitfalls

- Carrying reasoning across ticks instead of re-reading the contract and run-log from disk.
- Doing multiple tasks in one tick, producing an unreviewable diff.
- Self-declaring "done" and crossing the merge boundary unattended.
- Driving the cadence with a Python `while True` instead of a host scheduler under the lock.

## Definition of done

- [ ] A tick reads its bounded input from the handoff contract and run-log, not conversation history.
- [ ] A tick advances exactly one stage and commits an independently reviewable unit.
- [ ] The exit condition is checkable; merge/release ticks require explicit human approval.
- [ ] All state is externalized (contract, ledger, git) before the tick ends.
- [ ] Cadence is a host primitive, one tick per interval, under the single-driver lock.
