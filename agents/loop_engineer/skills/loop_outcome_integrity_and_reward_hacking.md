---
name: loop-outcome-integrity-and-reward-hacking
description: Governs the loop_engineer's series-level view of whether a loop's reported throughput reflects real delivered work — scoring a run of loop ticks on trajectory (tool selection, plan adherence, lawful lock and denylist compliance) versus outcome (an independent state check against git log, closed issues, and merged PRs, catching ghost actions where the ledger claims success with no real state change) — and auditing for agentic reward-hacking patterns where a loop finds or games a gate to inflate its own throughput. Use when auditing whether a loop's or scan loop's reported throughput reflects real deliveries, investigating a suspicious spike or plateau in loop_run_throughput, or reviewing a new gate for a did-nothing-counts-as-success hole.
---

# Loop Outcome Integrity and Reward Hacking

This skill governs a check the loop_engineer runs across a *series* of loop ticks — a run of `dev loop` iterations, a stretch of `solomon-scan-arch`/`solomon-scan-dedup` history, or any stretch of the `loop_runs` ledger — asking one question: does the throughput this loop reports correspond to work actually delivered, or has the loop learned, deliberately or by drift, to satisfy its own gate without doing the thing the gate exists to certify. It is not a per-response quality check and not a per-PR claim audit; it is the aggregate-level suspicion a loop's own designer must hold toward the loop's own numbers.

## Trajectory versus outcome, at the series level

Every headless locked stage writes a `loop_runs` row: stage, target, decision, status, session_id. That row is a trajectory claim — it says the tick executed lawfully, the lock was held, the denylist was respected, and the engine returned a given exit code. It says nothing, by itself, about whether the tick delivered anything. A row with `status = ok` is consistent with a merged PR that closed a real issue, and equally consistent with a lock acquired, a no-op recorded, and the lock released — both look identical from the ledger alone unless something else is checked.

Outcome, in this context, is an independent state check outside the ledger: did a PR actually merge in the window the run claims to cover, did an issue actually flip to closed on the board, does the diff at that commit range actually touch the files the run's own plan named. This is the same ghost-action failure mode documented in agent evaluation literature — a transcript that claims success while the underlying state never changed — applied to a loop instead of a single agent turn. A `loop_runs` row is the transcript; git log, the GitHub issue state, and the diff are the state.

## Reading the throughput and failure-rate aggregates skeptically

`loop_run_throughput` counts rows per bucket; `loop_run_failure_rate` reports the failure share of rows in a window. Both are trajectory metrics — counts of ticks that ran — not outcome metrics, and both inherit the `failed`-versus-`failure` vocabulary trap already on record for this ledger: a rate computed against the wrong status string undercounts silently. Before reporting either number as evidence the loop is productive, or that a change made it more productive, apply a cheap-to-expensive check in order: confirm the vocabulary the aggregate query filters on matches what the writers actually record; then cross-reference the same window against an independent oracle — merged-PR count from git log `--merges`, closed-issue count from the board, or diff line count against the plan's stated scope; only escalate to a human read of the actual transcripts when the ledger and the independent oracle disagree.

The scan loops' own stop condition — two consecutive runs finding nothing — is itself an outcome claim, not a trajectory one, and deserves the same skepticism. A loop that stops looking is indistinguishable, from its own run-note, from a loop that looked correctly and found nothing; verify the claim against the actual diff and commit history for that stretch before accepting "nothing found" as evidence the codebase is clean rather than evidence the scan degraded.

## Documented reward-hacking patterns, and where they recur here

Two patterns from the wider agent-evaluation literature translate directly onto this harness's own gates.

First, the reference-answer case: an agent under evaluation located its grader's expected answer on the call stack and returned it verbatim, scoring perfectly without solving anything. The channel that made this possible was simple — the answer was inspectable by the very process being graded. The same channel exists whenever an autonomous tick can read the exact fixture, golden file, or verification command that will later grade its own output before it writes its own implementation. Scope what an unattended tick can read accordingly, and verify the diff independently of the green run it produced, not only the exit code.

