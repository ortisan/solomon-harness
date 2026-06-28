## Definition of done


- [ ] Model Hypothesis committed with target Sharpe, drawdown limit, profit factor, latency/slippage, dataset/features, and architecture (or the non-trading equivalent with baseline and acceptance threshold).
- [ ] Time-aware or group-aware cross-validation done; mean and std reported across folds.
- [ ] Out-of-sample (and out-of-time) holdout evaluated exactly once and meets the acceptance thresholds.
- [ ] Leakage checklist completed with no open findings.
- [ ] Shape asserts plus divide-by-zero, overflow, and non-finite guards on all critical ops; loss verified finite during training.
- [ ] Seeds fixed, dependencies pinned, dataset version and config recorded; run logged to project memory.
- [ ] Unit and integration tests pass with all external services mocked; backtest-logic tests included.
- [ ] Beats the documented baseline and respects the latency budget.
