---
name: backtesting-verification-specific-because-finance-bugs-are-silent
description: Governs how QA proves a trading backtest is correct rather than merely green, covering look-ahead bias, cost realism, walk-forward validation, reproducibility, and PnL invariant checks. Use when reviewing or writing backtest tests, strategy validation, or a quant_trader handoff at /solomon-review.
---

# Backtesting Verification (Specific, Because Finance Bugs Are Silent)

This skill is the QA-to-quant_trader verification seam: how QA proves a backtest is correct, not merely green. A trading backtest is the rare program whose most dangerous defects produce no error, no crash, and no failing assertion. It emits a smooth, plausible, profitable equity curve regardless of whether the logic is sound, so the usual "tests pass, ship it" gate is blind here. At the /solomon-review stage QA treats the backtest engine as code under test and demands evidence for every claim the curve makes: that signals saw only past data, that costs were charged, that the result survives out-of-sample, and that the same inputs reproduce the same PnL to the cent. Risk scoring and FMEA detectability for these silent failure modes are owned by `test_planning_and_traceability`; a backtest's low detectability is exactly what should push its FMEA RPN high. Deterministic-test mechanics (seed pinning, frozen clock) are owned by `test_design_rules`. This file owns the financial invariants those mechanics protect.

## Why finance bugs are silent

A web bug throws a 500 or renders the wrong page; a human sees it. A backtest bug shifts a number inside a 10-year compounded curve, and the curve still looks like a curve. A one-bar look-ahead leak typically *improves* the reported Sharpe, so the bug masquerades as alpha and survives review precisely because it makes the result more attractive. There is no oracle in the output itself. The oracle has to come from independent reconstruction: recompute the metric a second way, replay the data with the future masked, or charge costs and prove the PnL moved. Never accept "the backtest ran and made money" as a pass. The pass criterion is "an independent check failed to find a leak, a missing cost, or an irreproducible result."

## Look-ahead / peeking bias

Assert that any decision at bar `t` consumes only data with timestamp `<= t`. The two highest-yield checks:

- **Shift test.** Take a feature used by the signal, shift its input one bar into the future, rerun, and prove the result changes materially. If shifting the future in does nothing, the engine was already peeking. If the live result already matches the future-shifted result, you have found a leak.
- **Causal replay.** Drive the engine bar-by-bar through a feed that physically cannot return rows with timestamp `> t` (slice the frame, do not pass the whole DataFrame to a vectorized indicator that silently centers its window). Centered rolling stats (`pandas.Series.rolling(window).mean()` with `center=True`), `ffill` across the decision boundary, and resampling that labels a bar by its close while exposing the close at the open are the classic leak sources. Use point-in-time data so the value the test sees is the value that existed at `t`, not the latest restatement.

## Train/test leakage and survivorship bias

Two dataset-level leaks that no per-bar assertion catches:

- **Split leakage.** For model-backed strategies, scalers and feature-selection fit on the full series before the split leak test-window statistics into training. Assert the preprocessing pipeline was `fit` only on the training window (`sklearn` transformers fit inside the walk-forward fold, never before it), and that train and test windows do not overlap. For overlapping-label problems use purged, embargoed K-fold (López de Prado) and assert the embargo gap is non-zero.
- **Survivorship bias.** A universe built from *today's* listed symbols silently deletes every company that delisted, merged, or went bankrupt, which inflates returns. Assert the symbol universe is reconstructed as-of each rebalance date from a point-in-time membership table, and that delisted tickers carry their final return (often -100 percent), not a gap. Reject fundamentals that are forward-filled or restated rather than as-first-reported.

## Cost realism

A strategy that only profits at zero cost is not a strategy. Assert that slippage, commission/transaction cost, and funding/borrow are applied and non-zero on every fill, and that fill assumptions are realistic (no fills at the bar low, no fills beyond available volume, signal-to-fill latency of at least one bar for daily bars). The canonical check is a zero-cost vs with-cost run that proves net return dropped by the expected amount, and that the strategy's edge does not vanish once realistic costs are charged. Charge borrow on shorts and funding on leveraged/perpetual positions; a long-short book that ignores borrow is reporting phantom return.

## Walk-forward / out-of-sample validation

Reject a single in-sample fit. Require anchored or rolling walk-forward: optimize on window `n`, evaluate on the untouched window `n+1`, roll, and report the stitched out-of-sample curve, never the in-sample one. Assert the out-of-sample window was never touched during parameter selection and that the count of optimized parameters is small relative to the out-of-sample observations. Treat a large in-sample / out-of-sample performance gap as an overfitting flag and escalate it to quant_trader; the deflated Sharpe ratio and the probability of backtest overfitting (PBO) are the quant's metrics, but QA verifies the split that makes them honest.

## Reproducibility

