---
name: requirements-traceability
description: Governs maintaining the Requirements Traceability Matrix - the auditable chain from PRD requirement through story and acceptance criterion to test and PR/commit, with stable IDs and computed orphan detection. Use when freezing a PRD, handing criteria to qa, or reconciling coverage gaps.
---

# Requirements Traceability

Maintain an unbroken, auditable chain from every PRD requirement down to the code and tests that satisfy it, so no requirement ships untested and no code exists without a requirement behind it. The Product Owner owns the forward links (requirement to story to acceptance criterion); QA owns the test links back up the chain (see qa `test_planning_and_traceability`). The shared contract between you is the Requirements Traceability Matrix (RTM), kept as a memory-backed artifact rather than a stale spreadsheet.

## The traceability chain and stable IDs

The canonical chain is one directed path per requirement:

```
PRD requirement  ->  user story  ->  acceptance criterion  ->  test(s)  ->  PR / commit
   PRD-CHECKOUT-03 ->  US-14      ->  AC-14.2             ->  T-checkout-empty-cart -> #214 / a1b9f3c
```

Give every node a stable, immutable ID and never renumber:

- Requirement: `PRD-<AREA>-<NN>` (e.g. `PRD-CHECKOUT-03`), assigned where the requirement is first stated in the PRD (see `the_prd_contract_template`).
- User story: `US-<NN>`, one per INVEST story (see `user_stories_invest`).
- Acceptance criterion: `AC-<story>.<n>` (e.g. `AC-14.2`), one per Given-When-Then scenario (see `acceptance_criteria_given_when_then`).
- Test ID: owned by QA, but it must carry the `AC-<id>` it covers so the link is machine-readable.
- Delivery: the PR number and merge commit SHA.

IDs are append-only. When a requirement is dropped, mark it `obsolete` with the superseding ID and the decision that retired it; do not reuse the number. ISO/IEC/IEEE 29148:2018 calls this bidirectional traceability, and it is the whole point: you must be able to walk the chain forward (does requirement X have a passing test?) and backward (why does this test exist?).

## The Requirements Traceability Matrix

The RTM is one row per acceptance criterion, because the AC is the atomic verifiable unit. Tracing at requirement granularity is too coarse to prove coverage.

| Req | Story | AC | Test(s) | PR/commit | Status |
| --- | --- | --- | --- | --- | --- |
| PRD-CHECKOUT-03 | US-14 | AC-14.1 | T-checkout-happy | #214 / a1b9f3c | covered, passing |
| PRD-CHECKOUT-03 | US-14 | AC-14.2 | T-checkout-empty-cart | #214 / a1b9f3c | covered, passing |
| PRD-CHECKOUT-03 | US-14 | AC-14.3 | (none) | - | GAP |

Status values: `not started`, `in progress`, `covered, passing`, `covered, failing`, `GAP` (no test), `obsolete`. A row is only green when a linked test exists and passes. The PO fills Req/Story/AC at PRD freeze; QA fills Test and flips Status as tests are written and run.

### A worked row, end to end

Read one row as a full sentence to confirm the chain is real, not nominal:

- **Requirement** `PRD-CHECKOUT-03`: "A shopper with an expired saved card can complete checkout by updating the card inline." Stated in the PRD problem/scope sections, frozen with an ID.
- **Story** `US-14`: "As a returning shopper, I want to update my expired card during checkout, so that I do not lose my cart."
- **Acceptance criterion** `AC-14.2`: "Given a shopper with an expired saved card, When they submit a valid replacement card, Then the order completes and the card is saved." This is the atomic, verifiable promise.
- **Test** `T-checkout-empty-cart` / `test_ac_14_2_expired_card_replaced`: a pytest carrying `@pytest.mark.requirement("AC-14.2")`, asserting the order completes and the token is stored. Owned by QA.
- **Delivery** `#214 / a1b9f3c`: the PR and merge commit, whose message carries `Refs: US-14, AC-14.2` and `Closes #214`.

