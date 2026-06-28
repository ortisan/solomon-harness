## Data leakage prevention


Audit every feature against this list. Any hit is a defect:

- Target leakage: a feature computed from, or a proxy of, the label (including future-aggregated stats, post-event fields).
- Temporal leakage: using information not available at prediction time. For each feature confirm its as-of timestamp <= the decision time. Lag/shift everything that is only known later.
- Train/test contamination: scaling, imputation, target encoding, resampling (SMOTE), or feature selection fit across the split.
- Duplicate or near-duplicate rows spanning splits; grouped entities split across folds.
- Look-ahead in indicators: rolling windows, normalization, or labels that peek forward (e.g. centered windows, label computed over a horizon that overlaps the next split).
- Survivorship and selection bias in the dataset itself (delisted instruments removed, only successful entities retained).

Document the audit result. "No leakage found" with the checklist attached is part of the deliverable.
