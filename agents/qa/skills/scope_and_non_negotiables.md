# QA Specialist Best Practices

Purpose: a concrete, enforceable standard for designing, automating, and reporting tests so every change reaching production is verified, isolated, deterministic, and traceable.

## Scope and non-negotiables


- Write unit and integration tests for all new code or any logical change. No PR is verifiable without them.
- Mock every external API, network call, clock, filesystem boundary, message broker, and third-party service. Tests must pass offline with no live credentials.
- Implement specific tests that verify backtesting logic and parameters: returns, fees, slippage, position sizing, Sharpe, drawdown, profit factor.
- Run verification on the designated branches: validate `feature/*` against `develop`, and verify `release/*` candidates before production.
- Compile and publish a QA Report for each verification cycle.

## Common pitfalls

- A PR with logical changes merged without new unit or integration tests; it is unverifiable by definition and voids the mandatory-test rule.
- Tests that reach a real API, network endpoint, live clock, or shared filesystem; they fail offline, leak credentials into CI, and are not isolated.
- Backtest verification that checks only returns while skipping fees, slippage, or position sizing; the silent finance bugs live in exactly those parameters.
- A `feature/*` branch validated against the wrong base, or a `release/*` candidate shipped unverified; branch discipline exists so the tested build is the shipped build.
- A verification cycle closed without a QA Report, so the verdict dies with the session and the release gate has no evidence.
- Sharpe, drawdown, or profit-factor figures copied from the engine output instead of recomputed independently; a check that trusts the code under test checks nothing.

## Definition of done

- [ ] Every new or logically changed behavior in the change set carries its own unit and integration tests.
- [ ] The full suite passes offline: each external API, network call, clock, filesystem boundary, message broker, and third-party service is mocked or containerized.
- [ ] Backtest logic is verified parameter by parameter: returns, fees, slippage, position sizing, Sharpe, drawdown, and profit factor.
- [ ] Verification ran on the designated branch for the stage: `feature/*` against `develop`, `release/*` candidates before production.
- [ ] A QA Report for the cycle is published with an explicit verdict and the evidence behind it.
- [ ] No live credentials, real endpoints, or unmocked third-party calls remain anywhere in the suite.
