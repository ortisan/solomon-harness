## Testing (QA discipline)


- Strict TDD: write the failing test first, then the implementation, then refactor (Red, Green, Refactor).
- Mock all external API calls and market-data services so tests are deterministic and offline. No network in unit tests.
- Test backtest accounting against hand-computed fixtures: a known sequence of fills, costs, and prices must produce an exact, asserted PnL and Sharpe.
- Test the cost and slippage model in isolation, including the large-order impact path.
- Test the leakage guards: a fixture with a deliberate lookahead must fail the leakage assertion.
- Test numerical guards: zero-volatility windows, empty trade sets, single-bar series, and extreme values must not raise or return nan.