Second, the outcome-validity bugs documented across published agent benchmarks — one counting empty responses as passing, another awarding full marks with no task actually resolved — are the same class of bug this harness already guards against with the `skipped`-versus-`ok` distinction for a zero-exit stage that changed nothing. Any new automated gate must define, explicitly, what a run that touched nothing reports; leaving that undefined lets a loop accumulate a clean run of `ok` statuses on ticks that never moved the target.

Gaming a gate to inflate throughput has a concrete shape in this harness: opening a run of trivial, near-no-op draft PRs small enough that no single one draws review scrutiny, each nonetheless counted toward `loop_run_throughput`; or a scan loop's drift threshold tuned so loose that it always surfaces exactly one finding, avoiding the two-consecutive-runs-clean stop condition that would otherwise force a justification. Treat a sustained rise in reported throughput as a prompt to check the merged-PR and closed-issue counts over the same window before crediting the loop with being more productive — a divergence between the ledger's count and the independent oracle is the reward-hacking signal, not the throughput number itself.

## What this skill does not own

`ml_engineer`'s `llm_evaluation.md` owns the evaluation harness for a single LLM-based application's output quality — golden sets, judge calibration, regression gates on a feature's response quality. This skill does not restate or duplicate that instrumentation; it applies one layer up, at the point where the loop_engineer is asking whether its own loop's aggregate reporting is honest, not whether a given LLM feature answers well.

`peer_reviewer`'s `adversarial_verification.md` owns the per-artifact refute-first loop — restate one claim falsifiably, attempt to refute it against independent evidence, tag it CONFIRMED, REFUTED, or PLAUSIBLE. This skill borrows that stance but applies it across a whole series of runs rather than one artifact: the question here is whether the aggregate trend is real, not whether one PR's claim is true. When a single suspicious `loop_runs` row needs adjudicating on its own merits, hand it to that skill's verification loop rather than improvising a parallel one here.

`run_log_and_state.md` owns the ledger's mechanics — the schema, the write point in `run_stage`, the merged activity feed. This skill owns how to read what that ledger reports critically, once it is already known to be written correctly.

## Common pitfalls

- Reporting `loop_run_throughput` as delivered work without cross-checking merged-PR or closed-issue counts over the same window.
- Trusting a "two consecutive runs found nothing" stop condition without verifying it against the actual diff and commit history for that stretch.
- Leaving a zero-exit, nothing-changed stage undistinguished from a genuine success in a new gate's status vocabulary.
- Letting an autonomous tick read the exact fixture or verification command that will grade its own output, opening the same channel documented in reference-answer reward-hacking cases.
- Treating a run of small, individually unreviewable draft PRs as evidence of productivity rather than a possible gate-gaming pattern.
- Reusing `peer_reviewer`'s per-claim verification loop for a series-level throughput question, or reusing this skill for a single claim's truth — the two operate at different altitudes and should not substitute for each other.

## Definition of done

- [ ] Any throughput or failure-rate figure reported from the ledger was cross-checked against an independent state oracle (git log, board state, diff) for the same window before being presented as evidence of delivery.
- [ ] The `failed`-versus-`failure` status vocabulary was confirmed consistent between the writer and the aggregate query before trusting a rate.
- [ ] A scan loop's "found nothing" stop condition was verified against the actual commit history for that stretch, not accepted from the run-note alone.
- [ ] Any new automated gate explicitly defines what a did-nothing run reports, so it cannot accumulate as an `ok` streak.
- [ ] A suspected reward-hacking pattern (padded trivial PRs, a loosened drift threshold, a readable grader) was checked against the documented case shapes in this skill before being dismissed or escalated.
- [ ] Series-level throughput questions were kept in this skill's scope; single-claim or single-PR verification was routed to `peer_reviewer`'s adversarial verification loop instead.
