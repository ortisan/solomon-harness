---
name: bar-data-backtesting-hygiene
description: Governs what a daily or intraday bar backtest must satisfy before it reaches quant_trader — signal-on-close execute-next-open discipline, causal indicators, survivorship-bias-free point-in-time universes, split and dividend adjustment, realistic market-on-open slippage, regime-spanning walk-forward splits, and minimum sample sizes. Use when building or reviewing a bar-level backtest for a daytrade or swing strategy prior to the validation handoff.
---

# Bar Data Backtesting Hygiene

This skill governs the hygiene of bar-level backtests — the data resolution swing and daytrade strategies live on — so that what reaches quant_trader is worth validating. It sets what the swing_trader must deliver for the backtest to be trustworthy; the verdict itself, the overfitting tests, and the acceptance thresholds belong to quant_trader and are never exercised here.

## Signal on close, execute next open

A signal computed on a bar's close uses information that only exists at that close, so the earliest honest execution is the next bar's open, at the open price plus modeled slippage. Same-bar execution at the close is lookahead unless the strategy explicitly trades the closing auction and models MOC mechanics, and that must be stated on the card. The rule is fractal: a 15-minute strategy signals on the completed 15-minute bar and executes at the next bar's first prints. Intrabar triggers (stop entries) are legitimate only when the fill is modeled at the trigger price plus slippage — never at the bar's favorable extreme.

## Causal indicators only

Every indicator must be computable with data available at signal time. The recurring violations: centered or zero-lag smoothing that uses future bars; normalizations (z-scores, min-max) fit on the full sample, which import the future's mean and variance into the past; and repainting constructs — zigzag legs and swing pivots that are only confirmed N bars after they occur, so a rule may reference a pivot only from N bars later. Limit-fill assumptions are a sibling trap: a resting limit at the bar's low did not fill just because the bar touched it — that assumes owning the low print. Require trade-through (price strictly beyond the limit) for an assumed fill, or apply an explicit fill-probability discount.

## Universe construction and adjustment

- Survivorship bias: backtest on point-in-time universe membership including delisted tickers. Running a long-equity strategy over today's index constituents inflates results materially, because every bankruptcy and delisting has been quietly removed from the sample. The universe file states its as-of dates and its delisting handling (positions in delisted names exit at the delisting price or documented recovery value, not disappear).
- Point-in-time fundamentals: catalyst inputs (earnings dates, surprises, guidance) use as-announced values with announcement timestamps; restated figures are leakage in fundamental clothing. This data arrives from research_analyst already timestamped.
- Adjustment: splits are always adjusted. For returns and indicator continuity, use total-return (dividend-adjusted) series; for price-level rules — stops, pivots, round-number levels — state explicitly which series the rule reads, because a dividend-adjusted historical price is not the price anyone traded. The card records which series feeds which computation.

## Realistic costs for bar-level fills

- Market-on-open fills: liquid large caps, model 5-15 bps of slippage against the official open; small caps and low-ADV names, 25-75 bps or more. Cap modeled participation at 1-5% of the name's average opening-auction volume; above that, an explicit impact model is required, not a bigger constant.
- Intraday stop-market triggers: half the quoted spread plus 5-20 bps by ADV tier, doubled inside the first five minutes of the session per the session-structure skill.
- Commissions and fees at the actual schedule, and borrow costs on shorts. A strategy whose edge disappears when slippage doubles is flagged on the card as cost-fragile before quant_trader sees it.

## Splits, walk-forward, and sample size

- Declare the in-sample/validation/out-of-sample split and the full parameter grid before any results exist; a split declared after inspection is in-sample everywhere.
- Walk-forward: rolling train and test windows, and the windows must span regimes — a sample that is one long bull market validates nothing about drawdown behavior. Include at least one high-volatility or bear segment, and report results per segment, not only pooled.
- Minimum samples: at least 200 out-of-sample trades before a setup's statistics mean anything, across at least two distinct regimes. Every parameter combination searched raises the bar — a 50-point grid demands multiple-testing skepticism, and the grid size is reported to quant_trader, whose deflated-Sharpe and reality-check machinery is the authority on it.

## Common pitfalls

- Executing at the signal bar's close, because the close is part of the information set that generated the signal.
- Full-sample normalization inside features, because it leaks the future's distribution into every historical decision.
- Backtesting today's index members through the past, because the dead names are exactly the ones the strategy would have owned.
- Filling resting limits at bar extremes on a touch, because that awards the best print in the bar to every order.
- A flat slippage constant for every name and time of day, because open-auction and small-cap fills are multiples worse and the edge may live entirely inside that error.
- Declaring splits after seeing results, because it silently converts the holdout into training data.

## Definition of done

- [ ] Execution follows signal-on-close, execute-next-open (or an explicitly modeled MOC/intrabar rule stated on the card).
- [ ] All indicators verified causal; limit fills require trade-through or carry a fill-probability discount.
- [ ] Universe is point-in-time and survivorship-bias-free, with delisting handling stated; adjustment policy per series is recorded.
- [ ] Slippage is modeled per order type, ADV tier, and session phase; participation caps are respected.
- [ ] Splits and the full parameter grid were declared before results; walk-forward spans at least two regimes with at least 200 out-of-sample trades.
- [ ] The backtest package goes to quant_trader for the verdict, and the handoff is logged in project memory.
