---
name: spec-contract-fidelity
description: Governs the spec corpus survey run before any edit and the contract precedence ladder used to resolve contradictory sources, so the deliverable is built from the canonical contract instead of a paraphrase of it. Use when starting implementation of any issue, before writing PLAN.md or any production or test code, and again whenever two sources disagree about what the deliverable must do.
---

# Spec contract fidelity

Build from the contract, never from a paraphrase of it. The canonical contract for an issue is spread across a small set of artifacts — the spec document, the issue's acceptance criteria, the ADRs the change touches — and the most expensive implementation failure is not a bug but a faithful, well-tested build of the wrong thing. This skill defines two mechanisms that prevent it: the spec corpus survey, which guarantees you have read every contract-bearing artifact before the first edit, and the contract precedence ladder, which guarantees that when sources disagree you resolve the conflict the same way every run instead of guessing. The motivating failure mode is real: a deliverable can pass multiple review rounds on engineering quality while contradicting the product contract wholesale, because no round ever read the artifact that pinned the canonical behavior.

## The spec corpus survey

Run the survey before writing PLAN.md and before any production or test code. Inventory every artifact that could pin concrete facts about the deliverable:

- `docs/specs/<n>-<slug>.md` — the spec document, when the issue has one (ADR-0028 convention): Requirements, Acceptance Criteria, Implementation Pointers, Verification.
- The issue body — acceptance criteria, Definition of Done, out-of-scope list, and any managed development block.
- `docs/adrs/` — every ADR whose decision constrains this change, plus design contracts it cites.
- The incoming handoff contract from `get_latest_activity` and the artifacts it points to.
- Existing tests and validators that encode the current contracted behavior of the surfaces you will touch.

For each artifact record a one-line verdict: **contract-bearing** (it pins concrete facts — names, types, defaults, required flags, routes, commands, state machines, error shapes, copy) or context-only. When the corpus is large, delegate the inventory to a read-only subagent and keep only the verdict list; then read every contract-bearing artifact in full yourself before planning. The survey's output goes into PLAN.md: the problem statement links the issue, and the plan lists the contract-bearing artifacts it was built from, so the reviewer can check the plan against the same corpus. A survey that lists nothing but the issue title is a red flag — either the issue is genuinely trivial or you are about to build from a paraphrase.

## The contract precedence ladder

When two sources disagree, do not pick the convenient one and do not stall. Resolve top-down:

1. **Machine-checkable constraints.** Failing tests, schema definitions, validator rules, lint gates, and the spec's Verification commands. What a machine checks outranks what prose says, because prose drifts and checks do not.
2. **Contract catalogs.** The issue body's Given/When/Then acceptance criteria are canonical; the spec document's Acceptance Criteria section is a mirror of them, and the spec's Requirements plus any canonical example documents complete the catalog. When mirror and issue body diverge, the divergence is itself a finding — reconcile toward the issue body and re-sync the spec at refine or review; never count the two as independent votes. These catalogs own the observable behavior of the deliverable.
3. **ADRs and design contracts.** They own structure: boundaries, dependencies, patterns, quality-attribute trade-offs. An ADR can constrain how you satisfy a catalog entry but does not delete it.
4. **Paraphrases.** PLAN.md, the issue title, PR descriptions, handoff summaries, and code comments are derived restatements: a paraphrase never overrides a higher rung. When your plan disagrees with the spec, the plan is wrong — re-plan, do not reinterpret.

Two rules complete the ladder. Same-rung conflicts resolve toward the reading that satisfies the most acceptance criteria, and the conflict is recorded in PLAN.md so the reviewer sees the judgment call. A material contradiction between rungs — the spec demands what an ADR forbids — is not yours to arbitrate silently: file it through the discovered-problem protocol as a new issue with `Refs #<issue>` and surface the block.

## The runtime shape is never the contract

The existing runtime shape is never the contract. When the contract demands a field, a route, a state, or an error the current code cannot express, extend the runtime to meet the contract; do not quietly narrow the deliverable to what the code already makes easy. If the extension is genuinely out of scope, that is a discovered problem — file it and say so in the PR — never a silent scope cut. The test for this failure mode: if your deliverable's shape matches the old code more closely than it matches the acceptance criteria, you molded the contract to the runtime.

## Common pitfalls

- Building from the issue title and PLAN.md alone when a spec document exists; the plan is a rung-4 paraphrase and the survey would have caught it.
- Marking an artifact context-only because it is long. Length is not a verdict; an examples catalog is contract-bearing precisely because of its concrete values.
- Resolving a spec-versus-ADR contradiction inline "to keep moving". That trade-off belongs to a human via the discovered-problem protocol, not to the implementing agent.
- Treating a passing suite as proof of fidelity. Tests written from the same paraphrase encode the same drift; parity is checked against the catalogs, not against the tests (the qa gate's `spec_contract_parity` owns that check at review).
- Quietly returning what the current adapter can produce instead of what the acceptance criterion states, on the theory that "the interface doesn't support it". That is the runtime-shape failure; extend or file, never shrink.

## Definition of done

- [ ] The survey ran before any edit, and PLAN.md lists every contract-bearing artifact it was built from.
- [ ] Every contract-bearing artifact was read in full, not skimmed via a summary.
- [ ] Every conflict between sources was resolved by the ladder, and the resolution (or filed discovered-problem issue) is recorded.
- [ ] No acceptance criterion was narrowed to fit the existing runtime shape without a filed issue naming the gap.
- [ ] The deliverable's concrete facts — names, defaults, routes, states, error shapes — trace to rung-1/rung-2 sources, not to a paraphrase.