Every cell points at the next; if any cell is empty the row is not green. That is the contract: an accepted promise (`AC-14.2`) is verified by a named, passing test and tied to the exact code that satisfied it.

## Memory-backed RTM, not a spreadsheet

Persist the RTM through the project memory so it survives sessions and is auditable, instead of a file that drifts:

- Store the matrix per PRD with `save_memory` under a deterministic key: `rtm:PRD-<name>` (e.g. `rtm:PRD-CHECKOUT`). The key is derived from the PRD area, lowercased after the prefix is not required but the `PRD-<AREA>` segment must match the requirement IDs exactly so the row IDs and the record key never diverge. Group every RTM under a single `category` (use `category="rtm"` on the `save_memory` call) so `get_memory` can list all matrices for a sprint reconciliation in one query rather than guessing keys. Update the record whenever a link is added; read the current baseline with `get_memory` before every reconciliation.
- At sprint start, hand the frozen baseline to QA with `log_handoff` (from `product_owner` to `qa`), naming the PRD key and the set of ACs in scope. QA reads it, writes tests, and writes the test IDs back into the same RTM record. This is the explicit ownership boundary.
- Every coverage `GAP` that remains after planning is a real defect in the plan: open it with `log_issue` (one issue per uncovered AC, titled with the `AC-<id>`) so it appears in `get_open_issues` and blocks the release gate. Close the issue only when the RTM row goes green.
- Any scope change that re-links the chain (an AC removed, a requirement split, a story merged) must be recorded with `save_decision` referencing the affected IDs and the rationale, then the RTM updated. Use `get_decision` to reconstruct why a link changed. Silent edits to acceptance criteria after freeze are forbidden; route them through the scope-change protocol (see `scope_boundaries`).
- Reconcile drift with `get_latest_activity` and `get_session`: compare the RTM against merged PRs and the QA test inventory at least once per sprint, and before any release sign-off.

## Linking code and tests to requirements

Make the backward links machine-readable so the RTM can be regenerated, not hand-typed:

- Commits and PRs carry a Git trailer: `Refs: US-14, AC-14.2`, and `Closes #214` to tie in the tracking issue (Conventional Commits; see scrum_master). A grep over the log then yields requirement-to-commit links for free.
- Tests tag the AC they verify. In this Python stack, a pytest marker `@pytest.mark.requirement("AC-14.2")` or a naming convention `test_ac_14_2_*` makes coverage queryable. QA owns the exact mechanism; the PO owns that the tag value matches a real AC ID.
- For automated, gated tracing, OpenFastTrace (OFT) parses `req~`/`[covers]` markers across PRD, code, and tests and fails CI on any uncovered or orphaned item. ReqIF (OMG) is the interchange format if requirements live in an external ALM tool (Jama, Polarion, DOORS). Prefer one source of truth: the RTM in project memory, with external tools synced from it, not the reverse.

## Detecting orphans: forward and backward gaps

Both orphan classes are computed by set difference between the RTM's AC IDs and the IDs the codebase actually references; this is mechanical, run it every reconciliation:

- **Orphan requirement (forward gap, untested promise).** An AC in the frozen RTM with no linked, passing test. Detect it by listing every `AC-<id>` in the `rtm:PRD-<name>` record and subtracting the set of AC IDs that appear in a test tag or commit trailer. Anything left is an orphan requirement: scope that was accepted but is unverified or unbuilt. *Example:* `AC-14.3` is in the RTM but no `@pytest.mark.requirement("AC-14.3")` and no `Refs: AC-14.3` exist anywhere — it surfaces as a `GAP` row and must get a `log_issue`.
- **Orphan test (backward gap, unrequested work).** A test whose `AC-<id>` tag points at no AC in any frozen RTM (or whose tag is missing entirely). Detect it by collecting every AC referenced by a test marker and subtracting the union of AC IDs across all `rtm:*` records; the remainder is orphan tests. *Example:* `test_ac_99_1_*` references `AC-99.1`, which exists in no PRD — either a requirement was never written (backfill it) or the test is dead (delete it).

