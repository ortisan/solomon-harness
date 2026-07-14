---
name: common-pitfalls
description: Lists the review reject list for ML and DRL deliverables, covering validation, leakage, numerical, and reporting defects that invalidate a result. Use when reviewing an ML or DRL deliverable for validation soundness, leakage safety, numerical stability, or reporting honesty before approval.
---

# ML Engineer Common Pitfalls

The review reject list for ML and DRL deliverables: the validation, leakage, numerical, and reporting defects that invalidate a result. Each bullet names a failure a reviewer must block, and the Definition of done below is the gate proving a deliverable avoided every one of them.

## Common pitfalls

Reject any of these in review:

- Random K-fold on time-ordered data.
- Scaler or encoder fit before the split.
- Backtest Sharpe reported without transaction costs or slippage.
- A single train/test split presented as if it were cross-validation.
- Reusing the holdout for model selection.
- Silent `NaN`/`inf` in loss masked by `nan_to_num` instead of fixing the cause.
- Unseeded runs whose numbers cannot be reproduced.
- Metrics quoted without fold variance or a baseline comparison.

## Definition of done

- [ ] Time-ordered data was validated walk-forward (`TimeSeriesSplit` or purged walk-forward with embargo), never with random K-fold.
- [ ] Every scaler, encoder, and other learned transform was fit inside the training fold via a pipeline, not before the split.
- [ ] Any quoted backtest Sharpe is net of the transaction-cost and slippage assumptions declared on the hypothesis card.
- [ ] Model selection ran on cross-validation folds or a validation split; the out-of-sample holdout was opened exactly once for the final number.
- [ ] Loss and inputs carry fail-fast finiteness checks, with no `nan_to_num` masking anywhere on the training path.
- [ ] Seeds are fixed and recorded, so every reported number reruns to the same value.
- [ ] Each headline metric is reported with its fold mean and standard deviation next to a measured baseline.
