---
name: cointegration-and-pairs-trading
description: Governs statistical-arbitrage pair selection and spread construction — Engle-Granger and Johansen cointegration tests, ADF stationarity, Ornstein-Uhlenbeck half-life, hedge-ratio estimation, z-score entry and exit rules, and rolling stability monitoring for a relationship that can break down. Use when selecting, testing, or monitoring a pairs-trading or statistical-arbitrage candidate before it is registered as a strategy hypothesis.
---

# Cointegration and Pairs Trading

Cointegration identifies pairs of individually non-stationary price series whose linear combination is stationary — a spread that wanders but is pulled back to an equilibrium level rather than drifting forever. This skill governs how quant_trader selects, tests, and monitors a pairs-trading candidate: which test to run, how to size the hedge ratio, how to confirm the spread mean-reverts on a tradeable horizon, and when a previously cointegrated pair has broken. Adapted from agiprolabs/claude-trading-skills (MIT). Correlation is not a substitute: two assets can move together for months without being cointegrated, and a cointegrated pair can show weak short-term correlation during exactly the divergence a pairs trade is meant to capture.

## Cointegration versus correlation

Correlation measures short-term co-movement and can vanish within weeks as the regime changes; cointegration measures a long-run price-level equilibrium that, where genuine, persists for months to years. Two independently trending series — both rising through a bull market — show high correlation with no equilibrium relationship at all, the classic route to a spurious pairs trade. Screen by correlation (Pearson above 0.7 over the same window) only to cut the search space before the costlier cointegration test; clearing that bar is not evidence of cointegration.

## Testing for cointegration

Engle-Granger two-step is the default for two series: regress `Y_t = alpha + beta*X_t + epsilon_t` by OLS, then run an Augmented Dickey-Fuller test on the residuals. Stationary residuals (p < 0.05) indicate cointegration; beta is the hedge ratio, alpha the long-run spread mean. Engle-Granger uses its own critical values, not the standard ADF table — roughly -3.90 at 1%, -3.34 at 5%, -3.04 at 10% for a two-series test. Test both Y-on-X and X-on-Y and report the stronger (more negative) result, since the two regressions can disagree. The Johansen test handles three or more series at once via a VAR representation, testing the rank of the coefficient matrix with a trace statistic and a maximum-eigenvalue statistic; use it for baskets over two legs, since pairwise Engle-Granger misses relationships that only hold jointly. Phillips-Ouliaris substitutes for Engle-Granger when residuals show heteroskedasticity or serial correlation. Minimum sample: 100 observations is a hard floor, 200+ preferred, with out-of-sample stability checked rather than trusting the fitting window alone.

## Spread construction and mean-reversion diagnostics

Build the spread from the fitted hedge ratio, `spread_t = Y_t - beta*X_t - alpha`, then standardize to a z-score using its own rolling or full-sample mean and standard deviation — the z-score, not the raw spread, drives entry and exit. Confirm the spread itself mean-reverts, independent of the cointegration p-value: an ADF test on the spread should also clear p < 0.05, and the Hurst exponent should sit below 0.5 (0.5 is a random walk; toward 0.3-0.4 is a clearer signal). Estimate the half-life by fitting an AR(1) model, `spread_t = c + lambda*spread_{t-1} + u_t` — the discrete-time analog of an Ornstein-Uhlenbeck process — as `half-life = -ln(2)/ln(lambda)`. A viable candidate reverts with a half-life of roughly 5 to 60 days: shorter is often noise the microstructure eats in costs, longer ties up capital for a return that behaves more like drift than a trade.

## Rolling stability and when to stop trading

Cointegration is not permanent: a structural break — a protocol change, a corporate action, a fundamental shift — can end the relationship without warning. Re-run the test on a rolling window (60-90 days) and track the p-value, hedge ratio, and half-life over time rather than trusting the original fit indefinitely. Set explicit stop conditions ahead of time: a rolling p-value past 0.10, a hedge ratio drifted more than roughly 25% from the estimation-window value, or a half-life outside the 5-60 day band signal flattening the pair, not widening the stop.

## Entry, exit, and the cost hurdle

A standard entry opens when the z-score crosses roughly 2 standard deviations from the mean — long the underperformer, short the outperformer, sized by the hedge ratio — and exits on reversion, typically z = 0 or z = 0.5. Add a hard stop, for example z beyond 3.5 or no reversion within some multiple of the half-life, since divergence past that point is more likely a broken relationship than a bigger opportunity. Cost it honestly first: a pairs trade is four transactions per round trip, and at a representative 0.3% per leg that is 1.2% round-trip drag the spread's expected move must clear.

## Wiring into the house workflow

Estimate the hedge ratio and every diagnostic walk-forward — fit on a training window, trade only the following window — never on the full sample and backtested on that same data; that ordering is look-ahead bias regardless of how clean the in-sample p-value looks. Once a pair clears cointegration, spread-stationarity, and half-life screens, it still needs the mandatory model-hypothesis card (target Sharpe, drawdown limit, profit factor, latency and cost constraints) and must pass quant_trader's backtest pipeline before it is treated as validated. Screening produces a candidate, not a cleared trade.

## Common pitfalls

- Spurious cointegration between two series simply trending together in the same regime; confirm on 200+ observations and check out-of-sample stability, not just the fitting-window p-value.
- Structural breaks silently ending a relationship that was genuinely cointegrated historically; monitor rolling p-values rather than trusting a one-time result forever.
- Estimating the hedge ratio on the full sample and backtesting on that same sample, inflating every downstream number through look-ahead bias.
- Trading pairs tested on fewer than 100 observations, where the test has too little power to distinguish a real relationship from noise.
- Ignoring the four-leg transaction cost structure, so a statistically significant but economically small spread never clears its own hurdle.
- Assuming the relationship holds symmetrically in every regime; a pair that only reverts in calm markets or one direction needs a threshold or regime-conditioned model, not a static z-score rule.

## Definition of done

- [ ] Correlation pre-filter applied (~0.7 threshold) before the costlier cointegration test, on a sample of at least 100 (preferred 200+) observations.
- [ ] Engle-Granger run in both directions (or Johansen for 3+ series) with the correct critical values; hedge ratio and long-run mean recorded.
- [ ] Spread confirmed mean-reverting independently: ADF p < 0.05 and Hurst below 0.5, with half-life via the AR(1)/Ornstein-Uhlenbeck relation falling between 5 and 60 days.
- [ ] Rolling stability monitoring wired in (60-90 day window) with explicit stop conditions on p-value, hedge-ratio drift, and half-life drift.
- [ ] Entry/exit/stop z-score thresholds defined and the four-leg cost hurdle checked against the expected reversion move.
- [ ] Hedge ratio and half-life estimated walk-forward, never fit and tested on the same sample; candidate registered on the mandatory model-hypothesis card and cleared through quant_trader's backtest pipeline before use.
