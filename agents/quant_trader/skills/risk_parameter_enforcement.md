---
name: risk-parameter-enforcement
description: Fixes the house risk numbers enforced in code, not reported after the fact: position-sizing formulas, drawdown governors, VaR/ES limits, position caps, and kill-switch conditions that flatten the book. Use when implementing or reviewing position sizing, exposure limits, or automated risk controls.
---

# Risk Parameter Enforcement

Risk limits are controls enforced in code before and during trading, not statistics reported after the fact, and this skill fixes the house numbers: sizing formulas, drawdown governors, VaR/ES limits, position caps, and the kill-switch conditions that flatten the book. A limit that cannot halt trading automatically is a wish.

## Position sizing formulas

- Fixed-fractional: risk a fixed fraction of equity per trade, defined by the stop distance — `size = (equity * f) / stop_distance`, with f = 0.5-1% per trade for a single strategy. Simple, robust, the default for entries with hard stops.
- Volatility targeting: scale the book to a target annualized volatility, typically 10-15%: `weight_t = target_vol / realized_vol_t`, with realized vol from an EWMA (span 20-60 days) and the scaling capped (for example at 2x) so a quiet tape cannot balloon exposure right before the regime breaks. Vol targeting also stabilizes the Sharpe estimate across regimes.
- Kelly: full Kelly maximizes log growth in theory and produces intolerable drawdowns under estimation error in practice, because the optimum depends on moments you cannot measure precisely. Cap at 0.25-0.5x the estimated Kelly fraction; never full Kelly. Half-Kelly keeps roughly 75% of the growth rate at half the variance.

Whatever the formula, sizing is computed by the risk layer, not inside the signal. The signal proposes direction and conviction; the risk layer disposes.

## Drawdown limits and the governor

- State a hard max-drawdown limit on the hypothesis card; default cap 20% peak-to-trough on the net equity curve.
- Governor schedule, enforced in code: at 50% of the limit (10% DD under the default), cut gross exposure by half; at 75% (15%), cut to a quarter; at the limit, flatten and halt. Restart requires human sign-off and a written post-mortem.
- Calibrate a kill trip against the backtest as well: trip at 1.25x the backtested max drawdown even if still under the hard cap, because exceeding what the model thought possible means the model is wrong, not unlucky.

## VaR and Expected Shortfall

- Per-trade: the loss to the stop (or a 2-sigma adverse move where no stop exists) must not exceed the fixed-fractional f above.
- Portfolio: compute 1-day VaR at 95% and 99% by historical simulation over a 250-500 day window, EWMA-weighted so the estimate reacts to the current regime. House limit: 95% 1-day VaR <= 2% of NAV.
- Prefer Expected Shortfall at 97.5% (the FRTB convention) as the binding tail limit: ES is subadditive and measures the tail beyond the VaR threshold instead of stopping at it. House limit: 97.5% 1-day ES <= 3% of NAV.
- Backtest the risk model itself: a 95% VaR should be breached on about 5% of days. Run a Kupiec proportion-of-failures test; persistent over- or under-breaching means the window or weighting is wrong.

## Position and exposure caps

- Per-name cap: 5-10% of NAV. Per-sector or per-cluster cap: 20-25%.
- Gross exposure cap stated explicitly (for example 200% for a market-neutral book, 100% for long-only) and a net exposure band (for example +/-10% for market-neutral).
- Gearing and margin: cap borrowed capital explicitly and hold a margin-utilization ceiling (for example <= 50% of available margin) so a volatility spike cannot force liquidation at the worst prices.
- Cap by correlation cluster, not just by name: three tickers expressing the same macro trade pass per-name checks while being one concentrated position. Cluster on rolling correlation or factor loadings and cap the cluster.

## Kill-switch conditions

Flatten and halt, automatically, on any of:

- Drawdown at the hard limit, or at 1.25x the backtested max drawdown.
- Live-vs-backtest divergence: rolling realized Sharpe below half the backtested value over a meaningful window, or realized slippage above 2x the modeled value, or fill quality persistently worse than assumed.
- Data integrity: stale feed (no update within the expected interval), NaN inputs reaching the signal, or a position reconciliation break between the internal book and the broker.
- Operational: order-reject rate spikes, repeated retry storms, or the strategy requesting sizes above its caps — a bug signature, not a market view.

Every trip is logged with cause and full state and recorded to project memory; restart is a human decision, never automatic.

## Common pitfalls

- Full Kelly, or "Kelly-inspired" sizing with no cap; estimation error turns it into ruin dynamics.
- Vol targeting without a scaling cap, so low-volatility regimes quietly build maximum exposure at the worst time.
- Limits that live in a config file the execution path never reads; enforcement must sit between signal and order submission.
- VaR as the only tail measure; it says nothing about the size of losses beyond the threshold.
- Per-name caps without correlation clustering; ten 5% positions on one macro bet is a 50% position.
- Restarting after a kill-switch trip without a post-mortem; the trip was information about the model.

## Definition of done

- [ ] Sizing formula chosen and documented (fixed-fractional f = 0.5-1%, vol target 10-15% with a scaling cap, or Kelly capped at 0.25-0.5x), computed in the risk layer.
- [ ] Hard drawdown cap (default 20%) with a coded governor schedule (half gross at 50% of the limit, quarter at 75%, flat at the limit) plus the 1.25x-backtest kill trip.
- [ ] 95%/99% 1-day VaR and 97.5% ES computed daily; limits (VaR95 <= 2% NAV, ES97.5 <= 3% NAV) enforced pre-trade; breach counts monitored with a Kupiec test.
- [ ] Per-name, per-cluster, gross, net, and gearing caps enforced in code, with a margin-utilization ceiling.
- [ ] Kill-switch conditions implemented (drawdown, divergence, data integrity, operational) with logging, memory persistence, and human-gated restart.
- [ ] Live-vs-backtest monitors running: realized Sharpe, slippage, and fill quality tracked against the modeled assumptions.
