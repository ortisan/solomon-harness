# Test Planning and Traceability

Build a risk-based test plan that ties every acceptance criterion to the tests that verify it, so the release gate measures coverage of requirements, not just lines executed. The plan is a contract: each criterion has a stable identifier, a risk score that sets how deeply it is tested, named design techniques that generate the cases, and a traceability matrix that makes uncovered requirements and orphan tests both visible. Without this, a suite can be green and well-covered by `pytest-cov` while a Must-have requirement was never exercised.

## Standards and the test basis

- Plan against ISO/IEC/IEEE 29119: Part 2 (risk-based test process), Part 3 (test plan and traceability documentation), Part 4 (test design techniques). ISTQB Foundation terminology is the shared vocabulary; use it so the plan reads the same to any engineer.
- The test basis is the acceptance criteria, not the implementation. Pull Given/When/Then criteria and their IDs from the product_owner outputs (`acceptance_criteria_given_when_then`, `the_prd_contract_template`); each criterion must already carry a stable ID such as `AC-PAY-03`. If a criterion is ambiguous or untestable, it is a requirements defect: send it back via `log_issue` before writing a single case, do not guess the intent in a test.
- One acceptance criterion can map to many tests across levels; one test can verify part of several criteria. The matrix records that many-to-many relation explicitly. This is forward and backward traceability, mirroring product_owner `requirements_traceability` from the requirement side.

## Plan structure and entry/exit criteria

The plan document follows the ISO/IEC/IEEE 29119-3 test plan skeleton; keep it short and operational, not ceremonial.

- Scope and items: the criteria IDs in and out of this cycle, and the branch under test (`feature/*` against `develop`, `release/*` before production, per the QA duties).
- Risk register: the per-criterion scores from the section below, the single source for prioritization.
- Approach: levels exercised (unit/integration/E2E, sized by `the_test_pyramid_target_distribution`), design techniques, and the environment and test data (production-like and anonymized for UAT, see `uat`).
- Entry criteria: criteria are testable and ID'd, the build deploys, external services are mocked at the boundary (`mocking_and_isolation_mock_all_external_services`), and seeds/clock are pinned.
- Exit criteria: 100 percent of Must criteria covered and passing, no open Blocker/Critical defects, requirements- and code-coverage thresholds met. These are the gate; state them as numbers, not adjectives.

## Risk-based prioritization

Test depth is a budget; spend it where failure costs most. Score each criterion before designing cases.

- Risk = Likelihood x Impact, each on a 1-5 scale, giving a 1-25 level. Likelihood reflects code novelty, complexity, churn, and dependency count; Impact reflects user/money/safety/regulatory damage if it fails. Document the inputs, not just the product, the same way product_owner `prioritization` records RICE inputs.
- For safety- or money-critical paths, use the FMEA Risk Priority Number instead: RPN = Severity x Occurrence x Detection (each 1-10, range 1-1000). Detection is the value QA owns: low detectability (a silent failure mode, see `backtesting_verification_specific_because_finance_bugs_are_silent`) raises RPN even when severity is moderate.
- Map risk band to test intensity:
  - High (risk >= 15 or RPN >= 200): full design techniques (boundary + equivalence + decision table as applicable), tested at unit and integration, plus an E2E happy path. Mandatory.
  - Medium (8-14 / 100-199): equivalence partitions plus boundaries at one level.
  - Low (< 8 / < 100): single representative case or scripted exploratory session; do not gold-plate.
- Execution order follows risk: run P1 (highest risk) first so the gate fails fast on the most damaging defects. Align P-levels with the UAT defect severities in `uat` (Blocker/Critical gate release).
- Record the agreed risk model and band thresholds once with `save_decision` so every cycle prioritizes identically; recover it with `get_decision` rather than re-arguing it each release.

## Test design techniques

Name the technique per criterion; "I tested it" is not a technique. The ISO/IEC/IEEE 29119-4 specification-based methods — equivalence partitioning, boundary value analysis, decision tables, state-transition, pairwise/combinatorial, and property-based — are owned, with their mechanics, worked examples, and the canonical boundary set, by `test_design_rules`. This skill does not re-explain them; it decides which technique each criterion warrants — by the risk band defined in `Risk-based prioritization` above, so a High-band criterion draws the full set at unit and integration while Medium and Low scale down exactly as that map specifies — and records the chosen technique in the matrix so case design is auditable. For parsers, math, and stated invariants, record the `hypothesis` property and its invariant as the verifying artifact. Every technique's definition and code example lives in `test_design_rules`; cite it, do not restate it.

## The traceability matrix

The matrix (RTM) is the deliverable that proves the plan is complete. Keep it as data, regenerated each cycle, not a stale spreadsheet.

