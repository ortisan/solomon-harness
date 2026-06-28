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
