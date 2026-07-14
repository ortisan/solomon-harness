---
name: auditing-delivered-work
description: Governs the read-only audit of one merged pull request or diff against current best practice, classifying each observation as gap found, no gap found, or insufficient evidence and recording it with save_decision. Use when a single delivered PR or diff needs to be benchmarked against the state of the art without editing any code.
---

# Auditing a Delivered Work Item

The audit takes one merged pull request or diff and measures the delivered artifact against the current state of the art, producing a structured, evidence-backed finding set without changing any code. This skill governs the read-only audit pass that is the core of slice 1 of the practice_curator epic: it identifies which competency domains a delivery touches, compares the chosen approach to documented best practice, and classifies every observation into a defined output state. The audit is read-only: it never modifies any other agent's files, never edits the codebase, and never opens a change on its own. Its product is a report and a set of recorded decisions, not a patch.

## Inputs and how to bound the audit

Start from a concrete, merged unit of work: a PR number, a merge commit SHA, or an explicit diff range (`git diff <base>...<head>`). Pull the diff, the PR description, the linked issue, and the test changes together; an audit that reads only the production diff and skips the test diff misses the most informative signal about quality. Bound the scope to the files actually changed plus their direct call sites. Do not expand into the whole repository — that is the fleet sweep, which is out of scope for this slice.

Classify the delivery by competency domain before judging it. A single PR can touch software engineering, software architecture, ML/DRL engineering, and quantitative trading at once. Use `benchmarking_across_domains` to pick the right yardstick for each domain the diff touches; auditing an ML training loop against web-API conventions produces noise. Record the domain tags on the audit record so a later reviewer can see why a given standard was applied.

## The comparison loop

For each domain the diff touches, state the approach the delivery actually took (quote the lines), then state the current best-practice approach and where it is documented. The best-practice statement must be backed by evidence gathered through `sourcing_the_state_of_the_art` — at least two dated, credible sources per claimed practice. Never assert "the current standard is X" from memory; the value of the audit is that every gap is checkable against the record.

A worked example. A merged PR adds a DRL agent with a hand-rolled training loop and no fixed seed. The audit records: approach = "custom REINFORCE loop, `env.reset()` with no seed, single train/test split"; benchmark = "Stable-Baselines3 2.x ships vetted PPO and SAC with deterministic seeding, and out-of-sample evaluation expects walk-forward or purged k-fold with leakage controls"; evidence = the two dated sources `sourcing_the_state_of_the_art` produced; severity = high (reproducibility and leakage risk). That becomes one finding tied to one candidate target agent.

## Severity and the three output states

Grade each finding by impact, not by taste: high (correctness, security, reproducibility, or leakage risk), medium (maintainability or a measurable performance gap), low (style or minor drift). Then assign every observation to exactly one of three output states:

- Gap found: the delivery diverges from a best practice that is supported by sufficient evidence. The finding names a single target agent whose skill should change, but it stops there — proposing or editing that skill is a later slice.
- No gap found: the delivery already matches or exceeds current best practice. This is a first-class result and must be reported explicitly. An audit that returns only problems is not trustworthy, so emit a "no gap found" state with the evidence that confirmed the practice is current.
- Insufficient evidence: the auditor suspects a gap but `sourcing_the_state_of_the_art` could not produce at least two dated, credible sources, or the sources conflict. Park the observation in the insufficient evidence bucket rather than promoting it to a finding. Unsupported findings never graduate to a proposal.

This three-way split is the integrity boundary of the audit: a suspicion with no evidence is not a gap, and a confirmed match is not silence.

## Recording the result

Persist the audit as a decision in project memory with `save_decision`: the PR identifier, the domain tags, each finding with its severity, its output state, the sources cited, and the single candidate target agent per gap. Recording it lets the later slices (proposal, review, merge) resume exactly where the audit stopped, and lets a human read the reasoning without re-running the work. Keep the record direct and follow the shared humanizer rules in agents/AGENTS.md.

## Common pitfalls

- Editing a file during the audit. The pass is strictly read-only; any write to code or to another agent's skill conflates auditing with changing and breaks the never-blind boundary.
- Asserting a best practice from memory instead of through `sourcing_the_state_of_the_art`, so the claimed gap cannot be checked and may already be stale.
- Reporting only problems and omitting the "no gap found" state, which hides that most of the delivery was sound and erodes trust in the report.
- Promoting an insufficient-evidence suspicion to a finding, which manufactures work and risks pushing a wrong change downstream.
- Auditing a diff against the wrong domain's yardstick because the domain tags were never assigned.
- Naming more than one target agent for a single gap, which pre-breaks the one-target-per-proposal rule the next slice depends on.
- Skipping the test diff, missing the clearest evidence of whether the change is actually verified.

## Definition of done

- [ ] The audit input is a single merged PR, merge SHA, or explicit diff range, with the test diff included.
- [ ] Each changed area is tagged with the competency domains it touches.
- [ ] Every best-practice claim is backed by evidence from `sourcing_the_state_of_the_art` and benchmarked via `benchmarking_across_domains`.
- [ ] Every observation carries a severity and exactly one output state: gap found, no gap found, or insufficient evidence.
- [ ] A "no gap found" result is reported explicitly when the delivery already matches current best practice.
- [ ] Unsupported observations are held in the insufficient evidence bucket and never promoted to findings.
- [ ] Each gap names exactly one candidate target agent, and no other agent's files are modified during the audit.
- [ ] The audit is recorded with `save_decision`, including PR id, domains, findings, severities, states, and sources.
