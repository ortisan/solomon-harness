---
name: context-reset-discipline
description: Governs the Ralph-loop tick contract of disposable context, reading the handoff contract and run-log from disk, bounding each tick to one task, and externalizing state via `dev loop` before the tick ends. Use when reviewing a headless loop tick, or a tick that carried state across iterations.
---

# Context-Reset Discipline

Treat every loop tick as disposable: start from the handoff contract and the run-log on disk, do exactly one bounded task, externalize all state before the tick ends, and halt at the human review gate. This is the Ralph-loop discipline (Geoffrey Huntley) adapted to the harness — statelessness is the intended contract, not a degradation to tolerate.

## The tick contract

- **Fresh context every tick.** Each `/solomon-workflow` invocation starts clean and reads its bounded input from disk: the latest handoff contract (`get_latest_activity` -> `contract_path`) and the tail of the run-log (`solomon-harness log`). It never relies on conversation history carried across ticks.
- **One bounded task, then commit.** A tick advances exactly one stage and produces an independently reviewable unit. A tick that tries to do two things is wrong; bound the blast radius.
- **A checkable exit condition.** Each stage's success is objectively checkable (tests named, board column reached, PR state). For a merge or release tick the exit condition is literally "human approved" — self-gating may never substitute for `/solomon-review`.
- **Externalize before ending.** Before the tick ends, write the handoff contract, the `loop_runs` entry, and the git commit, so the next clean-context tick resumes from state, not memory.

## How the harness implements the reset

The headless tick runner is `solomon-harness dev loop --concurrency N` (`run_stage` in `solomon_harness/workflows.py`; `loop-auto` survives only as a deprecated input alias). It is a bounded for-loop, not a scheduler: `_parse_concurrency` strips the flag (default 1; values below 1 or non-integers are rejected) so it never leaks into `$ARGUMENTS`; the stage is remapped to `prompt_stage = "workflow"`, so `build_prompt` reads `.claude/commands/solomon-workflow.md`, drops the YAML frontmatter, and substitutes the remaining args with the loop-driven autonomous-mode directive — the `loop` stage has no command file of its own, so every iteration sees the exact `/solomon-workflow` instructions. Each iteration then launches a FRESH engine subprocess (`claude -p`, `gemini -p ... --skip-trust`, or `agy`; chosen by `SOLOMON_ENGINE`, default `claude`) with the prompt on stdin. The reset is therefore by construction: no conversation state can survive an iteration boundary, because each iteration is a new process reading the same instructions and resuming from durable state. A failed iteration (nonzero exit) stops the run rather than plowing ahead — the same one-confirmed-step behavior `/solomon-loop` has interactively. The whole run executes under the single-driver lock and the autonomy policy; despite its name, `--concurrency N` runs N iterations sequentially under one lock.

## What a tick reads and writes

Read at tick start, from durable state only: the SessionStart digest (`solomon-harness run`: the resume point, open issues, the last loop run, PRs awaiting review), the latest handoff contract at `.solomon/handoffs/issue-<n>-<from>-to-<to>.md` (releases use `.solomon/handoffs/release-vX.Y.Z-to-done.md`), and `solomon-harness log --last 20`. Write before tick end: the next handoff contract file plus its `log_handoff` memory row, the git commit on a `feature/<slug>` branch, and — on the headless path — the `loop_runs` entry `run_stage` appends automatically for locked stages. Skip any of these writes and the next tick starts blind: it re-derives, or worse re-does, the work.

## Why the reset is a feature

A long session degrades as the window fills with dead ends and stale file contents. Throwing the session away each tick and resuming from the filesystem + git keeps each tick sharp and makes resumption the normal path, not a recovery path. The raw infinite `while` loop, though, is forbidden here: cadence comes from a host primitive, one tick per interval, each under the single-driver lock — never a self-hosted runner. `dev loop` deliberately stays a finite, human-sized batch (N iterations, stop on first failure) so the ledger and the review gate keep pace with the loop.

## Common pitfalls

- Carrying reasoning across ticks instead of re-reading the contract and run-log from disk.
- Doing multiple tasks in one tick, producing an unreviewable diff.
- Self-declaring "done" and crossing the merge boundary unattended.
- Driving the cadence with a Python `while True` instead of a host scheduler under the lock.
- Reading `--concurrency N` as parallel drivers — the iterations are sequential under one lock; true parallel drivers would re-open the concurrent-driver race the lock exists to close.
- Continuing iterations after a failed one — `run_stage` breaks on the first nonzero exit on purpose; a loop that plows ahead compounds a bad state.

## Definition of done

- [ ] A tick reads its bounded input from the handoff contract and run-log, not conversation history.
- [ ] A tick advances exactly one stage and commits an independently reviewable unit.
- [ ] The exit condition is checkable; merge/release ticks require explicit human approval.
- [ ] All state is externalized (contract, ledger, git) before the tick ends.
- [ ] Cadence is a host primitive, one tick per interval, under the single-driver lock; headless batches go through `dev loop`, fresh subprocess per iteration, stop on first failure.
