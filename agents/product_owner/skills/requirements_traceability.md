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

## Memory-backed RTM, not a spreadsheet

Persist the RTM through the project memory so it survives sessions and is auditable, instead of a file that drifts:

- Store the matrix per PRD with `save_memory` under a deterministic key such as `rtm:PRD-CHECKOUT`. Update it whenever a link is added; read the current baseline with `get_memory` before every reconciliation.
- At sprint start, hand the frozen baseline to QA with `log_handoff` (from `product_owner` to `qa`), naming the PRD key and the set of ACs in scope. QA reads it, writes tests, and writes the test IDs back into the same RTM record. This is the explicit ownership boundary.
- Every coverage `GAP` that remains after planning is a real defect in the plan: open it with `log_issue` (one issue per uncovered AC, titled with the `AC-<id>`) so it appears in `get_open_issues` and blocks the release gate. Close the issue only when the RTM row goes green.
- Any scope change that re-links the chain (an AC removed, a requirement split, a story merged) must be recorded with `save_decision` referencing the affected IDs and the rationale, then the RTM updated. Use `get_decision` to reconstruct why a link changed. Silent edits to acceptance criteria after freeze are forbidden; route them through the scope-change protocol (see `scope_boundaries`).
- Reconcile drift with `get_latest_activity` and `get_session`: compare the RTM against merged PRs and the QA test inventory at least once per sprint, and before any release sign-off.

## Linking code and tests to requirements

Make the backward links machine-readable so the RTM can be regenerated, not hand-typed:

- Commits and PRs carry a Git trailer: `Refs: US-14, AC-14.2`, and `Closes #214` to tie in the tracking issue (Conventional Commits; see scrum_master). A grep over the log then yields requirement-to-commit links for free.
- Tests tag the AC they verify. In this Python stack, a pytest marker `@pytest.mark.requirement("AC-14.2")` or a naming convention `test_ac_14_2_*` makes coverage queryable. QA owns the exact mechanism; the PO owns that the tag value matches a real AC ID.
- For automated, gated tracing, OpenFastTrace (OFT) parses `req~`/`[covers]` markers across PRD, code, and tests and fails CI on any uncovered or orphaned item. ReqIF (OMG) is the interchange format if requirements live in an external ALM tool (Jama, Polarion, DOORS). Prefer one source of truth: the RTM in project memory, with external tools synced from it, not the reverse.

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
- Coverage gaps tracked only in someone's head instead of `log_issue`, so they never block the release gate.
- Treating code line/branch coverage as requirement coverage. High line coverage with an uncovered AC still means an unverified requirement.
- Editing acceptance criteria after sprint freeze without a recorded decision, desynchronizing the RTM from what QA tested.
- Orphan tests left unexplained, hiding either scope creep (work nobody requested) or a missing requirement.

## Definition of done

- [ ] Every in-scope requirement has a stable `PRD-<AREA>-<NN>` ID and traces forward through `US-`, `AC-`, test, and PR/commit with no broken link.
- [ ] The RTM is rowed per acceptance criterion and persisted with `save_memory` under a per-PRD key, not in an ad-hoc file.
- [ ] The frozen baseline was handed to QA with `log_handoff`, and QA has written test IDs back into the same record (boundary with qa `test_planning_and_traceability` respected).
- [ ] Backward links are machine-readable: commits use a `Refs: AC-<id>` trailer and tests tag their AC; the RTM can be regenerated from them.
- [ ] AC coverage is 100 percent of in-scope criteria before release; orphan-test and orphan-requirement rates are 0 or each exception is justified.
- [ ] Every remaining coverage GAP has an open issue via `log_issue` and blocks the release gate until its RTM row is green.
- [ ] Every post-freeze change to the chain is recorded with `save_decision` referencing the affected IDs; no IDs were renumbered or reused.
- [ ] The RTM was reconciled against merged PRs and the QA test inventory (via `get_latest_activity`) before sign-off.
