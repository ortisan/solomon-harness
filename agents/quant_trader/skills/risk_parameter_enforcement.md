## Risk parameter enforcement


- Position sizing: volatility targeting to a fixed annualized vol (for example `10-15%`), or fractional Kelly capped at `0.5x` Kelly. Never full Kelly.
- Portfolio limits: per-name, per-sector, and gross/net exposure caps. Cap leverage explicitly.
- Drawdown governor: de-risk or halt when realized drawdown breaches the stated limit. The limit is a control, not a statistic you report after the fact.
- Monitor live vs backtest divergence: track realized Sharpe, slippage, and fill quality against backtest assumptions. Flag drift early; a live Sharpe at half the backtested value means the assumptions were wrong.
