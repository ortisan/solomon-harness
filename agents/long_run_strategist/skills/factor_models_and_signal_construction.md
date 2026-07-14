---
name: factor-models-and-signal-construction
description: Governs how the long_run_strategist selects factors and builds portfolio-ready signals — which premia (value, quality, momentum, low volatility) have a real evidence base, how to winsorize and cross-sectionally standardize raw data, and how to monitor crowding and decay. Use when choosing a factor for a design, cleaning or combining signals, or deciding whether a candidate factor has enough out-of-sample and cost-survival evidence to enter a hypothesis card.
---

# Factor Models and Signal Construction

This skill governs how the long_run_strategist selects factors and turns raw data into portfolio-ready signals: which premia have a real evidence base, how to standardize and clean signals, how to watch for crowding and decay, and how to refuse data-mined factors. The stance: the published factor zoo is mostly noise, so a factor earns a place in a design only with an economic rationale, out-of-sample evidence, and survival after costs — and the eventual test of any signal belongs to quant_trader, not to this agent.

## The factor menu and its evidence

Restrict the default menu to premia with decades of scrutiny and a named literature.

- Value: cheap assets outperform expensive ones on average. Fama and French (1993) formalized it as HML; the five-factor model (Fama and French, 2015) adds profitability and investment. Value works in long, painful cycles — the 2010s drawdown is part of the record, not a refutation to be edited out.
- Quality and profitability: profitable, stable, well-run firms outperform junk. Novy-Marx ("The Other Side of Value", 2013) on gross profitability; Asness, Frazzini, and Pedersen ("Quality Minus Junk", 2019) on the composite.
- Momentum: covered in depth in the trend_following_and_momentum skill; in a factor stack it is the 12-1 cross-sectional construction (Jegadeesh and Titman, 1993; Carhart, 1997).
- Low volatility / low beta: low-risk assets have historically delivered better risk-adjusted returns than the CAPM predicts (Haugen and Baker; Frazzini and Pedersen, "Betting Against Beta", 2014). The standard rationale is borrowing constraints: many investors cannot use margin, so they bid up high-beta assets instead, leaving low-beta assets underpriced.

Cite the source when using a factor, and state the rationale class: a risk premium (compensation for bearing a real risk) or a behavioral effect (an error that may arbitrage away). The rationale determines how much decay to expect.

## Signal hygiene: z-scoring and winsorization

Raw metrics arrive on incompatible scales, so standardize before combining. Compute each signal cross-sectionally at each rebalance date: z = (x - median) / MAD-based or standard-deviation-based dispersion, using only data available at that date. Winsorize before standardizing — clamp raw values at the 1st and 99th percentiles, or clamp final z-scores to plus/minus 3 — because a single corrupted or extreme observation otherwise owns the portfolio. Where the factor has structural industry tilts (value especially), standardize within sector or country as well as globally, and make that choice explicit, because it changes what bet the portfolio holds. Combine standardized signals with fixed, simple weights (equal weight is a strong default); fitting combination weights is model estimation and goes to ml_engineer with proper cross-validation and leakage control.

## Crowding and decay monitoring

Published factors decay. McLean and Pontiff ("Does Academic Research Destroy Stock Return Predictability?", 2016) document that post-publication factor returns fall substantially — roughly a third to a half, stated qualitatively. Monitor each live factor with three instruments: the valuation spread between the long and short legs (a historically wide spread suggests the premium is cheap, a compressed spread suggests crowding), the rolling information coefficient (the correlation between the signal and subsequent returns; a persistent fall toward zero is decay), and drawdown depth versus the factor's own history. Distinguish revaluation-driven performance from true premium: a factor whose past return came mostly from its own long leg getting more expensive has borrowed from its future. Decay findings feed back into the hypothesis card as reduced expected returns, not as an excuse to re-mine the data for a fresher signal.

## Refusing data-mined factors

Harvey, Liu, and Zhu ("...and the Cross-Section of Expected Returns", 2016) counted hundreds of published factors and concluded that conventional significance thresholds are far too loose once the field's collective search is accounted for; they argue for a t-statistic bar near 3. Apply that skepticism procedurally. A candidate factor enters a design only if it passes all of: (1) an economic rationale stated before looking at the performance, specific enough to be falsifiable; (2) out-of-sample evidence in at least one independent dimension — a different time period, geography, or asset class than the one it was discovered in; (3) survival after realistic costs, since many published anomalies live entirely inside the bid-ask spread; (4) robustness to reasonable perturbation of its definition — a factor that works with an 11-month window but not 10 or 12 is a coincidence. The validation runs themselves are specified on the hypothesis card and executed by quant_trader; this agent's job is to make the acceptance criteria explicit and pre-registered so the test cannot be quietly softened after a failure.

## Common pitfalls

- Adopting a factor from a single paper without out-of-sample or cross-market evidence, because the factor zoo's base rate is failure (Harvey/Liu/Zhu).
- Skipping winsorization, because one erroneous data point at z = 15 silently becomes the portfolio's largest bet.
- Standardizing with statistics that include future dates, because look-ahead contamination fabricates performance and will be caught in validation.
- Ignoring sector structure in value signals, because the portfolio becomes a permanent sector bet the card never declared.
- Fitting signal-combination weights in-sample inside this agent, because model estimation belongs to ml_engineer under cross-validation and leakage control.
- Treating a compressed valuation spread and a fading information coefficient as noise, because crowding and decay are the expected fate of published factors and must lower the card's targets.

## Definition of done

- [ ] Every factor in the design names its evidence base and states whether the rationale is risk-based or behavioral.
- [ ] Signals are winsorized and cross-sectionally standardized using only point-in-time data, with sector/country neutralization decided explicitly.
- [ ] Combination weights are fixed and simple, or delegated to ml_engineer with validation requirements attached.
- [ ] Crowding and decay monitoring (valuation spread, rolling information coefficient, drawdown vs history) is specified with review triggers.
- [ ] Candidate factors pass the pre-registered gate: prior rationale, independent out-of-sample evidence, cost survival, and definition robustness.
- [ ] Acceptance criteria are written on the hypothesis card before testing, and the test itself is handed to quant_trader.
