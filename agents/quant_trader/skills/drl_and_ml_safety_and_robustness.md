## DRL and ML safety and robustness


- Validate tensor shapes before every critical operation (matmul, reshape, batched env steps). Assert expected shapes rather than trusting broadcasting.
- Guard against division-by-zero in returns, Sharpe, drawdown, and normalization. Use an epsilon floor or explicit branch; never let a zero denominator silently produce inf/nan.
- Guard against float overflow in compounding, exponentials, and reward accumulation. Clip rewards and log-returns; prefer log-space for products.
- Zero data leakage in feature engineering: fit scalers, PCA, and feature selection on the training fold only, then transform validation and test.
- For DRL: define the reward to match the real objective (risk-adjusted return net of costs, not raw PnL). Include transaction costs in the environment reward, or the agent learns to overtrade.
- Stationarity: prefer returns or fractionally differentiated series over raw prices; stationarize features and confirm with a unit-root test.
- Consider triple-barrier labeling and meta-labeling for supervised entries; size positions separately from the directional signal.
