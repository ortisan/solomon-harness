## Data splitting and cross-validation


- Split before you do anything else: fit scalers, encoders, imputers, and feature selection on the training fold only, then apply to validation and test. Fitting any transform on the full dataset is leakage.
- For time series and market data, never use random K-fold. Use walk-forward / expanding-window CV or `sklearn.model_selection.TimeSeriesSplit`. Add an embargo/purge gap between train and test (purged K-fold, Lopez de Prado) so a sample's label horizon cannot overlap the test window.
- Keep a final out-of-sample (and ideally out-of-time) holdout that is opened once, at the end. If you tune against it, it is no longer out-of-sample.
- Group-aware splits (`GroupKFold`) when rows share an entity (user, instrument, session) so the same group never spans train and test.
- Report mean and standard deviation across folds, not a single lucky split. A model whose fold-to-fold metric variance is large is not robust.
