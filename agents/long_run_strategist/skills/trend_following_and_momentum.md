---
name: trend-following-and-momentum
description: Governs how the long_run_strategist designs trend-following and momentum signals — choosing between time-series and cross-sectional constructions, selecting lookbacks from the 3-to-12-month evidence band, scaling by volatility, and anticipating whipsaw and momentum-crash regimes. Use when specifying a trend or momentum signal's construction, lookback ensemble, and volatility scaling, or when assessing a design's exposure to whipsaw and crash risk.
---

# Trend Following and Momentum

This skill governs how the long_run_strategist designs trend-following and momentum signals for long-horizon portfolios: choosing between time-series and cross-sectional constructions, selecting lookbacks, scaling by volatility, and anticipating the regimes in which trend loses money. The stance: momentum is among the best-documented return premia in the empirical literature, but it is crowded and crash-prone, so it must be diversified across assets and speeds, sized by risk rather than conviction, and shipped as a hypothesis card for quant_trader to validate — never as a self-graded result.

## Time-series versus cross-sectional momentum

Time-series (absolute) momentum trades the sign of an asset's own excess return over the lookback window: long when past excess return is positive, short or flat when negative. Moskowitz, Ooi, and Pedersen ("Time Series Momentum", Journal of Financial Economics, 2012) documented the effect across dozens of liquid futures and forwards in equities, bonds, currencies, and commodities, and Hurst, Ooi, and Pedersen ("A Century of Evidence on Trend-Following Investing", AQR) report qualitatively consistent performance across roughly a century of data. The payoff profile is convex: because the rule cuts losers and rides winners, it has historically produced gains in prolonged bear markets, the so-called crisis-alpha property. Treat that property as a statistical tendency with named sources, not a guarantee.

Cross-sectional (relative) momentum ranks assets against their peers and goes long recent winners and short (or underweight) recent losers. Jegadeesh and Titman (1993) established it in US equities; Asness, Moskowitz, and Pedersen ("Value and Momentum Everywhere", Journal of Finance, 2013) found it jointly with value across markets and asset classes. Cross-sectional momentum is roughly market-neutral by construction, which removes the directional bet but exposes the short side to momentum crashes: Daniel and Moskowitz ("Momentum Crashes", 2016) show losses concentrate in sharp rebounds after severe market drawdowns, when the beaten-down short leg rallies violently. A long-horizon design usually blends both constructions, because their failure regimes differ.

## Lookback selection and signal decay

The evidence base clusters in the 3-to-12-month band. The canonical equity construction is 12-month return skipping the most recent month (12-1), because returns inside roughly one month are dominated by short-term reversal, and horizons beyond two to three years shade into value-like overreaction reversal (De Bondt and Thaler, 1985). Momentum therefore lives in a band: too fast is reversal, too slow is value.

Do not grid-search fifty lookbacks and keep the best one — that is data mining, and quant_trader should reject it. Prefer a small ensemble of spaced lookbacks (for example 3, 6, and 12 months) averaged into one signal; the ensemble reduces parameter sensitivity and rebalance-timing luck for a negligible cost in expected return. Then measure signal decay: recompute the strategy with the signal lagged by one, five, and ten trading days. A genuinely long-horizon signal survives a multi-day implementation lag with most of its risk-adjusted return intact; if the edge evaporates with a one-day lag, the strategy is a short-horizon strategy wearing the wrong label, and it belongs to a different design conversation with different cost assumptions.

## Volatility scaling

Scale each position inversely to its forecast volatility so every asset contributes comparable risk: weight proportional to sigma_target / sigma_i times the signal sign, following the construction in Moskowitz, Ooi, and Pedersen (2012). Estimate sigma_i with an exponentially weighted moving average of daily returns (span roughly 20 to 60 days, annualized). Two guards are mandatory per the house safety rules: floor the volatility estimate (for example at one-quarter of its long-run median) so a quiet market cannot blow up the position through a near-zero denominator, and cap the resulting scaling factor so no single asset dominates. Volatility management is also documented to improve momentum itself: Barroso and Santa-Clara ("Momentum Has Its Moments", 2015) show that scaling equity momentum by its own recent volatility reduces crash risk materially — cite the finding qualitatively, do not hard-code their numbers.

## Whipsaw regimes and failure modes

Trend following loses money in rangebound, mean-reverting markets: every reversal flips the sign at close to the worst price, and the strategy pays the whipsaw toll repeatedly. The 2010s equity market, with its sharp V-shaped recoveries (late 2018, early 2020), was hostile to medium-speed trend for exactly this reason. The design responses are diversification across many assets and several speeds, volatility targeting to bound the damage of any one market, and honest expectations: whipsaw cost is the price of the premium, and a simulated trend strategy that never whipsaws has been overfit. For the cross-sectional variant, consider crash-aware sizing that reduces exposure after severe market drawdowns, when short-side beta spikes and crash risk is highest.

## Common pitfalls

- Selecting the single best-performing lookback in-sample, because it is a data-mined parameter that will not repeat; use a spaced ensemble instead.
- Omitting the skip-month in equity cross-sectional momentum, because the most recent month is reversal and contaminates the signal.
- Dividing by an unfloored volatility estimate, because a volatility collapse then produces an absurd position and violates the house division-by-zero guard.
- Presenting an in-sample Sharpe as validated, because grading belongs to quant_trader through the hypothesis-card handoff.
- Selling trend as a guaranteed hedge, because crisis alpha is a historical tendency, not a contract, and 2010s-style whipsaw regimes are the counterexample.
- Ignoring signal decay measurement, because a signal that dies under a one-day lag cannot be run as a long-horizon strategy.

## Definition of done

- [ ] The construction (time-series, cross-sectional, or blend) is chosen and justified against the named evidence base (Moskowitz/Ooi/Pedersen 2012; Jegadeesh/Titman 1993; Asness/Moskowitz/Pedersen 2013; Daniel/Moskowitz 2016).
- [ ] Lookbacks come from the 3-to-12-month evidence band as a spaced ensemble, with the skip-month applied where the asset class requires it.
- [ ] Volatility scaling uses an EWMA estimate with an explicit floor and a position cap.
- [ ] Signal decay is measured with lagged-implementation runs, and the strategy survives a multi-day lag.
- [ ] Whipsaw and momentum-crash behavior is addressed in the design (diversification, sizing, or crash-aware scaling) and stated on the hypothesis card.
- [ ] The complete specification ships as a hypothesis card to quant_trader for validation; no self-graded backtest is presented.
