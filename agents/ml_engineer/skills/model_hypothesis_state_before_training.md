## Model Hypothesis (state before training)


Write this down first. For trading and DRL models it is mandatory and must include:

- Target Sharpe ratio (annualized). Default acceptance bar: out-of-sample Sharpe >= 1.5; reject anything below 1.0.
- Maximum drawdown limit, e.g. <= 20% on the OOS window. State the figure and enforce it.
- Profit factor target: >= 1.3 OOS (gross profit / gross loss). Below 1.0 is a losing model, discard it.
- Latency and slippage constraints: inference latency budget (e.g. < 50 ms p99) and the slippage/transaction-cost model assumed (e.g. 2 bps per side plus spread). Backtests without costs are invalid.
- Dataset and features: exact source, date range, sampling frequency, and the feature list with how each is computed.
- Network or model architecture: layer sizes, activations, loss, optimizer, and the action/observation spaces for RL.

For non-trading models, keep the equivalent: primary metric and acceptance threshold, the baseline you must beat, latency budget, dataset/feature spec, and architecture. A model that does not beat a documented naive baseline (persistence, mean, majority class) is not shippable.
