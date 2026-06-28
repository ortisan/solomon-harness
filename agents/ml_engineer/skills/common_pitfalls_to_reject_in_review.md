## Common pitfalls to reject in review


- Random K-fold on time-ordered data.
- Scaler or encoder fit before the split.
- Backtest Sharpe reported without transaction costs or slippage.
- A single train/test split presented as if it were cross-validation.
- Reusing the holdout for model selection.
- Silent `NaN`/`inf` in loss masked by `nan_to_num` instead of fixing the cause.
- Unseeded runs whose numbers cannot be reproduced.
- Metrics quoted without fold variance or a baseline comparison.
