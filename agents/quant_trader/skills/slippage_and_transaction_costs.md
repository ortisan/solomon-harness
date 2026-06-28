## Slippage and transaction costs


- Never assume zero or fixed-cents costs. Minimum model: `half_spread + market_impact`.
- Market impact scales with participation. Use a square-root model (`impact ~ daily_volatility * sqrt(order_size / ADV)`) or Almgren-Chriss for scheduled execution. Linear-impact assumptions understate cost for large orders.
- Stress costs: rerun the backtest at `1x`, `2x`, and `3x` the modeled slippage. If the edge disappears at `2x`, it is a cost-sensitive strategy and likely not viable at scale.
- High-turnover strategies are cost-dominated. Report cost as a fraction of gross PnL; above `30-40%` of gross eaten by costs, rethink the design or slow it down.
- Borrow and financing for shorts and leverage are costs, not footnotes. Model hard-to-borrow names explicitly.
