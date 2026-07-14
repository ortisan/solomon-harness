---
name: defect-triage-and-lifecycle
description: Governs the defect lifecycle state machine from report to closure, including the severity-versus-priority axes, response SLAs, root-cause analysis, and the regression-test closure gate. Use when triaging a new defect, reclassifying severity or priority, or deciding whether a bug can be closed.
---

# Defect Triage and Lifecycle

Run every defect through a deterministic state machine from report to closure, where severity and priority are classified on separate axes, root cause is found before a fix is accepted, and no defect closes without a regression test that failed on the bug and passes on the fix. Treat the project memory as the system of record: defects live as `log_issue` entries, the triage queue is `get_open_issues`, and `get_issue` is the single read before any state transition.

## Severity and priority are orthogonal axes

Classify each defect on two independent scales. Conflating them is the most common triage error and leads to either firefighting cosmetics or sitting on data corruption.

- **Severity** measures technical and user impact, set by QA from evidence, independent of business calendar.
  - S1 Critical: data loss or corruption, security breach, full outage, or a silently wrong financial result in production (mispriced order, wrong PnL, look-ahead leakage reaching live trading). No acceptable workaround.
  - S2 High: a core feature is broken or a wrong-but-loud result; a workaround exists but is costly or manual.
  - S3 Medium: a non-core feature is degraded with an easy workaround.
  - S4 Low: cosmetic, copy, or minor UX issue with no functional impact.
- **Priority** measures scheduling urgency, set with the `product_owner` and `scrum_master`, factoring reach, frequency, and business value.
  - P0 fix now (drop other work), P1 fix this sprint, P2 scheduled in backlog, P3 opportunistic.

The two axes are independent: an S1 in a code path no live strategy touches can be P1; an S4 typo on a sign-up CTA can be P0. Record both, and record the reach (how many users/strategies) and frequency (always / intermittent / once) so priority is data, not opinion. For finance defects, default severity up one level versus a UI bug of the same visible size, because the failure is silent — see `backtesting_verification_specific_because_finance_bugs_are_silent`.

### Severity-driven response SLAs

Bind severity to acknowledgement and resolution targets so triage is not a discussion every time.

| Severity | Acknowledge | Mitigate/workaround | Permanent fix |
|----------|-------------|---------------------|---------------|
| S1       | 15 min      | 4 h                 | 24 h          |
| S2       | 4 h         | 2 days              | 1 sprint      |
| S3       | 1 day       | n/a                 | 2 sprints     |
| S4       | next triage | n/a                 | backlog       |

Track MTTA (time to acknowledge) and MTTR (time to resolve) per severity against these targets; a breached SLA is itself a signal to re-triage, not to relax the number.

## The lifecycle state machine

States and the only legal transitions. Each transition updates the defect's `log_issue` record and, where it crosses an owner, fires `log_handoff`.

1. New: filed via `log_issue`. Must carry title, severity, priority, environment, and a reproduction (steps, expected vs actual, frequency). Missing repro -> Needs Info, not Triaged.
2. Triaged: severity/priority confirmed, reproduced by QA, assigned. A defect that cannot be reproduced is parked in Needs Info with what is required, never silently closed.
3. In Progress: owned by `software_engineer`; fix developed under the TDD cycle.
4. In Review / Fixed: PR open with the linked regression test; awaiting QA verification.
5. Verified: QA confirms the fix on the target branch and the regression test is green in CI.
6. Closed: only from Verified, and only with a linked regression test (see gate below).

Side states: Reopened (a Closed/Verified defect recurs — record the reopen, it counts against quality), Rejected/Won't-Fix and Deferred (both require a rationale via `save_decision`), and Duplicate (link to the canonical issue). Reopen rate target < 5%; a higher rate means verification or RCA is shallow.

## Triage workflow

Run triage on a fixed cadence (daily for S1/S2 inflow, at minimum each sprint planning). The queue is not a spreadsheet — pull it live.

- `get_open_issues` returns the untriaged and in-flight backlog; `get_latest_activity` surfaces defects reported since the last cycle so nothing ages silently.
- For each item, `get_issue` for the full record, then: confirm reproduction, set/adjust severity and priority, deduplicate, and assign. Write the result back through `log_issue` and `log_handoff` to the assignee.
- Reproduction first. A defect is "reproduced" only with a minimal, deterministic recipe; if it is intermittent, capture frequency and seed/inputs and treat flakiness per the `flaky_tests` skill (quarantine, do not delete).
- Aging guard: any S1/S2 past its SLA, or any defect untouched beyond its severity window, is escalated in the cycle. Track defect aging and escape rate (defects found in production / total found) as the two headline triage metrics.

