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
