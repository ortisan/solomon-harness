# ADR-0038: Contract-fidelity gates in the start and review stages

- Status: accepted
- Date: 2026-07-17
- Deciders: software_architect, software_engineer, qa (maintainer-approved adoption from the compozy benchmark)
- Issue: #320

## Context and problem statement

Nothing in the lifecycle forces an implementing or reviewing agent to stay faithful to the canonical contract — the spec document, the issue's acceptance criteria, the ADRs — rather than a paraphrase of it. Three unguarded failure modes follow: an agent builds from the issue title or PLAN.md restatement without reading the contract-bearing artifacts; contradictory sources (spec versus issue body versus ADR) are resolved differently on every run, or the deliverable is quietly narrowed to what the current code makes easy; and completion claims are accepted without verification evidence, so review can approve on engineering quality alone. The compozy project documents the end state of this gap: seven consecutive review rounds approved a deliverable that contradicted the spec's canonical examples, because no round ever received them. Solomon adds a wrinkle compozy does not have: two nominally authoritative acceptance-criteria surfaces (the issue body and the spec's mirrored section) that can silently diverge.

## Decision drivers

- Fidelity to the contract must be checked mechanically at defined stage points, not left to per-run judgment.
- Contradiction resolution must be deterministic across runs and agents.
- The existing house mechanism for agent-behavior contracts is command text pinned by fitness tests (elicitation gate #222, spec bar #280); new runtime code is a heavier tool than the problem needs.
- The gates must not add interactive steps that could hang headless runs.

## Considered options

- Prompt-level gates in the command files, pinned by fitness tests (the house pattern).
- Python runtime enforcement (a lint/CI gate diffing deliverable against spec text).
- Status quo: rely on the existing AC/DoD check in the review qa lens.

## Decision outcome

Chosen option "prompt-level gates pinned by fitness tests", because it matches the established mechanism for workflow-policy rules and ships the full defense without new runtime surface. Three gates, defined in `docs/solomon-workflow.md` ("Contract-fidelity gates"):

1. **Spec corpus survey + contract precedence ladder** (`/solomon-start`, `software_engineer` via the `spec_contract_fidelity` skill): inventory and fully read every contract-bearing artifact before PLAN.md; resolve contradictions top-down — machine-checked constraints, contract catalogs, Accepted ADRs, paraphrases — where the issue body's acceptance criteria are canonical, the spec's Acceptance Criteria section is a mirror reconciled toward the issue body, a paraphrase never overrides a higher rung, and the existing runtime shape is never the contract.
2. **Verification iron law** (`/solomon-start` and the `/solomon-review` qa lens, `verification_iron_law` skill): no completion claim without same-run evidence (command, exit code, output summary), verification scope covering claim scope, a pre-push verification report reproduced in the PR body, and the review qa lens citing its own suite run — command, exit code, counts — in the review record.
3. **Contract parity** (`/solomon-review`, `qa` via the `spec_contract_parity` skill): field-by-field comparison of the deliverable against the contract corpus; a parity mismatch is a blocker, engineering quality alone can never earn approval, and the managed review record carries a `Contract parity:` verdict line.

### Consequences

- Positive: paraphrase drift is caught at plan time and again at review; contradiction handling is deterministic; completion claims carry auditable evidence; the two-AC-surface divergence has a defined owner (issue body canonical).
- Negative: start and review gain mandatory reading and reporting work on every issue, including trivial ones; the pinned sentences constrain future rewording of the command files (by design).
- Follow-ups: a mechanical AC-equivalence check between the issue body and the spec mirror (review-stage prompt check today; a `spec-lint.py` companion needs GitHub API access CI does not have), and the remaining compozy-benchmark adoption packages tracked as separate issues.

## More information

Adapted from the compozy benchmark (cy-execute-task's Spec Corpus Survey and Authority/Contract Precedence, cy-final-verify's Iron Law and Spec Contract Parity), with the architect-review improvement that designates the issue body's AC as canonical over the spec mirror. Amends the review qa lens defined under ADR-0019/ADR-0020 without changing merge ownership or the human gate. Enforced by the "Contract-fidelity gates (#320)" section of `tests/test_command_gates.py`. Recorded in project memory via `save_decision`.
