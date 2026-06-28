# Machine Learning Validation

Purpose: Validate model performance, prevent data leakage, and ensure generalization.

## Core Rules

1. Avoid Data Leakage
   - Split dataset partitions (train, validation, test) before executing scaling, normalization, imputation, or feature engineering steps.

2. Generalization Verification
   - Always evaluate models using cross-validation (e.g. k-fold) and separate, untouched out-of-sample datasets to guarantee real-world generalization.

3. Metric Alignment
   - Select and optimize validation metrics aligned with business objectives (e.g. optimizing precision for high-cost false alarms, recall for safety-critical failures, ROC-AUC for balanced classification classification thresholds).
