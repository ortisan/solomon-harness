---
name: long-horizon-backtest-hygiene
description: Governs the data and methodology requirements the long_run_strategist writes into every hypothesis card before quant_trader runs a backtest — survivorship-bias-free universes, point-in-time fundamentals, delistings and corporate actions, regime coverage, and low-frequency walk-forward design. Use when specifying acceptance criteria for a backtest, reviewing a dataset for look-ahead or survivorship defects, or setting the walk-forward and holdout methodology.
---

# Long-Horizon Backtest Hygiene

This skill governs the data and methodology requirements the long_run_strategist writes into every hypothesis card before quant_trader runs a backtest: survivorship-bias-free universes, point-in-time data, delistings and corporate actions, regime coverage, and low-frequency walk-forward design. The stance: at long horizons the scarce resource is independent observations, and the common killers are quiet data defects rather than exotic statistics — so the strategist specifies the hygiene bar up front, and a backtest that fails the bar is not evidence, no matter what its Sharpe says.

## Survivorship bias and universe construction

The universe at each historical date must be the universe as it existed on that date, including every company that later went bankrupt, was acquired, or was dropped from the index. Backtesting on today's constituents quietly conditions on survival and success, and the inflation is material — famously large for strategies tilted toward distressed or small names, and directionally flattering almost everywhere. Requirements: use a point-in-time universe or index-membership history (membership as of each rebalance date, not current membership); include dead tickers with their full price history; and treat ticker reuse (a dead company's symbol reassigned to a new listing) as a data hazard to be checked, not assumed away. If a point-in-time universe is unavailable for part of the sample, the card must say so and the affected period must be labeled as weaker evidence.

## Point-in-time fundamentals

A fundamental datum may only be used from the moment it was publicly knowable. Annual and quarterly figures are reported with a lag, and later restatements overwrite history in many databases, so a naive join of fundamentals to prices commits look-ahead twice: it uses numbers before their release date and it uses corrected numbers instead of the originally reported ones. Requirements: prefer a point-in-time fundamentals vendor snapshot where available; otherwise lag fundamentals conservatively (at least three months for annual figures, and state the lag on the card); and never recompute a historical signal with restated data. The same discipline applies to macro series, which are heavily revised: use first-release vintages or lag accordingly.

## Delistings and corporate actions

Delisting is where losing positions go to hide. Shumway (1997) documented that standard databases often omit or misstate delisting returns, and that ignoring them overstates performance, most severely for strategies that hold deteriorating names — a short side, a value screen, a small-cap tilt. Requirements: include delisting returns explicitly, and where the true delisting return is unknown, apply a conservative assumption (a substantial loss for performance-related delistings) rather than dropping the observation. Corporate actions must be handled through total-return series: dividends reinvested, splits adjusted, spin-offs and mergers tracked so that value neither appears from nor vanishes into an unadjusted price break. Futures-based designs have the analogous requirement: a stated roll methodology and a back-adjusted continuous series whose construction is documented on the card.

## Regime coverage

A long-horizon strategy holds through regimes, so its evidence must span regimes. The minimum bar: cover multiple decades where the data exists, and demand that the sample include materially different rate environments, at least one inflation shock, several volatility regimes, and both secular bull and bear phases for the traded assets. A strategy tested only on 2009-2021 has seen one regime — falling rates, low inflation, buy-the-dip equities — and its statistics are conditional on that regime, whatever their nominal significance. Where long history genuinely does not exist (a new asset class, a young market), the card must say so explicitly and compensate: test the economic logic on older analogue assets where defensible, and shrink the confidence and the sizing accordingly. Reporting per-regime performance, not just full-sample averages, is part of the validation request to quant_trader.

## Walk-forward at low frequency

With monthly rebalancing and a multi-decade sample, the backtest contains only a few hundred decision points and far fewer independent ones — serial correlation and overlapping holding periods shrink the effective sample further. Methodology requirements that follow: use expanding-window or long-rolling-window walk-forward validation with refit dates far apart, matching how the strategy would actually be re-estimated; keep a true holdout period untouched until the design is final, and spend it exactly once; judge parameter stability across walk-forward folds as a first-class result — a parameter that lurches from fold to fold is a data-mining symptom even when the average performance looks good; and require uncertainty estimates that respect the dependence structure, for example block-bootstrap confidence intervals rather than i.i.d. assumptions, stated qualitatively on the card. Multiple-testing honesty is part of hygiene: the card records how many variants were tried, because the tenth variant's p-value does not mean what the first one's did.

## Common pitfalls

- Backtesting on the current index membership, because conditioning on survivors inflates returns and hides exactly the failures the strategy would have held.
- Joining fundamentals or macro series at their calendar date rather than their release date, because look-ahead through reporting lags and revisions fabricates edge.
- Dropping delisted names or omitting delisting returns, because the losses of the disappeared are real losses (Shumway 1997).
- Using price series instead of total-return series, because ignoring dividends misstates long-horizon results badly for high-yield assets.
- Accepting a 2009-2021-only sample as sufficient evidence, because one regime is one observation of regime risk.
- Burning the holdout period repeatedly during design iteration, because a holdout consulted twice is in-sample.
- Hiding the number of variants tried, because undisclosed multiple testing invalidates the reported significance.

## Definition of done

- [ ] The hypothesis card specifies a point-in-time universe with dead companies, index membership as-of each date, and a ticker-reuse check.
- [ ] Fundamentals and macro inputs are point-in-time or conservatively lagged, with the lag stated; restated data is never used for historical signals.
- [ ] Delisting returns are included (with a stated conservative assumption where unknown) and all series are total-return with documented corporate-action and roll handling.
- [ ] Regime coverage spans multiple decades where data exists, and per-regime results are part of the requested validation output; data limitations are declared, not smoothed over.
- [ ] Walk-forward design (window scheme, refit frequency, single-use holdout, parameter-stability report, dependence-aware error bars) is written on the card.
- [ ] The number of variants tried is recorded, and the full hygiene specification is handed to quant_trader as acceptance criteria for the backtest.
