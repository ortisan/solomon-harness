## Definition of done


- [ ] Model Hypothesis card committed with every field as a concrete number (target Sharpe, DD limit, profit factor, latency/slippage, dataset/features, architecture).
- [ ] Backtest uses point-in-time, survivorship-free, corporate-action-adjusted data; fills on the next bar; costs and slippage in every fill.
- [ ] Net (post-cost) results meet the stated thresholds: Sharpe `>= 1.5` OOS, max DD within limit, profit factor `>= 1.3`.
- [ ] Out-of-sample evaluated once; walk-forward or CPCV with purging and embargo used; no leakage path remains.
- [ ] Deflated Sharpe and PBO reported and acceptable; multiple-testing accounted for.
- [ ] Per-regime metrics reported, including at least one crisis period; parameter stability checked.
- [ ] Slippage stress at `2x` and `3x` does not erase the edge; cost share of gross PnL within budget.
- [ ] Risk controls in place: vol targeting or capped fractional Kelly, exposure/leverage caps, drawdown governor.
- [ ] Tests written first; external services mocked; accounting, costs, leakage guards, and numerical edge cases all covered and green.
- [ ] Run is reproducible (pinned seeds, data snapshot, code hash) and persisted to memory via `save_backtest`.
