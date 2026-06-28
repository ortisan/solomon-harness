## Common pitfalls to reject


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
