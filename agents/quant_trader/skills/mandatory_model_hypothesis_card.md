## Mandatory Model Hypothesis card


Before writing strategy code, commit a hypothesis card. A strategy without one is not started. State each field with a number, not an adjective:

- Target Sharpe: net of costs, out-of-sample, annualized. Default bar `>= 1.5`. Below `1.0` net OOS, do not deploy.
- Max drawdown limit: peak-to-trough on the equity curve. Default hard cap `20%`; trip a kill switch at `1.25x` the backtested max DD.
- Profit factor: gross profit / gross loss. Default floor `1.3`. Below `1.1`, the edge is noise.
- Latency and slippage constraints: state the latency budget (for example intraday `< 50 ms` order-to-fill, EOD strategies `< 1 bar`) and the assumed slippage model and value (for example `half-spread + impact`, in bps).
- Dataset and features: instruments, date range, bar frequency, data vendor, point-in-time corrections (survivorship-free universe, corporate-action adjusted), and the exact feature list with lookback windows.
- Network or model architecture: rules-based logic, a named ML model (gradient boosting, linear, etc.), or a DRL setup (state, action, reward, network). State hyperparameters and the search space.

Also record: rebalance frequency, target volatility, expected turnover, capacity (notional the strategy absorbs before impact kills the edge), and the economic rationale. If you cannot explain why the edge exists, treat the result as overfit until proven otherwise.
