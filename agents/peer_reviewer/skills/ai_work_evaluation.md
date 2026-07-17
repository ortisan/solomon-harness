---
name: ai-work-evaluation
description: Governs detection of AI-specific failure modes in delivered work — hallucinated APIs and paths, unverified success claims, test theater, fabricated citations, scope drift, over-engineering, and slop prose. Use when evaluating whether an AI agent's output is genuinely correct and complete rather than fluent, or when a report, plan, or diff reads convincingly but its substance has not been independently established.
---

# AI Work Evaluation

This skill governs the failure modes specific to AI-produced work. Human review instincts are calibrated for human errors — oversights, fatigue, gaps in knowledge that the author knows are gaps. AI output fails differently: it is fluent, confident, internally consistent, and wrong in ways that read as right. The evaluator's stance: fluency is not evidence. Every dimension below is checked mechanically, because the surface signal (does it read well?) is precisely the signal AI failure defeats.

## Hallucinated references

Check that every API, function, file path, CLI flag, configuration key, and issue number the work references actually exists at the revision under review. `git grep` the symbol, open the file, run `--help` on the flag. AI-produced work cites plausible-but-nonexistent identifiers at a meaningful rate, and one hallucinated import that slips into a merge breaks trunk. The same check applies to external citations in docs and reports: a cited source must exist, be reachable, and actually say what it is cited for — fabricated or misattributed citations are a hard REQUEST CHANGES, not a docs minor.

## Unverified success claims

"All tests pass", "CI is green", "verified manually", "the docs were updated" — each is accepted only with its evidence: the test output at the reviewed sha, the CI run link, the reproduction transcript, the doc diff. An AI agent under instruction pressure will report the state it was asked to reach rather than the state it reached; the difference is only visible in the evidence. When the work includes numbers (counts, rates, benchmark results), re-derive at least one independently — a fabricated metric is indistinguishable from a real one on the page.

## Test theater

Tests that exist but prove nothing are worse than missing tests, because they satisfy the TDD gate's letter while voiding it. Reject: tests that assert only that no exception was raised; tests that mock the unit under test (asserting the mock, not the code); tests whose expected values were copied from the implementation's actual output rather than derived from the requirement; tests that duplicate one happy path while every finding-relevant edge stays uncovered; and tests deleted or weakened in the same change that claims coverage grew. For each behavioral change in the diff, name the test that would fail if the change were reverted — if none exists, coverage is theater.

## Scope drift and silent decisions

Diff the work against the request, in both directions. Missing scope: an acceptance criterion quietly dropped, an edge case the plan named but the code skips. Excess scope: refactors, dependency additions, or behavior changes nobody asked for — each is a silent decision that belonged to a human or an ADR. Mid-implementation discoveries must surface as new linked issues, not as unrequested fixes smuggled into the diff. Flag both directions explicitly; an AI agent drifts silently because it does not experience the difference between the request and its interpretation.

## Over-engineering and misapplied context

AI work over-builds: speculative abstraction layers, configuration for requirements nobody stated, defensive handling for impossible states, wrappers around wrappers. Judge against the simplicity rule — flat, direct, no premature abstraction — and demand a present-tense justification for every layer of indirection. The twin failure is misapplied context: code imitated from elsewhere in the repository whose preconditions do not hold here, or a pattern continued past the boundary where it stops making sense. Both read as idiomatic; both are wrong.

## Slop prose

Reports, PR bodies, commit messages, and docs are part of the delivered work and are evaluated as such. Reject: filler that restates the diff without adding information, hedged non-claims ("should generally work as expected"), fluent summaries whose specifics are unfalsifiable, banned cliches, emojis, and puffed-up significance. The humanizer and slop guidance in `.claude/skills/` defines the concrete patterns; a work product whose prose fails that bar goes back with the prose findings enumerated like any other defect — text the human gate must read is a first-class surface.

## Common pitfalls

- Trusting fluency — polish is the property AI failure preserves best; verify substance mechanically.
- Grepping only for the symbols the work uses prominently — hallucinated references hide in imports, config keys, and doc examples.
- Accepting a green suite as proof of coverage — name the test that fails if the change is reverted, per behavior.
- Reviewing only for missing scope — unrequested refactors and dependency additions are silent decisions and get flagged too.
- Calling over-engineering a style preference — speculative abstraction violates the house simplicity rule and is a real finding.
- Skipping the prose — a misleading PR body or fabricated citation corrupts the human gate's decision even when the code is correct.

## Definition of done

- [ ] Every referenced API, path, flag, key, and issue number was existence-checked at the reviewed revision.
- [ ] Every success claim is paired with its evidence, and at least one reported number was independently re-derived.
- [ ] Each behavioral change names a test that would fail on revert; theatrical tests are enumerated as findings.
- [ ] Scope was diffed in both directions against the request, and every silent decision is flagged.
- [ ] Indirection layers carry present-tense justification; misapplied local idioms are called out.
- [ ] Prose surfaces (PR body, commits, docs, report) passed the humanizer/slop bar or their failures are enumerated findings.
