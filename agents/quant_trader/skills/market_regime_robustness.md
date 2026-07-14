---
name: market-regime-robustness
description: Requires detecting market regimes explicitly, scoring strategy performance in each, stress-testing through named crisis windows, and proving parameter stability before any all-weather claim. Use when validating regime robustness or reviewing a backtest with a single blended PnL curve.
---

# Market-Regime Robustness

A backtest average hides which market states produced the PnL, and this skill requires detecting regimes explicitly, scoring the strategy in each, stressing it through named crisis windows, and proving parameter stability before any deployment claim. One-regime PnL presented as all-weather is the polite name for an undisclosed short-volatility position.

## Regime detection

Use at least two independent lenses and report both:

- Volatility buckets: split the sample into realized-vol terciles (20-60 day EWMA) or VIX terciles for equity-linked books. Volatility clusters — a GARCH(1,1) fit on daily equity returns typically shows alpha + beta > 0.95, meaning shocks persist for weeks — so the vol state is the most informative regime variable and the cheapest to compute.
- Hidden Markov Model: fit a 2-3 state Gaussian HMM (hmmlearn `GaussianHMM`) on daily returns and realized vol. Require that states are persistent (transition-matrix diagonals > 0.9 for daily data), economically nameable (calm-bull, turbulent, crisis), and stable across seeds and window perturbations; an HMM whose labels flip under reseeding is fitting noise. Smoothed (two-sided) state probabilities are for analysis only — a live signal may consume only filtered, causal probabilities, or the regime filter itself becomes lookahead.
- Trend vs mean-reversion: variance-ratio test or Hurst exponent (H > 0.55 trending, H < 0.45 reverting) to tag which mechanism the strategy's edge needs.
- Macro flags where relevant: rising vs falling rates, risk-on vs risk-off via credit spreads, USD strength.

## Stress windows

The test period must include named crises, scored out-of-sample, with dates pinned:

- 2008 GFC (Sep-Nov 2008), the May 2010 flash crash, the Aug 2015 CNY-devaluation selloff, Feb 2018 volmageddon, the March 2020 COVID crash, the 2022 rate shock (the year equities and bonds fell together, which breaks naive diversification assumptions), the Aug 2024 yen-carry unwind vol spike, and the April 2025 tariff gap.
- A strategy untested through a crisis is untested. If the instrument's history is too short (many crypto pairs), say so on the hypothesis card, stress with bootstrapped and synthetic shock paths, and size as if the worst observed drawdown will be exceeded.
- Report per window: net PnL, max drawdown, worst single day, and whether the risk controls (governor, kill switch) would have tripped.

## Per-regime reporting

- Report Sharpe, max drawdown, hit rate, and turnover per regime, for every detection lens used.
- Reject strategies whose entire PnL comes from one regime unless that regime is the explicit thesis — and then size for its absence: assume the favorable regime occupies only its historical share of time and check the drawdown carried while waiting for it.
- Watch conditional tails: a strategy that is flat on average in crisis regimes but carries a fat left tail there is a crisis-short in disguise.

## Parameter-stability plots

- Plot the performance surface (net Sharpe) over the parameter grid as a heatmap for each parameter pair. Choose the parameter set from the center of a plateau, never the peak of a spike.
- Neighborhood rule: perturb each chosen parameter by +/-20%; net Sharpe should stay within roughly 30% of the chosen value. A sharp cliff means the fit found the peak of a noisy surface, and live performance will land in the valley beside it.
- Repeat the stability check per regime: a plateau in the calm state that becomes a cliff in the turbulent state is regime fragility with extra steps.

## Minimum out-of-sample regime coverage

- The out-of-sample window must span at least two distinct volatility regimes and include at least one stress window from the list above; otherwise extend the OOS period or explicitly downgrade the confidence claim on the hypothesis card.
- Present walk-forward segment results against the regime timeline, so a reviewer can see whether OOS success came from one friendly stretch of market.

## Common pitfalls

- One-regime PnL presented as all-weather; the strategy is short the regime change.
- HMM regimes decoded with smoothed probabilities feeding a live signal — lookahead smuggled in through the regime filter.
- Regime labels that flip under reseeding or a one-month window shift, treated as stable structure.
- Picking the parameter peak instead of the plateau; the cliff edge is where live trading starts.
- Testing 2020 but not 2022: a fast crash and a slow grind are different failure modes, and hedges that worked in one failed in the other.
- Short-history assets stressed only on their own history; absence of a crisis in the data is not absence of crisis risk.

## Definition of done

- [ ] Regimes detected with at least two lenses (vol buckets plus HMM or a trend/reversion test); HMM persistence and seed-stability verified; only causal probabilities feed live signals.
- [ ] Per-regime table reported: Sharpe, max drawdown, hit rate, and turnover per regime and per lens.
- [ ] All applicable named stress windows scored out-of-sample, with per-window PnL, max drawdown, worst day, and risk-control trips.
- [ ] Parameter-stability heatmaps produced; the chosen set sits on a plateau and survives the +/-20% perturbation rule, checked per regime.
- [ ] OOS window covers at least two volatility regimes and one stress window, or the confidence claim is explicitly downgraded on the hypothesis card.
- [ ] One-regime dependence either rejected or declared as the thesis, with sizing for the regime's absence.
