## Hyperparameters and tuning


- Search with a tracked, reproducible method: Optuna or `RandomizedSearchCV` over a defined space; log every trial. Grid search only for small discrete spaces.
- Tune against CV folds, never against the final holdout.
- Use early stopping on a validation metric for gradient-boosted trees and neural nets; record the chosen iteration/epoch.
- Guard against overfitting: regularization (L1/L2, dropout, weight decay), max depth / min child weight limits, and a gap check between train and validation metrics. A large train-minus-validation gap means the model memorized.
- Save the winning configuration as a committed file (YAML/JSON), not as ad hoc notebook state.
