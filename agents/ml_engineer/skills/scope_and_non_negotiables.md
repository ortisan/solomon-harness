---
name: scope-and-non-negotiables
description: States the concrete standard every ML or DRL model must satisfy before it is considered done, covering the hypothesis card, cross-validation plus holdout, leakage audit, tensor safety guards, reproducibility, and tests. Use when scoping ML or DRL work, or checking a deliverable against the non-negotiable baseline before it leaves the workstation.
---

# ML Engineer Best Practices

Purpose: a concrete standard for training, validating, and shipping ML and DRL models in this project without overfitting, data leakage, or numerical faults.

## Scope and non-negotiables


Every model that leaves your workstation must satisfy all of these before it is considered done:

- A written Model Hypothesis (see below) committed alongside the code.
- Cross-validation results plus a held-out out-of-sample test the model never touched during tuning.
- A leakage audit with no open findings.
- Shape, divide-by-zero, and overflow guards on every critical tensor operation.
- A reproducible run: fixed seeds, pinned dependencies, recorded dataset version and config.
- Unit and integration tests, with all external services mocked.

## Common pitfalls

- Training started before a Model Hypothesis was committed — the acceptance threshold then drifts to fit whatever number the run produced.
- Cross-validation scores presented as the out-of-sample result — tuning already saw those folds; only the untouched holdout estimates generalization.
- A leakage audit compressed to "looks clean" with no per-feature as-of timestamps — that is an unverified claim, not an audit.
- A critical matmul, reshape, or division shipped without a shape assert or zero-denominator guard — silent broadcasting and divide-by-zero train to convergence on garbage.
- Results from an unseeded run or an unpinned environment — the numbers cannot be regenerated, so they cannot be reviewed.
- Tests that call live data or model-serving APIs — nondeterministic, and a network flake becomes a false test verdict.
- A trading backtest self-certified by this agent — cost, slippage, and capacity validation is quant_trader's gate and must be handed off.

## Definition of done

- [ ] Model Hypothesis committed and logged to project memory before the first training run.
- [ ] Cross-validation mean and standard deviation reported, and the out-of-sample holdout — never seen during tuning — evaluated against the card's thresholds.
- [ ] Leakage audit completed feature by feature with as-of timestamps and zero open findings.
- [ ] Every critical tensor operation carries its shape assertion plus divide-by-zero and overflow guards.
- [ ] Seeds fixed, dependencies pinned, and the dataset version and config recorded so the run regenerates end to end.
- [ ] Unit and integration tests are green and hermetic, with every external service mocked.
- [ ] Trading and DRL deliverables handed to quant_trader with the hypothesis card and backtest artifacts.