| AC ID | Risk | Test IDs | Level | Technique | Status | Defect IDs |
|-------|------|----------|-------|-----------|--------|------------|
| AC-PAY-03 | 20 | test_fee_at_min, test_fee_below_min, test_fee_decision_rules | unit, integration | BVA + decision table | pass | - |
| AC-PAY-07 | 12 | test_refund_partial | integration | equivalence | fail | ISSUE-214 |

- Maintain it bidirectionally. Forward (AC -> tests) surfaces any criterion with zero linked tests: a coverage hole. Backward (test -> AC) surfaces orphan tests that verify nothing in the current scope, which are noise to prune or a sign of a missing requirement to file.
- A Must-have criterion (MoSCoW from product_owner `prioritization`) with no passing linked test is a release blocker. Raise it with `log_issue` and tie it to the release `create_milestone`; do not let it pass on the strength of incidental code execution.
- Every defect found gets a row link, so a reader can move criterion -> test -> defect -> severity in one hop, and so a fixed defect points back to the criterion that must re-pass.

## Reporting requirements coverage, not just code coverage

Code coverage answers "did a test execute this line"; requirements coverage answers "did a test verify this behavior". They are different metrics and must be reported separately.

- Requirements coverage = (acceptance criteria with at least one passing linked test) / (total acceptance criteria). Report Must-criteria coverage separately and gate the release at 100 percent of Must; track Should/Could as trend, not as a gate.
- Publish both numbers in the QA report (`qa_report_the_required_output`) beside the `pytest-cov` line/branch figures from `coverage_a_floor_not_a_finish_line`. 100 percent line coverage with 70 percent requirements coverage is the classic trap: incidental execution with no asserting test behind the requirement.
- Add a result rollup by risk band so the reader sees that the highest-risk criteria are not the ones still failing. A green low-risk band over a red high-risk band is worse than the aggregate pass rate suggests.
- Track requirement-level defect density (defects per criterion) across cycles. A criterion that keeps reopening defects is under-specified or under-tested at its risk band; escalate it rather than re-running the same cases.
- Persist the approved plan and the per-cycle RTM with `save_memory`, and record the verification cycle with `save_session`. When handing executed results to the next stage or release owner, use `log_handoff` with the requirements-coverage number and the list of open `log_issue` blockers, so the gate decision is auditable, not a verbal "looks good".

## Common pitfalls

- Designing tests from the implementation instead of the acceptance criteria; the suite then re-asserts the code's current behavior and cannot catch a requirement that was built wrong.
- Acceptance criteria with no stable ID, so traceability is by prose matching and silently drifts as wording changes.
- A flat plan that tests every criterion to the same depth, starving high-risk paths while gold-plating trivial ones.
- Risk scored as a single gut number with no Likelihood/Impact (or Severity/Occurrence/Detection) breakdown, so it cannot be reviewed or reproduced next cycle.
- Decision logic verified by a few happy-path cases instead of one test per surviving decision-table rule; the untested rules are where the production bug lives.
- Reporting only code coverage and calling the requirement done; line coverage cannot detect a missing assertion behind an executed line.
- Orphan tests left in the suite with no linked criterion, and uncovered Must-have criteria left un-filed; both hide in a green run.
- The RTM authored once and never regenerated, so it certifies a prior release while the current criteria have moved.
- Combinatorial blow-up "solved" by deleting cases at random instead of an all-pairs reduction with high-risk combinations added back.

## Definition of done

- [ ] Every in-scope acceptance criterion has a stable ID sourced from the product_owner PRD, and ambiguous or untestable criteria were returned via `log_issue` before test design.
- [ ] Each criterion carries a documented risk score (Likelihood x Impact, or FMEA RPN for critical paths) with its inputs recorded, and the risk model/thresholds are persisted via `save_decision`.
- [ ] Test depth and execution order follow the risk band; high-risk criteria use boundary, equivalence, and decision-table techniques across unit and integration levels.
- [ ] A named design technique is recorded per criterion; decision-table criteria have at least one test per surviving rule and combinatorial parameters use an all-pairs set.
- [ ] A bidirectional traceability matrix links AC -> tests -> defects, with no uncovered Must-have criterion and no unexplained orphan tests.
- [ ] Requirements coverage is computed and reported separately from code coverage, with Must-criteria coverage at 100 percent gating the release.
- [ ] The QA report includes the requirements-coverage figure and a result rollup by risk band, and the plan/RTM/cycle are persisted via `save_memory` and `save_session`.
- [ ] Release hand-off uses `log_handoff` with the coverage number and open blocker issues; blocking gaps are tied to the release `create_milestone`.
