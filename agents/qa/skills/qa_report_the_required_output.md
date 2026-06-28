# QA Report the Required Output

The QA report is the artifact `/solomon-review` reads to pass or block a pull request. It is the gate, not a courtesy summary. A verbal "looks good", a green CI badge, or a screenshot of a passing run is not acceptable evidence: the reviewer needs one document that states scope, maps every exit criterion to evidence, and ends in an explicit machine-checkable verdict. This skill owns the report's structure and the go/no-go decision rule. It pulls thresholds from the sibling skills rather than re-deriving them: coverage numbers come from `coverage_a_floor_not_a_finish_line`, the mutation score from `mutation_testing`, requirements-coverage and the traceability matrix from `test_planning_and_traceability`, and defect severities from `uat`.

## Purpose: the report is the review gate

`/solomon-review` runs QA, security, and architecture gates in sequence and only approves when each returns a pass. The QA gate's return value is this report. If the verdict line is missing or ambiguous, the reviewer cannot proceed and the PR stalls. Three rules make the report a gate instead of a status update:

- The verdict is first and explicit. A reader who scrolls no further than line one knows GO or NO-GO and why.
- Every claim is backed by an artifact a third party can re-run: a command, a run ID, a log path. No "manually verified" without the steps.
- The exit criteria are the ones agreed in `test_planning_and_traceability`, stated as numbers. The report does not invent new criteria at review time, and it does not silently drop one that failed.

## Required structure

Publish one report per verification cycle, keyed to a single commit SHA. The sections below are mandatory; omitting one is itself a NO-GO because the gate cannot be evaluated against missing evidence.

- Scope and build under test: feature branch, target branch, commit SHA, build/pipeline ID, environment. The SHA pins the report to exactly what was tested; a report without it certifies nothing.
- Requirements coverage and code coverage, reported separately. Requirements coverage (Must-criteria at 100 percent) comes from the RTM in `test_planning_and_traceability`; line and branch coverage with the `--cov-fail-under` floor come from `coverage_a_floor_not_a_finish_line`. Do not conflate them: 100 percent line coverage with 70 percent requirements coverage is a fail.
- Results by risk band, not just an aggregate pass rate. Roll up pass/fail per High/Medium/Low band so a red High band is not hidden behind green Low-band volume.
- Defect list: each open defect with severity (Blocker/Critical/Major/Minor/Trivial per `uat`), status, owner, and the issue ID from `log_issue`. No prose-only defects.
- Flaky and quarantine status: which tests are quarantined, why, and the tracking issue. A quarantined test covering a Must criterion is an open gap, not a pass.
- Mutation score on critical modules (target 70 percent+ from `mutation_testing`); a surviving mutant on a money path is a missing assertion to disclose.
- The verdict: an explicit PASS/FAIL that maps each exit criterion to its evidence. The mapping is the point; a bare "PASS" with no criterion-to-evidence table is not auditable.

## Evidence makes the verdict auditable

Every number in the report points to something re-runnable. The reviewer, or a future engineer reading the persisted report, must be able to reproduce any claim without asking the author.

- Run IDs: the CI pipeline run URL and the local invocation, so a disputed result can be re-executed against the same SHA.
- Reproduction commands, verbatim, including seed and markers, for example `pytest -q --cov --cov-branch --cov-report=xml -m "not slow" --randomly-seed=1234`.
- Log and artifact paths: the JUnit XML, the `coverage.xml`, the mutation report, the failing test's captured output. A defect row links to the log line that proves it.
- Determinism note for any stochastic suite: the pinned seed and clock, so "passed" means "passes repeatably", not "passed once".

## The go/no-go rule

The verdict is mechanical, not a judgement call. GO requires all three; any single failure is NO-GO:

1. 100 percent of Must acceptance criteria passing, measured by the RTM's requirements-coverage figure from `test_planning_and_traceability`. Should/Could are reported as trend, never as a gate.
2. No open Blocker or Critical defect (severity scale from `uat`). Major and below are disclosed with owners and may ship by explicit, recorded waiver, never by silence.
3. Code-coverage thresholds met: line/branch at or above the `--cov-fail-under` floor and the elevated floor on core/money modules per `coverage_a_floor_not_a_finish_line`, plus the mutation-score target on critical logic per `mutation_testing`.

When a criterion fails, the report says so and links the blocking issue; it does not round up to GO. A waiver for a non-blocking item is a named line in the verdict with who approved it, not an unstated assumption.

## Worked example: a filled QA report

