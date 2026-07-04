# ML Engineer Definition of Done

The acceptance gate for an ML or DRL deliverable: every item below must hold before a model is called done. The pitfalls list the ways work gets falsely marked complete against this checklist; each one voids the corresponding checkbox.

## Common pitfalls

- A hypothesis card written after training, with thresholds fitted to the achieved number — a bar that chases the result accepts anything, so the first checkbox is void.
- "Cross-validated" ticked on a single train/test split, or a fold mean quoted without its standard deviation — the variance is the evidence that the number is stable.
- The holdout marked as evaluated once when it was reopened after a miss or consulted during model selection — a spent holdout measures tuning luck, not generalization.
- The leakage checklist signed off without a per-feature as-of audit or a shuffled-target test behind it — "no open findings" is then an assertion, not a finding.
- Non-finite-loss guards satisfied by `nan_to_num` instead of a fail-fast assert — masking converts a detectable failure into silent bias.
- Reproducibility claimed with unpinned dependencies or an unrecorded dataset version — a run nobody can regenerate cannot be audited against this list.
- "Beats the baseline" checked with no measured naive baseline on the card — without the floor, the margin cannot be computed.

## Definition of done


- [ ] Model Hypothesis committed with target Sharpe, drawdown limit, profit factor, latency/slippage, dataset/features, and architecture (or the non-trading equivalent with baseline and acceptance threshold).
- [ ] Time-aware or group-aware cross-validation done; mean and std reported across folds.
- [ ] Out-of-sample (and out-of-time) holdout evaluated exactly once and meets the acceptance thresholds.
- [ ] Leakage checklist completed with no open findings.
- [ ] Shape asserts plus divide-by-zero, overflow, and non-finite guards on all critical ops; loss verified finite during training.
- [ ] Seeds fixed, dependencies pinned, dataset version and config recorded; run logged to project memory.
- [ ] Unit and integration tests pass with all external services mocked; backtest-logic tests included.
- [ ] Beats the documented baseline and respects the latency budget.
