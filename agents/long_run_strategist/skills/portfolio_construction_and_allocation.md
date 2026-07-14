---
name: portfolio-construction-and-allocation
description: Governs how the long_run_strategist turns signals and asset views into portfolio weights — the limits of mean-variance optimization, when risk parity or hierarchical risk parity is the better tool, the mandatory constraint set, and estimation-error handling via shrinkage. Use when choosing a portfolio construction method, setting position and sector constraints, or checking a design against the 60/40 baseline it must beat after costs.
---

# Portfolio Construction and Allocation

This skill governs how the long_run_strategist turns signals and asset views into portfolio weights: what mean-variance optimization can and cannot be trusted with, when risk parity and hierarchical risk parity are the better tool, which constraints are mandatory, and how to handle estimation error. The stance: the weakest input in any allocation problem is the expected-return estimate, so prefer constructions that need it least, regularize everything, and force every design to beat a plain 60/40 baseline after costs before it earns its complexity.

## Mean-variance and its limits

Markowitz (1952) mean-variance optimization is the correct theory and a dangerous tool. In practice it is an error maximizer (Michaud, 1989): the optimizer allocates most aggressively exactly where the inputs are most wrong, because an overestimated expected return or an underestimated correlation looks like an opportunity. Expected returns are the noisiest input by an order of magnitude — small perturbations flip the solution between corner portfolios. Consequences for design: never feed a raw historical mean into an unconstrained optimizer; treat unconstrained mean-variance output as a diagnostic, not a portfolio; and when expected returns are genuinely needed, shrink them heavily toward a cross-sectional grand mean or derive them from equilibrium (the Black-Litterman construction, which starts from market-implied returns and tilts by explicitly sized views) rather than from sample averages.

## Estimation-error handling

Regularize both inputs and outputs. For the covariance matrix, use Ledoit-Wolf shrinkage toward a structured target (constant-correlation or identity); with hundreds of assets and a few years of data, the sample covariance matrix is ill-conditioned and its inverse is garbage. For weights, constraints are regularization: Jagannathan and Ma (2003) showed that imposing no-short-sale and upper-bound constraints improves out-of-sample performance in the same way shrinkage does, even when the constraints are "wrong" in-sample. Prefer longer estimation windows for correlations (they are more stable) and shorter, exponentially weighted windows for volatilities (they move faster). Where the choice between estimators materially changes the portfolio, that sensitivity itself is a finding to record on the hypothesis card, and any fitted estimator beyond these standard forms goes to ml_engineer.

## Risk parity and equal risk contribution

Risk parity abandons expected-return estimates entirely and sets weights so each asset or sleeve contributes equally to portfolio risk. Because low-volatility assets (bonds) get large weights, an unscaled risk-parity portfolio has bond-like expected returns; reaching equity-like targets requires gearing, and that borrowed capital is the construction's real cost and its real risk. Two failure modes must be stated in any risk-parity design: correlation regime shifts (equal risk contribution computed on a stock-bond correlation of -0.3 is a different portfolio from one computed at +0.5, and 2022-style simultaneous stock and bond drawdowns hit geared balanced portfolios hard), and the funding cost of the gearing itself, which rises exactly when rates rise. Equal risk contribution weights require the full covariance matrix and a numerical solve; inverse-volatility weighting is the correlation-blind approximation and is often good enough at the sleeve level.

## Hierarchical risk parity

Lopez de Prado's hierarchical risk parity (2016) addresses the instability of covariance inversion differently: cluster assets by correlation distance into a hierarchy, then allocate top-down by recursive bisection, splitting risk between clusters and only then within them. HRP never inverts the covariance matrix, so it works when the matrix is singular or badly conditioned (more assets than observations), and it degrades gracefully. Its output depends on the clustering, so fix the linkage method and distance metric in the specification and check that small data perturbations do not reshuffle the tree wildly. HRP is a strong default for wide, heterogeneous universes where mean-variance is untrustworthy and plain risk parity ignores obvious cluster structure.

## Constraints and the 60/40 baseline

Mandatory constraint set for any long-horizon design: a maximum single-position weight (5 to 10 percent for diversified universes), sector or cluster caps (20 to 30 percent) so no theme dominates, a minimum position count consistent with the diversification claim, bounds on gross and net exposure, and turnover limits that connect to the rebalancing skill. Every constraint must be written down with its rationale; an undocumented constraint is a hidden view.

Finally, the baseline: a global 60/40 equity/bond portfolio, rebalanced annually, is the null hypothesis of long-horizon allocation. Any proposed construction must beat it after costs on the risk-adjusted metrics named in the hypothesis card, or state precisely what else it buys (a drawdown profile, a diversification property, a liability match). Complexity that cannot beat two index funds is negative engineering, and quant_trader's validation run should include the baseline comparison explicitly.

## Common pitfalls

- Feeding raw historical mean returns into an unconstrained optimizer, because mean-variance maximizes into estimation error and produces extreme, unstable corner portfolios.
- Inverting a sample covariance matrix with more assets than independent observations, because the inverse is numerically meaningless; use shrinkage or HRP.
- Presenting risk parity's historical performance without stating the gearing and its funding cost, because the borrowed capital is where the tail risk lives.
- Assuming stock-bond correlation is permanently negative, because regime shifts (2022) break equal-risk arithmetic computed on the old regime.
- Shipping a design with undocumented constraints, because each constraint is a view and hidden views cannot be reviewed.
- Skipping the 60/40 comparison, because a complex allocation that loses to the baseline after costs should not ship.

## Definition of done

- [ ] The construction method (constrained mean-variance, risk parity, HRP, or a stated hybrid) is chosen with a written rationale tied to input quality.
- [ ] Expected returns, if used at all, are shrunk or equilibrium-derived; covariance uses Ledoit-Wolf-style shrinkage with stated windows.
- [ ] The full constraint set (max weight, sector/cluster caps, exposure bounds, minimum positions) is documented with rationales.
- [ ] Risk-parity or geared designs state the gearing level, funding-cost assumption, and correlation-regime sensitivity.
- [ ] HRP specifications fix the distance metric and linkage and include a perturbation check on the cluster tree.
- [ ] The hypothesis card names the 60/40 baseline comparison, and the validation handoff to quant_trader includes it.
