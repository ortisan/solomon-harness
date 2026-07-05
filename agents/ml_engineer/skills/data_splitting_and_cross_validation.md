# Data Splitting and Cross-Validation

This skill governs how datasets are partitioned for training, model selection, and final evaluation. The split protocol is chosen from the data's dependence structure before any modeling starts, and the final holdout is opened exactly once; a metric produced by the wrong splitter is not an estimate of anything, no matter how many folds it averaged.

## Match the splitter to the dependence structure

Split before you do anything else: fit scalers, encoders, imputers, and feature selection on the training fold only, then apply to validation and test. Fitting any transform on the full dataset is leakage (see `data_leakage_prevention`).

- Independent rows, classification: `StratifiedKFold(n_splits=5, shuffle=True, random_state=seed)`. Stratify on the label so class ratios hold in every fold; use k=10 below roughly 2,000 rows, and `RepeatedStratifiedKFold` (3x5) when the metric is noisy. For skewed regression targets, stratify on quantile bins of `y`.
- Rows sharing an entity (user, patient, instrument, session): `GroupKFold` or `StratifiedGroupKFold` keyed on the entity id, so the same group never spans train and test. Scoring the model on a user it already saw answers an easier question than the one production will ask.
- Time-ordered data: never random K-fold. Use walk-forward / expanding-window validation or `sklearn.model_selection.TimeSeriesSplit(n_splits=5, gap=g)`.

## When K-fold lies

Random K-fold assumes exchangeable rows. It overstates performance whenever that fails:

- Autocorrelated series: adjacent rows land in different folds, so the model is graded on near-copies of its training data. Inflation of 10 to 30 percent in the headline metric is routine on daily financial or sensor data.
- Duplicates and near-duplicates spanning folds (scraped corpora, augmented images). Hash-dedupe before splitting.
- Hidden groups: 50 images per patient split randomly is a patient-identity test, not a diagnosis test.
- Regime or distribution shift: K-fold reports interpolation skill, while production demands extrapolation to the newest period. For anything deployed on future data, the honest estimate is out-of-time.

## Time-series protocol: purge and embargo

For temporal data, walk forward: train on `[0, t)`, validate on `[t, t+h)`, advance, repeat. Two corrections are mandatory when labels are computed over a horizon:

- Purge: drop training samples whose label window overlaps the validation window. A sample labeled with the next 20 days of outcomes, sitting one day before the validation start, has seen the answer.
- Embargo: leave an additional gap after the validation window before training data resumes (purged K-fold with embargo, Lopez de Prado 2018). Size the gap at least `label_horizon + longest_feature_lookback`; `TimeSeriesSplit(gap=...)` implements the simple case.

Strategy-level validation of trading models (transaction costs, slippage, capacity, deflated Sharpe) is owned by `quant_trader`; hand off the walk-forward fold definitions and let that agent grade the backtest.

## Nested cross-validation for tuning

Tuning and estimating generalization on the same folds biases the estimate upward: the winning configuration is partly selected for fold noise. When the CV number itself is the reported result, nest it — an inner loop selects hyperparameters, an outer loop scores the selected model:

```python
from sklearn.model_selection import GridSearchCV, cross_val_score, StratifiedKFold

inner = StratifiedKFold(5, shuffle=True, random_state=1)
outer = StratifiedKFold(5, shuffle=True, random_state=2)
search = GridSearchCV(pipeline, param_grid, cv=inner, scoring="average_precision")
scores = cross_val_score(search, X, y, cv=outer, scoring="average_precision")
```

Cost is `k_outer * k_inner * n_candidates` fits, so reserve nested CV for small-to-medium data. With ample data, a fixed train/validation/test split is the cheaper honest design: tune on validation, report on test, once.

## The final holdout

Keep a final out-of-sample — and for temporal data, out-of-time — holdout that is opened once, at the end. If you tuned against it, inspected per-sample errors on it, or reran after seeing its number, it is spent; the next iteration needs fresh data or a fresh time slice. Log the single holdout evaluation to project memory so "once" is auditable.

## Reporting

Report mean and standard deviation across folds, never a single lucky split, plus the per-fold table. Large fold-to-fold variance is a robustness finding in itself: a model that scores 0.80 +/- 0.12 is a different deliverable from one at 0.78 +/- 0.02. State the splitter, k, gap and embargo sizes, group key, and seed with every result so a reviewer can re-derive the protocol.

## Common pitfalls

- Random K-fold on time-ordered or grouped data; the metric answers the wrong question.
- Transforms or feature selection fit on the full dataset before splitting.
- Tuning against the final holdout, then presenting it as out-of-sample.
- A single train/test split presented as if it were cross-validation.
- No purge or embargo when labels span a horizon, so training rows contain the validation answer.
- Reporting only the fold mean and hiding the variance.
- Re-splitting with new seeds until the metric looks good; seed shopping is tuning.

## Definition of done

- [ ] Splitter chosen and justified from the data's dependence structure (stratified, grouped, or temporal), with the group key or time column named.
- [ ] All preprocessing and feature selection fit inside the training fold only, enforced by a pipeline.
- [ ] Temporal data validated walk-forward with purge and embargo sized to the label horizon plus feature lookback.
- [ ] Hyperparameters tuned on inner folds or a validation split, never on the reported holdout; nested CV used when the CV number is the headline.
- [ ] Final out-of-sample (and out-of-time where applicable) holdout evaluated exactly once, and that evaluation logged.
- [ ] Results reported as mean plus standard deviation across folds with the per-fold table, splitter parameters, and seed.
- [ ] Trading-strategy backtest validation handed off to quant_trader with the fold definitions.
