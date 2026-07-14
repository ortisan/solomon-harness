---
name: hyperparameters-and-tuning
description: Governs how hyperparameter search is designed, budgeted, executed, and reported, covering grid search, random search, and Optuna with the TPE sampler run only against cross-validation folds. Use when designing a hyperparameter search, choosing a search strategy or budget, or reviewing a tuning report for holdout contamination.
---

# Hyperparameters and Tuning

This skill governs how hyperparameter search is designed, budgeted, executed, and reported. Search is a tracked, reproducible experiment with a pre-declared budget, run against cross-validation folds and never against the final holdout — and the tuning process itself is reported, because a best-of-500-trials number means something different from a best-of-10.

## Search strategy

- Grid search only for small discrete spaces (roughly <= 24 combinations, e.g. two categorical knobs). Beyond that it wastes budget on unimportant dimensions.
- Random search is the floor for continuous spaces (Bergstra and Bengio, 2012): with the same budget it covers each dimension better than a grid. `RandomizedSearchCV` is acceptable for sklearn estimators.
- Default choice: Optuna (4.x) with the TPE sampler. Define the space in code, use log-scale for rates and regularization strengths, and seed the sampler:

```python
import optuna

def objective(trial):
    params = {
        "learning_rate": trial.suggest_float("learning_rate", 1e-4, 0.3, log=True),
        "max_depth": trial.suggest_int("max_depth", 3, 10),
        "min_child_weight": trial.suggest_float("min_child_weight", 1e-2, 10, log=True),
        "subsample": trial.suggest_float("subsample", 0.5, 1.0),
    }
    return cv_score(params)  # mean metric over the CV folds

study = optuna.create_study(
    direction="maximize",
    sampler=optuna.samplers.TPESampler(seed=42),
    storage="sqlite:///tuning.db",   # trials survive crashes and are auditable
    study_name="churn-lgbm-v3",
)
study.optimize(objective, n_trials=100)
```

- Multi-fidelity methods when single trials are expensive: successive halving / ASHA allocate small budgets broadly and promote only the survivors. In Optuna use `HyperbandPruner` or `SuccessiveHalvingPruner` with `trial.report(...)` plus `trial.should_prune()` inside the training loop; in sklearn, `HalvingRandomSearchCV`. `MedianPruner(n_warmup_steps=5)` is a sane default for neural nets.

## Budgets

Pre-declare the budget in the model hypothesis: number of trials (50 to 200 is typical for tree models; fewer, pruned, for neural nets), wall-clock ceiling, and hardware. Also pre-declare the kill criterion — if the best trial has not beaten the baseline by the minimum margin at budget exhaustion, the result is a documented negative, not a license to keep searching. Every trial is logged (RDB storage or the experiment tracker), including pruned and failed ones; a search whose losers are invisible cannot be audited.

## Early stopping

- Gradient-boosted trees: train with a large `n_estimators` cap and `early_stopping_rounds=50` on a validation fold; record `best_iteration` and refit at that iteration count. The stopping set is spent data — it must not be the reported holdout.
- Neural nets: monitor the validation metric with patience of 5 to 10 evaluations; checkpoint and restore the best weights, and record the stopping epoch so the run is reproducible without re-searching.
- Early stopping is itself a hyperparameter consumer: the validation split used to stop is part of the tuning protocol and gets stated in the report.

## Overfitting guards

Regularization stays in the search space (L1/L2, dropout, weight decay, `max_depth`, `min_child_weight`) rather than bolted on afterward. After selection, check the train-minus-validation gap: a model at train 0.99 / validation 0.78 memorized, whatever the search says. Prefer the simpler configuration when two candidates are within one standard error of each other (the 1-SE rule); the flatter optimum generalizes and redeploys better.

## Reporting tuning honestly

- Tune against CV folds, never against the final holdout. The honest headline number comes from data the search never touched: nested CV or a fresh out-of-sample slice (see `data_splitting_and_cross_validation`).
- Report the search protocol next to the result: space, sampler, number of trials, pruning policy, compute spent, and the tracker link. "AUC 0.83" and "AUC 0.83, best of 200 TPE trials" are different claims.
- Never report best-of-N-seeds as the model's performance. Rerun the winning configuration across 3 to 5 seeds and report mean and standard deviation; selection on seed noise is tuning by another name.
- Save the winning configuration as a committed YAML/JSON file, not as notebook state, and record the study name so the full trial history is recoverable.
- Trading-strategy parameter sweeps (thresholds, position sizing, cost assumptions) are validated by `quant_trader`; excessive strategy re-parameterization is backtest overfitting, and that gate is theirs.

## Common pitfalls

- Grid search over a continuous space, spending the budget on redundant lattice points.
- Tuning against the holdout, or letting early stopping peek at it.
- Reporting the best trial's CV score as the generalization estimate without a fresh holdout or nested CV.
- Cherry-picking the best seed; the seed is not a hyperparameter.
- Unlogged trials, so the multiplicity behind the winning number is invisible.
- Winning config living only in a notebook cell instead of a committed file.
- Extending the search after budget exhaustion because the result "was close".

## Definition of done

- [ ] Search space, sampler, seed, trial budget, and kill criterion declared before the search started.
- [ ] Search run with a tracked method (Optuna TPE, halving/ASHA, or randomized search) with every trial persisted to durable storage.
- [ ] Early stopping performed on a validation fold with the chosen iteration/epoch recorded; the reported holdout untouched.
- [ ] Train-versus-validation gap checked on the selected configuration; 1-SE simplicity rule considered.
- [ ] Winning configuration committed as YAML/JSON with the study name referenced.
- [ ] Final metric measured on data the search never saw, rerun across 3 to 5 seeds, reported as mean plus standard deviation with the search protocol stated.
- [ ] Trading-parameter sweeps handed off to quant_trader for backtest-overfitting review.
