# QA Specialist Best Practices

Purpose: a concrete, enforceable standard for designing, automating, and reporting tests so every change reaching production is verified, isolated, deterministic, and traceable.

## Mandatory competencies (non-negotiable)

- Write unit and integration tests for all new code or any logical change. No PR is verifiable without them.
- Mock every external API, network call, clock, filesystem boundary, message broker, and third-party service. Tests must pass offline with no live credentials.
- Implement specific tests that verify backtesting logic and parameters: returns, fees, slippage, position sizing, Sharpe, drawdown, profit factor.
- Run verification on the designated branches: validate `feature/*` against `develop`, and verify `release/*` candidates before production.
- Compile and publish a QA Report for each verification cycle.

## The test pyramid (target distribution)

Hold the shape, not the exact percentages, but use these as a budget when a suite drifts:

- Unit: ~70%. Single function/class, no I/O, sub-millisecond. The bulk of edge-case coverage lives here.
- Integration: ~20%. Real wiring between in-process components (domain plus an adapter), external boundaries faked or containerized.
- E2E: ~10%. Full path through the deployed system. Slowest and most brittle, so keep them few and focused on critical user journeys.

Anti-pattern to reject: the "ice-cream cone" (mostly E2E, few unit). It is slow, flaky, and gives weak failure localization.

## Test design rules

- One behavior per test. The test name states the behavior: `test_<unit>_<condition>_<expected>`.
- Arrange-Act-Assert, visibly separated. No assertions in the Arrange block.
- Deterministic always: pin seeds (`random.seed`, `numpy.random.default_rng(seed)`, `PYTHONHASHSEED`), freeze time (`freezegun` / `time-machine`), and never depend on test execution order. Add `pytest-randomly` to surface order coupling.
- Test behavior through the public contract (ports), not private internals. Tests coupled to implementation rot on every refactor.
- Cover the boundaries: empty, single, max, off-by-one, negative, zero, null/None, malformed input, duplicate, and timezone/locale edges. For numeric paths add NaN, inf, and overflow inputs.
- Use property-based tests (`hypothesis`) for parsers, serializers, math, and invariants. Encode the invariant, let it generate counterexamples, and pin any shrunk failure with `@example`.
- Parametrize instead of copy-pasting (`@pytest.mark.parametrize`). Each case carries an `id`.
- Assert on specific values and error types (`pytest.raises(SpecificError, match=...)`), never a bare `assert result` or broad `Exception`.

## Mocking and isolation (mock all external services)

- Patch at the boundary where the dependency is used, not where it is defined: `patch("module_under_test.client")`, not the library's own module.
- HTTP: intercept with `responses`, `respx` (httpx), or `requests-mock`. Register every expected call and assert it was made. Unmatched requests must fail the test, never hit the network.
- Use `autospec=True` (or `create_autospec`) so mocks reject calls that do not match the real signature. A green test against a drifted signature is a false pass.
- Assert the interaction, not just the return: `assert_called_once_with(...)`, argument captors, call counts and order when order matters.
- Databases and brokers: prefer ephemeral real instances via `testcontainers` for integration tests; reserve in-memory fakes (`fakeredis`, SQLite) for fast unit-level checks. Document which fidelity each test buys.
- Build fixtures with factories (`factory_boy` / `faker`) over hand-rolled dicts so test data stays valid as schemas evolve.
- Forbidden in tests: real API keys, live endpoints, `sleep`-based waits (poll with a timeout instead), and shared mutable global state between tests.

## Backtesting verification (specific, because finance bugs are silent)

Treat the backtest engine as code under test, not a black box.

- No look-ahead / data leakage: assert that any decision at bar `t` uses only data available at or before `t`. Add a regression test that shifts a signal one bar into the future and proves results change, confirming the guard is live.
- Cost realism: every fill applies commission and slippage. Add a zero-cost vs with-cost test proving net return drops by the expected amount. A strategy that only profits at zero cost must be flagged.
- Point-in-time data: verify survivorship-bias-free and as-reported datasets; reject tests built on restated/forward-filled fundamentals.
- Metric correctness: unit-test Sharpe, Sortino, max drawdown, profit factor, and CAGR against hand-computed fixtures with known inputs. Verify Sharpe annualization uses the correct periods-per-year factor.
- Numeric safety: guard division-by-zero (flat-equity Sharpe, zero-trade profit factor), and check for inf/NaN propagation in the equity curve. Validate array/series shapes before vectorized operations.
- Reconciliation: equity curve must equal starting capital plus the cumulative sum of per-trade P&L net of costs. Compute money in `Decimal` or integer minor units and assert within an explicit tolerance, never with naive float equality.
- Determinism: same seed and same data produce a byte-identical result file. Snapshot key metrics and fail on drift.
- Cross-validation context: when reviewing a model-backed strategy, confirm walk-forward / purged K-fold splits, an untouched out-of-sample window, and that train/test windows do not overlap.

## Coverage (a floor, not a finish line)

- Measure with `pytest-cov` (line and branch): `--cov --cov-branch --cov-report=term-missing --cov-report=xml`.
- Thresholds: 80% line coverage minimum project-wide via `--cov-fail-under=80`; 90%+ on core domain, risk, and money-handling modules. Fail CI below the floor.
- Branch coverage is the real target. 100% line with partial branch coverage hides untested conditionals.
- Coverage measures executed lines, not asserted behavior. Defend the suite with mutation testing (`mutmut` or `cosmic-ray`) on critical modules; a surviving mutant means a missing assertion. Target a mutation score of 70%+ on core logic.
- Exclude only generated code and genuine no-ops, with an explicit `# pragma: no cover` and a one-line reason. Never raise the floor by excluding hard code.

## Flaky tests

- Quarantine, do not delete, and do not paper over with auto-reruns. `pytest-rerunfailures` and `flaky` hide the symptom and let nondeterminism back into the gate. Move the test under a marker (for example `@pytest.mark.quarantine`) that the gating run excludes, open a tracking issue with the id, then fix the root cause: nondeterminism, real time, real network, order coupling, or shared state.
- A flaky test in `release/*` blocks the release until resolved or proven unrelated.

## UAT

- Derive UAT cases from acceptance criteria and user stories, not from the implementation.
- Each case has: preconditions, steps, test data, expected result, actual result, pass/fail, and tester sign-off.
- Run on a production-like environment with realistic, anonymized data. Never run UAT against unit mocks.
- Record defects with severity (Blocker/Critical/Major/Minor/Trivial) and reproduction steps. Blockers and Criticals gate release.

## QA Report (the required output)

Publish per verification cycle. Include:

- Scope: branch under test, target branch, commit SHA, build id, environment.
- Results: total, passed, failed, skipped, flaky, with the run command and duration.
- Coverage: line and branch percentages, delta vs the previous run, modules below threshold.
- Backtest verification: metrics validated, leakage and cost checks, determinism check result.
- Defects: id, severity, status, owner.
- Risk and gate decision: explicit Go / No-Go with the reasons.
- Traceability: requirement or story id mapped to the tests that cover it.

Write it in plain, direct language. State the gate decision up front.

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