## Root-cause analysis before the fix is accepted

A fix that addresses the symptom without the root cause produces a reopen. RCA is blameless and mandatory for S1/S2.

- Separate the proximate cause (the line that threw) from the root cause (why the defect was introduced and why it escaped). Use 5 Whys for linear causes and a fishbone (Ishikawa) when several factors combine.
- Classify each defect: the inject phase (requirements, design, code, or test-escape) and the type using Orthogonal Defect Classification (assignment, checking, algorithm, interface, timing/serialization, function). The distribution tells you where to add prevention, not just where to patch.
- A test escape (the defect reached this stage because no test covered it) is itself a finding: record the missing coverage and add it. Relate to `mutation_testing` — if a surviving mutant maps to this defect class, the suite was already warning you.
- Persist the RCA and any Won't-Fix/Deferral decision with `save_decision`, including the inject phase, the classification, and the prevention action, so the rationale is auditable and the next agent reading `get_decision` sees why.

## Closure gate: a regression test for every fix

No defect moves to Closed without a regression test, and the test must prove it catches this specific defect.

- Red on the bug, green on the fix: the regression test must fail on the pre-fix commit (reproducing the defect) and pass on the fix. This is the same Red/Green discipline the `software_engineer` applies; a test that passes on the buggy code proves nothing and is rejected.
- Place the test at the lowest layer that reproduces the defect (prefer a unit test over E2E), consistent with `the_test_pyramid_target_distribution`. Mock external services per `mocking_and_isolation_mock_all_external_services` so the regression is deterministic.
- Link the test to the defect: the `get_issue` record must reference the test path/CI run. Verification (`save_session` for the cycle) records that the linked test ran green on the target branch.
- For finance defects, the regression test asserts the corrected numeric outcome with explicit tolerances and a fixed seed, not merely "did not raise" — an assertion-free test is rejected per `common_pitfalls_to_reject`.
- The verification result feeds the per-cycle `qa_report_the_required_output`; closure without a published verification entry is not closure.

## Common pitfalls

- Severity and priority collapsed into one field, so a silent S1 in finance code is deprioritized behind a visible cosmetic bug. Keep two axes.
- Closing a defect because the PR merged, with no regression test linked. Closure requires a test that was red on the bug.
- A "regression test" that passes on the unfixed commit; it asserts the wrong thing and would not catch a recurrence. Demand the red-then-green evidence.
- Marking a defect Closed when it could not be reproduced. Park it in Needs Info with the data required, never silent-close.
- RCA that stops at the proximate cause ("added a null check") without the inject phase or the test-escape finding, so the same class of defect returns.
- Triage from a stale list. Pull `get_open_issues` / `get_latest_activity` live each cycle; a defect tracked only in chat is untracked.
- Won't-Fix or Deferred with no `save_decision` rationale, leaving an undocumented gap an auditor or the next agent cannot reconstruct.
- Reopens treated as new defects, hiding a rising reopen rate that signals shallow verification.
- Security-relevant defects triaged on the QA scale alone; route them to the `security` agent for STRIDE impact before setting severity.

## Definition of done

- [ ] Every defect is filed with `log_issue` carrying severity, priority, environment, reach/frequency, and a minimal reproduction.
- [ ] Severity (impact) and priority (urgency) are set independently; finance/silent defects are not under-rated.
- [ ] Triage runs on a fixed cadence off `get_open_issues` and `get_latest_activity`; SLA breaches and aging defects are escalated.
- [ ] State transitions are legal per the lifecycle machine, written back via `log_issue`, and cross-owner moves fire `log_handoff`.
- [ ] S1/S2 defects have a blameless RCA recorded with `save_decision`: proximate vs root cause, inject phase, ODC type, and a prevention action.
- [ ] No defect is Closed without a linked regression test that was red on the buggy commit and green on the fix, placed at the lowest reproducing layer with external services mocked.
- [ ] Verification of each fix is recorded (`save_session`) and rolled into the QA report; reopen rate, escape rate, MTTR-by-severity, and aging are tracked.
- [ ] Won't-Fix, Deferred, and Duplicate outcomes carry a documented rationale and a link to the canonical issue where applicable.