Because both the RTM (memory) and the references (test markers, commit trailers) are queryable, this is a CI-able diff, not a manual audit. Report both counts each sprint; a non-zero forward count blocks release, and a non-zero backward count means the plan and the code have silently diverged.

## Coverage metrics and gates

Compute these from the RTM, not from line coverage (line coverage is a QA concern; requirement coverage is yours):

- AC coverage = ACs with at least one passing linked test / total in-scope ACs. Release gate: 100 percent. Anything below means an accepted requirement ships unverified.
- Requirement coverage = requirements with every AC green / total requirements. Report per PRD.
- Orphan-test rate = tests linked to no AC / total tests. Target 0; each orphan is either a missing requirement to backfill or dead test to delete.
- Orphan-requirement rate = requirements with no downstream story or AC / total. Target 0 at baseline freeze; a non-zero value means the PRD has unimplementable or forgotten scope.

Forward and backward orphan counts both matter: forward orphans are untested promises, backward orphans are unrequested work. Regulated contexts (IEC 62304 medical, DO-178C avionics, ISO 26262 automotive) mandate zero of both and a signed RTM as an audit deliverable; even outside them, hold the same bar at release.

## Common pitfalls

- Tracing at requirement granularity instead of per acceptance criterion, so a half-covered requirement reads as green. Row the RTM by AC.
- A spreadsheet RTM that no automation reads or writes; it is stale within a sprint. Back it with `save_memory` and regenerate links from commit trailers and test tags.
- Renumbering or reusing IDs after a change, which silently breaks every existing link. IDs are append-only; retire with an `obsolete` marker and a `save_decision`.
- One-directional traceability: forward links exist but no test points back at its AC, so you cannot prove a test verifies what it claims. 29148 requires both directions.
- An RTM record key that does not match its requirement IDs (e.g. `rtm:checkout` while rows use `PRD-CART-*`), so reconciliation cannot find the matrix for a requirement.
- Coverage gaps tracked only in someone's head instead of `log_issue`, so they never block the release gate.
- Treating code line/branch coverage as requirement coverage. High line coverage with an uncovered AC still means an unverified requirement.
- Editing acceptance criteria after sprint freeze without a recorded decision, desynchronizing the RTM from what QA tested.
- Orphan tests left unexplained, hiding either scope creep (work nobody requested) or a missing requirement.

## Definition of done

- [ ] Every in-scope requirement has a stable `PRD-<AREA>-<NN>` ID and traces forward through `US-`, `AC-`, test, and PR/commit with no broken link.
- [ ] The RTM is rowed per acceptance criterion and persisted with `save_memory` under the `rtm:PRD-<name>` key with `category="rtm"`, not in an ad-hoc file.
- [ ] The frozen baseline was handed to QA with `log_handoff`, and QA has written test IDs back into the same record (boundary with qa `test_planning_and_traceability` respected).
- [ ] Backward links are machine-readable: commits use a `Refs: AC-<id>` trailer and tests tag their AC; the RTM can be regenerated from them.
- [ ] Orphan requirements and orphan tests are computed by set difference each reconciliation; both counts are reported and forward orphans are 0 before release.
- [ ] AC coverage is 100 percent of in-scope criteria before release; orphan-test and orphan-requirement rates are 0 or each exception is justified.
- [ ] Every remaining coverage GAP has an open issue via `log_issue` and blocks the release gate until its RTM row is green.
- [ ] Every post-freeze change to the chain is recorded with `save_decision` referencing the affected IDs; no IDs were renumbered or reused.
- [ ] The RTM was reconciled against merged PRs and the QA test inventory (via `get_latest_activity`) before sign-off.
