---
name: position-sizing-and-risk-budgeting
description: Governs how the long_run_strategist sizes each position and the whole portfolio — volatility targeting, capped fractional Kelly, drawdown-based de-risking ladders, and correlation-aware risk budgets. Use when setting a strategy's volatility target and gross-exposure cap, capping a sizing rule against Kelly, or pre-committing the de-risking ladder before a drawdown occurs.
---

# Position Sizing and Risk Budgeting

This skill governs how the long_run_strategist decides how much of each position and of the whole portfolio to hold: volatility targeting, capped fractional Kelly, drawdown-based de-risking, and correlation-aware risk budgets. The stance: sizing is where strategies die — a correct signal at the wrong size still ruins the account — so size from risk, not conviction, cap everything that depends on an estimated edge, and pre-commit the de-risking rules before the drawdown, not during it.

## Volatility targeting

Fix a portfolio-level annualized volatility target and scale exposure to hold it. A long-horizon diversified strategy typically targets around 10 percent annualized; that number is a design choice recorded on the hypothesis card, chosen so the implied drawdown expectation (see below) is survivable for the capital and the mandate. Mechanics: forecast portfolio volatility with an exponentially weighted moving average of daily portfolio returns (span roughly 20 to 60 days, annualized by the square root of 252), then set the scaling factor to target divided by forecast. Guards are mandatory per the house safety rules: floor the volatility forecast so a quiet regime cannot push the scaling factor toward infinity through a near-zero denominator, and cap gross exposure explicitly (for example 200 percent) so the strategy's use of margin is bounded by design rather than by the forecast. Volatility targeting stabilizes the risk actually taken across regimes and makes the realized track comparable to the card's targets; without it, the strategy takes its largest exposures precisely when markets are quietest and most complacent.

## Kelly and its cap

The Kelly criterion sizes to maximize long-run log growth given a known edge and known odds. Its relevance here is mostly as an upper bound: full Kelly assumes the edge estimate is exact, and in markets it never is. Overestimating the edge and betting full Kelly on it produces violent drawdowns and, past a point, lower growth than smaller bets — the growth curve is asymmetric, and betting beyond true Kelly is strictly destructive. House rule: cap sizing at 0.25x to 0.5x of the estimated Kelly fraction. Fractional Kelly buys a large reduction in variance and drawdown for a modest reduction in growth (half-Kelly retains roughly three-quarters of full-Kelly growth at about half the variance, stated qualitatively), and it is robustness against the estimation error that is certain to exist. In practice the volatility target above is usually the binding constraint; compute the implied Kelly fraction anyway as a sanity check, and if the volatility target implies betting beyond half Kelly, the target is too high for the edge claimed on the card.

## Drawdown-based de-risking ladders

Pre-commit a ladder that cuts exposure as drawdown from the high-water mark deepens. A workable default for a 10 percent volatility strategy: at a 10 percent drawdown, cut exposure to 75 percent of normal; at 15 percent, to 50 percent; at 20 percent, to 25 percent; beyond 25 percent, halt and trigger a design review, because the strategy is outside the envelope the hypothesis card promised. Re-risking follows the same ladder in reverse with hysteresis — restore each step only after the drawdown recovers several points past the level that triggered the cut — so the portfolio does not flip-flop across a boundary. Two properties make the ladder legitimate rather than superstitious: it is written before live losses (a de-risking rule invented mid-drawdown is emotion with arithmetic), and it is consistent with the drawdown expectation of the volatility target — a 10 percent volatility strategy should be expected to see drawdowns of roughly two to three times its annualized volatility over decades, so the ladder must not be so tight that normal fluctuation triggers a permanent de-risk.

## Correlation-aware sizing

Position-level volatility is not risk contribution. A position's marginal contribution to portfolio risk depends on its correlation with everything else, so ten "independent" 2-percent-risk positions that correlate at 0.8 are one 15-percent bet wearing ten names. Budget risk, not capital: cap each position's and each cluster's contribution to total portfolio risk (for example, no cluster above 20 percent of the risk budget), computed from the shrunk covariance matrix specified in the portfolio-construction skill. Track the effective number of independent bets rather than the count of positions. And stress the correlation assumption: recompute the risk budget with correlations shifted toward one, because in liquidation events diversification degrades exactly when it is needed; the sizing must remain survivable under that stress, and the stressed figure belongs on the hypothesis card next to the normal-regime figure.

## Common pitfalls

- Sizing by conviction or equal capital weights instead of risk contribution, because correlated positions silently concentrate the book.
- Dividing by an unfloored volatility forecast, because a quiet market then produces enormous exposure and violates the house division-by-zero guard.
- Betting at or near full Kelly on an estimated edge, because edge estimates are noisy and overbetting is asymmetrically destructive; the cap is 0.25x to 0.5x.
- Writing the de-risking rule during the drawdown, because a rule invented under stress is not a rule.
- A ladder tighter than the volatility target's normal drawdown envelope, because routine fluctuation then locks the strategy permanently under-risked.
- Reporting only normal-regime risk contributions, because correlations rise in crises and the stressed budget is the one that matters for survival.

## Definition of done

- [ ] The annualized volatility target is stated on the hypothesis card with its implied drawdown expectation (roughly two to three times annualized volatility over decades).
- [ ] The volatility forecast method (EWMA span, floor, annualization) and the gross-exposure cap are specified.
- [ ] The implied Kelly fraction is computed and sizing stays within the 0.25x-0.5x Kelly cap.
- [ ] The drawdown de-risking ladder, its re-risking hysteresis, and the halt-and-review level are written down before live exposure.
- [ ] Risk budgets are correlation-aware: per-position and per-cluster risk-contribution caps, plus a correlations-toward-one stress figure.
- [ ] The full sizing policy ships with the hypothesis card to quant_trader for validation against the stated targets.
