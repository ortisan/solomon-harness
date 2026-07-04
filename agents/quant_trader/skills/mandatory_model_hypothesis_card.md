# Mandatory Model Hypothesis Card

Before writing strategy code, commit a hypothesis card that states — as numbers, not adjectives — the target Sharpe, drawdown limit, profit factor, latency and slippage constraints, dataset and features, and the model architecture; a strategy without a card is not started, and a card without numbers is not a card. The card is a pre-registration: it makes the strategy falsifiable before the backtest can flatter it.

## The fields and their default bars

- Target Sharpe: net of costs, out-of-sample, annualized. Default bar >= 1.5. Below 1.0 net OOS, do not deploy. The number that must clear the bar is the deflated Sharpe (see the overfitting skill), not the raw one.
- Max drawdown limit: peak-to-trough on the net equity curve. Default hard cap 20%; the kill switch trips at 1.25x the backtested max drawdown (see the risk skill).
- Profit factor: gross profit divided by gross loss. Default floor 1.3. Below 1.1 the edge is indistinguishable from noise at realistic trade counts.
- Latency and slippage constraints: the latency budget (for example intraday < 50 ms order-to-fill; EOD strategies < 1 bar) and the assumed slippage model with its value (half-spread plus square-root impact, stated in bps or ticks per side).
- Dataset and features: instruments, date range, bar frequency, data vendor, point-in-time corrections (survivorship-free universe, corporate-action adjusted, first-reported fundamentals), and the exact feature list with lookback windows.
- Network or model architecture: rules-based logic, a named ML model (gradient boosting, linear), or a DRL setup (state, action, reward, network), with hyperparameters and the search space declared up front. The declared search space is the trial count the final Sharpe must be deflated by.

Also record: rebalance frequency, target volatility, expected turnover, capacity (the notional at which impact consumes the edge, from the cost skill), and the economic rationale — who is on the other side of the trade and why their behavior persists. If you cannot explain why the edge exists, treat any positive result as overfit until proven otherwise.

## Worked example

```yaml
name: tsmom-liquid-futures
thesis: >
  12-month time-series momentum, skipping the most recent month, persists in
  liquid futures because institutional rebalancing and risk-parity flows adjust
  over weeks, not days.
targets:
  sharpe_net_oos: ">= 1.2 deflated (trial count declared below)"
  max_drawdown: "15% hard cap; kill at 1.25x backtested max DD (backtest: 11%)"
  profit_factor: ">= 1.4"
constraints:
  latency_budget: "EOD strategy; signal at close t, execution at open t+1"
  slippage_model: "half-spread + sqrt impact (Y=1.0); default 0.5 tick/side; stressed 2x, 3x"
  cost_share_budget: "<= 25% of gross PnL"
data:
  instruments: "24 CME/ICE futures: equity index, rates, FX, commodities"
  range: "2004-01-02 .. 2024-12-31; OOS 2021-01-04 .. 2024-12-31, single touch"
  frequency: "daily bars; point-in-time roll schedule; back-adjusted for analysis only"
  features: "returns over 21/63/126/252d lookbacks; 60d EWMA vol for sizing"
model:
  architecture: "rules-based: sign of 252d return skipping last 21d; vol-targeted sizing"
  search_space: "lookback in {126, 252} x skip in {0, 21} = 4 trials, all logged"
risk:
  sizing: "vol target 12% annualized; per-contract cap; gross exposure cap 150%"
  turnover_expected: "~400% annualized"
  capacity: "~200M USD at 10% ADV participation before impact halves the edge"
falsification: >
  Reject if net OOS Sharpe < 1.0, or PBO >= 0.10, or the 2x-slippage run erases
  the edge, or PnL is concentrated in a single volatility regime.
```

## Process rules

- The card is committed, and saved to project memory via `save_decision`, before the first line of strategy code; every backtest attaches to it via `save_backtest`, which keeps the trial count honest.
- Amendments are allowed but logged: changing a target after seeing results is a new hypothesis, and any OOS window already seen is burnt for the amended card.
- The falsification block is mandatory: state in advance exactly which result kills the idea. A card that cannot fail is marketing.
- Review gate: a second reader (or the reviewing agent) checks the card for numbers-not-adjectives, a declared search space, and an economic rationale before work starts.

## Common pitfalls

- Adjectives where numbers belong: "low drawdown", "fast execution", "robust features".
- A search space declared as 4 trials that becomes 400 in the notebook; the deflation is then fiction — log every trial.
- No latency budget, so an intraday signal gets validated with EOD fills.
- No capacity figure, so the strategy is "great" at a notional it can never absorb.
- An economic rationale written after the backtest to fit the result; the rationale is a prior, not a caption.
- Amending the drawdown cap upward mid-drawdown; the card is a control, not a diary.

## Definition of done

- [ ] Card exists before strategy code, with every field a concrete number: target Sharpe (net, OOS, deflated), max drawdown cap, profit factor floor, latency budget, slippage model and value.
- [ ] Dataset block pins instruments, date range, frequency, vendor, point-in-time corrections, and the exact feature list with lookbacks.
- [ ] Architecture and the full hyperparameter search space declared; every subsequent trial logged against the card.
- [ ] Rebalance frequency, target volatility, expected turnover, capacity, and economic rationale recorded.
- [ ] Falsification criteria stated in advance and mechanically checkable.
- [ ] Card saved via `save_decision`; backtests attached via `save_backtest`; amendments logged together with what they invalidate.