```markdown
# QA Report — PAY-142 partial-refund flow

VERDICT: NO-GO — 1 open Critical (ISSUE-214), Must-criteria coverage 95% (< 100%).

## Scope and build
- Branch: feature/pay-142-partial-refund -> develop
- Commit: 9f3a1c7   Build: ci-2026-06-28-118   Env: staging (prod-like, anonymized data)

## Coverage
- Requirements (Must): 19/20 = 95%   (gate: 100%)  -> FAIL
- Requirements (Should): 7/9 = 78%   (trend only)
- Line: 87%  Branch: 81%  (floor 80% / core 90%)  core module pay/refund.py 91% -> PASS
- Mutation (pay/refund.py): 74% (target 70%) -> PASS

## Results by risk band
| Band | Criteria | Tests | Pass | Fail |
|------|----------|-------|------|------|
| High (>=15) | 6 | 41 | 40 | 1 |
| Medium      | 9 | 55 | 55 | 0 |
| Low         | 5 | 18 | 18 | 0 |

## Defects
| ID | Severity | Status | Owner | Evidence |
|----|----------|--------|-------|----------|
| ISSUE-214 | Critical | Open | a.silva | refund > original rounds up; logs/junit#test_refund_partial |
| ISSUE-219 | Minor | Open | a.silva | UI shows stale balance 1s; waiver requested |

## Flaky / quarantine
- test_refund_webhook_retry: quarantined (timing), QUAR-31. Covers Should-criterion AC-PAY-11, not a Must -> non-blocking.

## Exit-criterion -> evidence
| Criterion | Required | Actual | Evidence |
|-----------|----------|--------|----------|
| Must AC pass rate | 100% | 95% | RTM rev 9f3a1c7; AC-PAY-07 fails |
| No open Blocker/Critical | 0 | 1 | ISSUE-214 |
| Line/branch coverage | 80/80 | 87/81 | coverage.xml, ci run 118 |
| Mutation (core) | 70% | 74% | mutmut report run 118 |

Reproduce: pytest -q --cov --cov-branch --cov-report=xml -m "not slow" --randomly-seed=1234
```

The verdict line resolves to NO-GO from the rule alone: rule 1 fails (95 percent < 100 percent) and rule 2 fails (one open Critical). No discussion required.

## Persist and hand off

The decision must survive the session so the next agent sees why the PR was blocked or cleared, without re-running the suite.

- `save_session` records the cycle: SHA, verdict, the two coverage numbers, and the artifact paths. This is the auditable record the release owner reads later.
- `log_handoff` passes the verdict to the next stage with the requirements-coverage figure and the list of open `log_issue` blocker IDs, mirroring the hand-off contract in `test_planning_and_traceability`. A NO-GO hand-off names exactly what must change to flip the verdict.
- Tie any blocking gap to the release `create_milestone` so a Must-criterion failure cannot quietly ride into a release.

## Common pitfalls

- A verdict buried at the bottom, or worded as "mostly passing", so `/solomon-review` cannot mechanically read GO/NO-GO.
- Reporting one aggregate pass rate that hides a failing High-risk band behind green Low-risk volume.
- Citing code coverage as proof a requirement is done; line coverage cannot see a missing assertion, which is why requirements coverage is reported separately.
- Defects described in prose with no issue ID, severity, or owner, so the blocker count cannot be computed.
- Quarantined or flaky tests counted as passes when they cover a Must criterion, turning an open gap into a false GO.
- No commit SHA, so the report certifies an unknown build and cannot be reproduced.
- A waiver applied silently instead of as a named, approved line in the verdict.
- The report left in the PR thread only and never persisted, so the decision dies with the session.

## Definition of done

- [ ] The report is keyed to a single commit SHA with branch, target, build ID, and environment stated.
- [ ] Requirements coverage (Must at 100 percent), code coverage (line/branch), and mutation score are reported as separate numbers, sourced from `test_planning_and_traceability`, `coverage_a_floor_not_a_finish_line`, and `mutation_testing`.
- [ ] Results are rolled up by risk band, and the defect list carries severity (`uat` scale), status, owner, and `log_issue` ID for every entry.
- [ ] Flaky/quarantine status is disclosed, with any Must-covering quarantine flagged as an open gap.
- [ ] An explicit PASS/FAIL verdict maps each exit criterion to re-runnable evidence (run IDs, logs, reproduction command).
- [ ] The verdict applies the go/no-go rule mechanically: 100 percent Must passing, no open Blocker/Critical, coverage thresholds met.
- [ ] The cycle is persisted with `save_session` and handed off with `log_handoff` (coverage figure + open blocker IDs), with blocking gaps tied to the release `create_milestone`.
