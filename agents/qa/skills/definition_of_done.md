# QA Definition of Done

The exit gate for a QA verification cycle: what must hold before a change is signed off. The pitfalls below are the ways a suite gets falsely called done against this checklist; the checklist itself follows.

## Common pitfalls

- A green suite that only passes online with live credentials, because the external-service mocking requirement was never actually met.
- Coverage reported as one overall line number while the 90%+ floor on core/risk/money modules goes unchecked; the risky code is exactly where the gap hides.
- Determinism claimed without a randomized-order run, pinned seeds, or a frozen clock, so a pass proves nothing about the next run.
- Backtest checks accepted from the engine's own metrics with no independent reconstruction; look-ahead and missing costs are silent and self-flattering.
- Flaky tests auto-rerun until green, or quarantined without a tracking issue, which reclassifies an open gap as a pass.
- Verification run on the wrong branch, so the sign-off certifies a build that will never ship as tested.
- A QA Report published without an explicit Go / No-Go or requirement-to-test traceability, leaving the review gate nothing mechanical to evaluate.

## Definition of done


- Unit and integration tests exist for every new or changed behavior, and the full suite is green.
- Every external service, clock, and network call is mocked or containerized. The suite passes offline with no live credentials.
- Tests are deterministic: seeds pinned, time frozen, order-independent (verified with randomized order).
- Branch coverage meets the floor (80% overall, 90%+ on core/risk/money modules); CI fails below it.
- Boundary, error, and overflow/NaN/divide-by-zero cases are covered; error type and message asserted.
- Backtest checks pass: no look-ahead, costs applied, metrics match fixtures, equity reconciles within tolerance, result is reproducible.
- Mutation score on core logic meets target, or surviving mutants are triaged.
- No flaky tests left in the gating run; each quarantined test has a tracking issue and is not masked by auto-reruns.
- Verification ran on the correct branch (`feature/*` vs `develop`, `release/*` before production).
- QA Report published with an explicit Go / No-Go and requirement-to-test traceability.