Same inputs must yield identical PnL. Pin the RNG seed (mechanics in `test_design_rules`), pin the data snapshot to an immutable hash, and use a deterministic clock rather than `datetime.now()`. Two runs over the same seed and snapshot must produce a byte-identical result file; snapshot the key metrics and fail on drift. Compute money in `Decimal` or integer minor units and reconcile with an explicit tolerance, never naive float equality. A backtest that is not reproducible cannot be debugged, audited, or trusted.

## Invariants to assert

Independent reconstruction beats trusting the engine's own numbers:

- **PnL accounting identity.** Final equity must equal starting capital plus the cumulative sum of per-trade PnL net of costs. Any residual is a leak or a double-count.
- **Position and exposure limits.** Gross/net exposure, per-name position, and leverage never breach the configured cap on any bar.
- **Metric cross-check.** Recompute Sharpe and max drawdown from the equity curve in the test and assert they match the engine output within tolerance. Verify Sharpe annualization uses the correct periods-per-year factor and guard division-by-zero (flat-equity Sharpe, zero-trade profit factor) and inf/NaN propagation in the curve.

## Worked example: no look-ahead and costs were charged

```python
import numpy as np
import pandas as pd
import pytest

def test_signal_uses_only_past_bars_and_costs_reduce_pnl():
    rng = np.random.default_rng(42)               # pinned seed (see test_design_rules)
    n = 500
    close = pd.Series(100 + np.cumsum(rng.normal(0, 1, n)),
                      index=pd.date_range("2020-01-01", periods=n, freq="D"))

    # No look-ahead: signal at bar t is decided from a feature shifted by 1 bar,
    # so it can only see data with timestamp <= t-1.
    sma = close.rolling(20).mean()
    signal = (close.shift(1) > sma.shift(1)).astype(int)  # decided on past bars only

    # Guard: the decision for bar t must not depend on close[t]. Recomputing the
    # signal with the future masked must leave today's decision unchanged.
    masked = close.copy()
    masked.iloc[-1] = np.nan                              # hide the most recent close
    sma_masked = masked.rolling(20).mean()
    signal_masked = (masked.shift(1) > sma_masked.shift(1)).astype(int)
    assert signal.iloc[-1] == signal_masked.iloc[-1], "signal peeked at the current bar"

    ret = close.pct_change().fillna(0.0)
    gross_pnl = float((signal * ret).sum())

    # Costs: charge commission + slippage on every position change. Net must be lower.
    cost_per_turn = 0.0010                                 # 10 bps round-trip, non-zero
    turns = signal.diff().abs().fillna(0.0)
    costs = float((turns * cost_per_turn).sum())
    net_pnl = gross_pnl - costs

    assert costs > 0, "no transaction costs were applied"
    assert net_pnl < gross_pnl, "net PnL must be below gross once costs are charged"
```

The first block proves the signal is causal by masking the current bar and showing the decision is invariant. The second proves costs are live and strictly reduce PnL. Both failures are the silent kind a green run would otherwise hide.

## Common pitfalls

- Accepting a profitable equity curve as proof of correctness with no independent reconstruction behind any number.
- A vectorized indicator (centered rolling window, `ffill` across the decision boundary, resample mislabeling) that quietly reads the current bar; never proven causal by a shift or mask test.
- Costs configured but defaulted to zero, or applied only on entry, so the curve is gross dressed as net.
- A universe drawn from today's survivors, deleting every delisted name and inflating returns.
- Scalers or feature selection fit on the full series before the train/test split, leaking test-window statistics into training.
- Reporting the in-sample optimized curve as the result instead of the stitched out-of-sample walk-forward.
- Money compared with float `==`; a 1e-9 residual masks a real accounting leak or passes a real one.
- A backtest that is not reproducible run-to-run, so a metric drift cannot be distinguished from a code change.

## Definition of done

- [ ] A shift or mask test proves the signal at bar `t` uses only data `<= t`; centered windows and cross-boundary `ffill` are ruled out.
- [ ] Point-in-time data is used; the symbol universe is reconstructed as-of each rebalance date and delisted names retain their final return (no survivorship bias).
- [ ] Preprocessing is fit only inside each walk-forward fold; train/test windows do not overlap, and overlapping-label problems use a purged, embargoed split.
- [ ] Slippage, commission, and funding/borrow are asserted non-zero on every fill; a zero-cost vs with-cost run proves net return dropped as expected and the edge does not depend on zero cost.
- [ ] Results are reported on an untouched out-of-sample / walk-forward window, not a single in-sample fit; a large in/out gap is escalated to quant_trader.
- [ ] Pinned seed, pinned data-snapshot hash, and deterministic clock yield byte-identical PnL across two runs; money is compared in `Decimal`/minor units within an explicit tolerance.
- [ ] The PnL accounting identity, position/exposure limits, and an independent Sharpe/max-drawdown recomputation all pass against the engine output; division-by-zero and inf/NaN paths are guarded.
- [ ] Detectability of each silent failure mode is fed back into the FMEA risk score in `test_planning_and_traceability`.
