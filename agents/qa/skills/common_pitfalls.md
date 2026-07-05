# QA Common Pitfalls

The test-suite failure modes a QA reviewer rejects on sight: hollow assertions, drifting mocks, masked flake, and backtests validated at zero cost. The closing checklist is the gate proving a suite carries none of them.

## Common pitfalls


- Tests that assert nothing, or assert only "did not raise".
- Mocks without `autospec`, so signature drift passes silently.
- Patching the library's own module instead of the import site in the unit under test.
- Chasing a coverage number while branch coverage and assertions lag.
- `sleep`-based synchronization instead of polling with a timeout.
- Auto-rerunning flaky tests until they pass instead of fixing the nondeterminism.
- Backtests validated only at zero cost, or with restated/forward-filled data.
- Reconciling money with float equality instead of Decimal or minor units.
- E2E tests standing in for missing unit tests, making the suite slow and the failures unlocalized.
- Shared fixtures that mutate global state and leak between tests.

## Definition of done

- [ ] Every test asserts an observable outcome, not merely "did not raise", and failure paths check the error type and message.
- [ ] All mocks use `autospec` or `create_autospec` and patch the import site in the unit under test, not the library's own module.
- [ ] Branch coverage and assertion quality were reviewed alongside the raw coverage number; no metric was chased for its own sake.
- [ ] Synchronization polls a condition with a timeout; no `sleep`-based wait remains in the suite.
- [ ] No flaky test is masked by auto-reruns: each one is fixed or quarantined with a tracking issue.
- [ ] Backtest tests charge non-zero costs and run on point-in-time data, with no restated or forward-filled inputs.
- [ ] Money reconciliation uses `Decimal` or integer minor units, never float equality.
- [ ] Each assertion lives at the lowest pyramid level that can make it, and fixtures leave no shared state between tests, verified under randomized order.
