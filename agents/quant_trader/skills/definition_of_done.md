---
name: definition-of-done
description: States the evidence bar a trading strategy must clear before deployment, pairing the pitfalls that fake each checklist item with the deployment checklist itself covering the hypothesis card, net-of-cost thresholds, and reproducibility. Use when deciding whether a strategy or backtest is ready to ship or deploy.
---

# Quant Trader Definition of Done

The evidence bar a strategy must clear before deployment. The pitfalls below are the shortcuts that fake each checklist item; the checklist itself follows.

## Common pitfalls

- A hypothesis card back-filled after the backtest with targets tuned to the observed result; the pre-registration is fiction and the strategy is unfalsifiable.
- Thresholds "met" on gross numbers while the net run misses Sharpe `>= 1.5` OOS or profit factor `>= 1.3`; only net-of-cost results count.
- Deflated Sharpe and PBO computed against a trial count far below the real search; undeclared reruns make the deflation meaningless.
- Walk-forward claimed without purging and embargo, so the out-of-sample curve is quietly in-sample and the checklist item holds in name only.
- The slippage stress skipped or run only at `1x`, letting a cost-fragile edge pass that dies at the first live fill.
- Regime coverage marked done without a crisis period in the sample, so the all-weather claim rests on one benign regime.
- A run called reproducible without pinned seeds, a data-snapshot hash, or a `save_backtest` record; a result that cannot be rerun cannot be audited.

## Definition of done


- [ ] Model Hypothesis card committed with every field as a concrete number (target Sharpe, DD limit, profit factor, latency/slippage, dataset/features, architecture).
- [ ] Backtest uses point-in-time, survivorship-free, corporate-action-adjusted data; fills on the next bar; costs and slippage in every fill.
- [ ] Net (post-cost) results meet the stated thresholds: Sharpe `>= 1.5` OOS, max DD within limit, profit factor `>= 1.3`.
- [ ] Out-of-sample evaluated once; walk-forward or CPCV with purging and embargo used; no leakage path remains.
- [ ] Deflated Sharpe and PBO reported and acceptable; multiple-testing accounted for.
- [ ] Per-regime metrics reported, including at least one crisis period; parameter stability checked.
- [ ] Slippage stress at `2x` and `3x` does not erase the edge; cost share of gross PnL within budget.
- [ ] Risk controls in place: vol targeting or capped fractional Kelly, exposure/gearing caps, drawdown governor.
- [ ] Tests written first; external services mocked; accounting, costs, leakage guards, and numerical edge cases all covered and green.
- [ ] Run is reproducible (pinned seeds, data snapshot, code hash) and persisted to memory via `save_backtest`.
