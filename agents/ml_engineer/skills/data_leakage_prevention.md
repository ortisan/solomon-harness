# Data Leakage Prevention

This skill governs how features, preprocessing, and splits are audited so no information unavailable at prediction time reaches the model. Leakage is a defect, not a caveat: a leaked metric predicts nothing about production, and the audit that proves its absence is part of the deliverable, not optional hygiene.

## The leakage taxonomy

Audit every feature against this list. Any hit is a defect:

- Target leakage: a feature computed from, or a proxy of, the label — future-aggregated statistics, post-event fields (`days_to_churn`, `refund_issued`), columns populated by the outcome process itself.
- Temporal leakage: information not available at prediction time. For each feature confirm its as-of timestamp <= the decision time; lag or shift everything that is only known later. Watch for silently backfilled columns in warehouses, where today's value overwrites history.
- Train/test contamination: scaling, imputation, target encoding, resampling (SMOTE), or feature selection fit across the split.
- Group leakage: the same entity (user, patient, instrument) appearing on both sides of a split; use group-aware splitters (see `data_splitting_and_cross_validation`).
- Duplicate or near-duplicate rows spanning splits. Hash-dedupe exact rows; for text and images, screen near-duplicates with embedding similarity before splitting.
- Look-ahead in derived indicators: centered rolling windows, full-series normalization, labels computed over a horizon that overlaps the next fold.
- Survivorship and selection bias in the dataset itself: delisted instruments removed, only successful entities retained. This one cannot be fixed by splitting; it requires a better data pull.

## Fit-transform inside the fold: pipeline enforcement

The only reliable defense against contamination is structural: every learned transform lives inside an `sklearn.pipeline.Pipeline` (or the framework equivalent), and cross-validation is run on the pipeline, so `fit` sees the training fold only.

```python
from sklearn.pipeline import Pipeline
from sklearn.compose import ColumnTransformer
from sklearn.preprocessing import StandardScaler, TargetEncoder
from sklearn.feature_selection import SelectKBest
from sklearn.model_selection import cross_validate

pipe = Pipeline([
    ("prep", ColumnTransformer([
        ("num", StandardScaler(), num_cols),
        ("cat", TargetEncoder(random_state=0), cat_cols),  # internal CV, sklearn >= 1.3
    ])),
    ("select", SelectKBest(k=50)),          # selection is a learned transform too
    ("model", clf),
])
scores = cross_validate(pipe, X, y, cv=cv)   # fit happens inside each fold
```

Rules that follow from this design:

- Never call `fit` or `fit_transform` on anything before the split. `transform`-only steps (log, ratios from the same row) are safe; anything that learns statistics is not.
- Target encoding is the highest-risk transform: use `TargetEncoder` with its built-in internal cross-fitting rather than a hand-rolled groupby-mean, which leaks the row's own label.
- Resampling (SMOTE, undersampling) belongs in an `imblearn.pipeline.Pipeline`, which applies it to training folds only; resampled validation data fabricates the metric.
- Feature selection based on correlation with the target is model fitting. Inside the pipeline, always.

## Leakage audits

Run these checks before believing any strong result; a suspiciously good metric is guilty until proven innocent.

- As-of audit: for every feature, write down when its value becomes known relative to the decision time. A feature without a defensible timestamp is rejected.
- Shuffled-target test: retrain on labels randomly permuted. The metric must collapse to chance (AUC ~0.5, R2 ~0); anything better means the pipeline is fitting structure it should not see.
- Dominance check: if one feature carries almost all importance and the metric is near-perfect (AUC > 0.95 on a hard problem), inspect that feature's provenance first.
- Time-inversion check on temporal data: train on the future, test on the past. Scores close to the forward direction suggest the features do not respect time at all.
- Duplicate scan across the split boundary after every new data pull, not just once.

Document the audit result. "No leakage found", with the completed checklist attached, is part of the deliverable. Market-data specifics — survivorship-free universes, point-in-time fundamentals, cost-aware backtests — are validated by `quant_trader`; hand off the feature as-of table with the model.

## Common pitfalls

- Scaler, imputer, or encoder fit on the full dataset, then "the split" done afterward.
- Hand-rolled target mean encoding that includes the row's own label.
- SMOTE applied before splitting, inflating minority-class metrics.
- A backfilled warehouse column treated as if its historical values were point-in-time.
- Feature selection on the whole dataset, then CV on the survivors — the survivors already saw the test labels.
- Accepting a near-perfect metric without running the shuffled-target or dominance checks.
- Declaring "no leakage" without a written per-feature as-of audit.

## Definition of done

- [ ] Every feature audited against the taxonomy, with an as-of timestamp justified per feature.
- [ ] All learned transforms (scaling, imputation, encoding, selection, resampling) live inside a Pipeline and are fit per fold.
- [ ] Target encoding uses internal cross-fitting; no groupby-mean over the training frame.
- [ ] Shuffled-target test run and collapsed to chance level; result recorded.
- [ ] Duplicate and near-duplicate scan run across the split boundary on the current data pull.
- [ ] Dataset-level selection and survivorship bias assessed and documented.
- [ ] Audit checklist attached to the deliverable and logged to project memory; market-data validation handed off to quant_trader.
