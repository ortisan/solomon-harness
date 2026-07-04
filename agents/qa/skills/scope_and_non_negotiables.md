# QA Specialist Best Practices

Purpose: a concrete, enforceable standard for designing, automating, and reporting tests so every change reaching production is verified, isolated, deterministic, and traceable.

## Scope and non-negotiables


- Write unit and integration tests for all new code or any logical change. No PR is verifiable without them.
- Mock every external API, network call, clock, filesystem boundary, message broker, and third-party service. Tests must pass offline with no live credentials.
- Implement specific tests that verify backtesting logic and parameters: returns, fees, slippage, position sizing, Sharpe, drawdown, profit factor.
- Run verification on the designated branches: validate `feature/*` against `develop`, and verify `release/*` candidates before production.
- Compile and publish a QA Report for each verification cycle.
