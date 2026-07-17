---
name: spec-contract-parity
description: Governs the contract parity gate at review — a field-by-field comparison of the deliverable against the canonical contract artifacts (spec, acceptance criteria, ADRs) where any parity mismatch is a blocker and engineering quality alone can never earn approval. Use when reviewing a pull request in the qa lens, after the test run and acceptance-criteria check, and whenever a review is asked to approve work whose spec document or examples were not in the review's inputs.
---

# Spec contract parity

Contract parity is the review-side answer to a specific, documented failure: a deliverable can pass every quality gate — green suite, clean architecture, tidy diff — across multiple review rounds while contradicting the product contract wholesale, because no round ever compared the built thing against the artifact that pinned the canonical behavior. The parity gate closes that hole. It is a field-by-field comparison of the deliverable against the contract catalogs, run by the qa lens as part of `/solomon-review`, and its verdict is absolute: a parity mismatch is a blocker regardless of how well-engineered the change is, and engineering quality alone can never earn approval.

## Assemble the contract corpus first

A parity check is only as good as its inputs. Before comparing anything, collect the same corpus the implementer's spec corpus survey should have used: the spec document (`docs/specs/<n>-<slug>.md`) with its Requirements, Acceptance Criteria, and Verification sections; the linked issue's acceptance criteria and Definition of Done; every ADR the PR cites or touches; and any canonical example document the spec references. A review round that never received these artifacts is invalid as a parity check — record that the gate could not run rather than letting a quality-only pass stand in for it. This mirrors the incoming handoff contract: the start-to-review handoff points at PLAN.md and the PR, but parity is checked against the contract, not against the plan, because the plan is a paraphrase and inherits its drift.

## The field-by-field comparison

Walk the contract corpus and diff the deliverable against it field by field — concrete fact against concrete fact, not theme against theme:

- **Names and identifiers** — commands, flags, routes, functions, columns, config keys the contract states verbatim.
- **Types, defaults, and required flags** — a contract default of `2` delivered as `4`, an optional field delivered required.
- **Behavior under the stated scenarios** — each Given/When/Then reproduced against the actual code path, not the test that claims to cover it.
- **State machines and orderings** — allowed statuses, legal transitions, precedence orders the contract fixes.
- **Error shapes and messages** — the contracted failure behavior, which drifts more often than the happy path.
- **Copy and rendered output** — user-visible strings a spec or example pins.

For every mismatch, report the file:line of the deliverable, the contract line it violates, and the severity — a parity mismatch is a blocker. The remediation direction is fixed: fix the deliverable; never reinterpret the contract to match what was built. If the implementer believes the contract itself is wrong, that is a discovered problem for a human to arbitrate through a new issue, not a reviewer's judgment call.

## Why green tests are not parity

The suite passing proves the code matches the tests. If the tests were written from the same paraphrase the implementation was built from — the issue title, the PLAN.md restatement — they encode the same drift, and green proves nothing about the contract. So parity is checked against the catalogs directly, and the test suite itself becomes an object of the check: every contracted behavior needs a test that genuinely asserts it. A hollow test — one that exists, names the behavior, runs the code, and asserts nothing that would fail if the contracted behavior broke — is a parity finding in its own right, adjacent to what `mutation_testing` catches statistically: an assertion that no contract violation can kill is not evidence. Flag hollow tests as blockers when they cover acceptance criteria, majors otherwise.

## Verdict integration

The parity result merges into the review verdict alongside the existing checks (test pyramid, suite run, acceptance criteria, Definition of Done): zero parity mismatches is a precondition for approval, and the review record's findings list each mismatch with its contract citation so a re-review can confirm the fix against the same line. When the gate cannot run — no spec, no AC, corpus missing from the inputs — say so explicitly in the verdict rather than approving on quality; an unrunnable gate is a process finding, not a pass.

## Common pitfalls

- Approving on engineering quality when the contract artifacts were never in the review inputs. That is the exact seven-rounds failure this gate exists to prevent.
- Checking parity against PLAN.md or the PR description. Both are paraphrases; parity runs against the spec, the acceptance criteria, and the ADRs.
- Treating a mismatch as minor because the code's behavior "is arguably better". Improvement proposals go through the contract's owner via a new issue; the gate compares, it does not renegotiate.
- Accepting a test's existence as coverage of a criterion without reading its assertions; hollow tests satisfy grep, not the contract.
- Softening a parity blocker to a major to converge a long review. Severity is defined by the gate, not by review fatigue.
- Re-running only the previously failing comparison after a fix. A parity fix can break an adjacent field; re-walk the affected artifact section.

## Definition of done

- [ ] The contract corpus (spec, issue AC/DoD, cited ADRs, canonical examples) was assembled and read before comparing.
- [ ] Every contracted name, default, scenario, state, and error shape was compared field by field against the deliverable.
- [ ] Every mismatch is reported with deliverable file:line, the violated contract line, and blocker severity.
- [ ] Hollow tests over acceptance criteria were flagged; no criterion is "covered" by a test that asserts nothing.
- [ ] The verdict states parity explicitly — passed, failed with findings, or could-not-run — and approval was only possible with zero mismatches.
