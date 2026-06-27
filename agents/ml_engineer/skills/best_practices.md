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

## Model Hypothesis (state before training)

Write this down first. For trading and DRL models it is mandatory and must include:

- Target Sharpe ratio (annualized). Default acceptance bar: out-of-sample Sharpe >= 1.5; reject anything below 1.0.
- Maximum drawdown limit, e.g. <= 20% on the OOS window. State the figure and enforce it.
- Profit factor target: >= 1.3 OOS (gross profit / gross loss). Below 1.0 is a losing model, discard it.
- Latency and slippage constraints: inference latency budget (e.g. < 50 ms p99) and the slippage/transaction-cost model assumed (e.g. 2 bps per side plus spread). Backtests without costs are invalid.
- Dataset and features: exact source, date range, sampling frequency, and the feature list with how each is computed.
- Network or model architecture: layer sizes, activations, loss, optimizer, and the action/observation spaces for RL.

For non-trading models, keep the equivalent: primary metric and acceptance threshold, the baseline you must beat, latency budget, dataset/feature spec, and architecture. A model that does not beat a documented naive baseline (persistence, mean, majority class) is not shippable.

## Data splitting and cross-validation

- Split before you do anything else: fit scalers, encoders, imputers, and feature selection on the training fold only, then apply to validation and test. Fitting any transform on the full dataset is leakage.
- For time series and market data, never use random K-fold. Use walk-forward / expanding-window CV or `sklearn.model_selection.TimeSeriesSplit`. Add an embargo/purge gap between train and test (purged K-fold, Lopez de Prado) so a sample's label horizon cannot overlap the test window.
- Keep a final out-of-sample (and ideally out-of-time) holdout that is opened once, at the end. If you tune against it, it is no longer out-of-sample.
- Group-aware splits (`GroupKFold`) when rows share an entity (user, instrument, session) so the same group never spans train and test.
- Report mean and standard deviation across folds, not a single lucky split. A model whose fold-to-fold metric variance is large is not robust.

## Data leakage prevention

Audit every feature against this list. Any hit is a defect:

- Target leakage: a feature computed from, or a proxy of, the label (including future-aggregated stats, post-event fields).
- Temporal leakage: using information not available at prediction time. For each feature confirm its as-of timestamp <= the decision time. Lag/shift everything that is only known later.
- Train/test contamination: scaling, imputation, target encoding, resampling (SMOTE), or feature selection fit across the split.
- Duplicate or near-duplicate rows spanning splits; grouped entities split across folds.
- Look-ahead in indicators: rolling windows, normalization, or labels that peek forward (e.g. centered windows, label computed over a horizon that overlaps the next split).
- Survivorship and selection bias in the dataset itself (delisted instruments removed, only successful entities retained).

Document the audit result. "No leakage found" with the checklist attached is part of the deliverable.

## Hyperparameters and tuning

- Search with a tracked, reproducible method: Optuna or `RandomizedSearchCV` over a defined space; log every trial. Grid search only for small discrete spaces.
- Tune against CV folds, never against the final holdout.
- Use early stopping on a validation metric for gradient-boosted trees and neural nets; record the chosen iteration/epoch.
- Guard against overfitting: regularization (L1/L2, dropout, weight decay), max depth / min child weight limits, and a gap check between train and validation metrics. A large train-minus-validation gap means the model memorized.
- Save the winning configuration as a committed file (YAML/JSON), not as ad hoc notebook state.

## Tensor-shape and numerical-safety checks

Before any matmul, reshape, broadcast, loss, or reward computation:

- Assert shapes explicitly: `assert x.shape == (batch, features), x.shape`. Prefer named checks at function boundaries over silent broadcasting. Validate batch dimension alignment and that contraction dims match.
- Divide-by-zero: never divide by a raw denominator. Add epsilon (`1e-8`) or use `np.divide(..., where=denom!=0)`. This covers Sharpe (zero variance), returns normalization, and softmax/logit denominators.
- Overflow and invalid values: clip logits and rewards to sane ranges, and use numerically stable primitives. Prefer framework `F.cross_entropy`/`F.log_softmax` over a hand-rolled softmax-then-log, use `log1p`/`expm1` for small values, and standardize inputs. Run `torch.isnan/isinf` (or `np.isfinite`) checks on inputs, loss, and gradients during training; fail fast on a non-finite loss.
- Gradient safety: clip gradient norm (e.g. `clip_grad_norm_` at 1.0), watch for exploding/vanishing gradients, and assert the loss is a finite scalar before `backward()`.
- Dtype and device discipline: keep a consistent dtype (float32 unless you have a reason), confirm tensors share a device before ops, and avoid silent int/float casts that truncate.
- Validate that probabilities sum to 1 (within tolerance) and that bounded outputs stay in range.

## Reproducibility

- Seed everything: Python `random`, `numpy`, framework RNG (`torch.manual_seed`, `cuda` seeds), and set `PYTHONHASHSEED`. Seed DataLoader workers via `worker_init_fn` and a fixed `generator` so parallel data loading is reproducible. For exact runs set deterministic flags (`torch.use_deterministic_algorithms(True)`, `cudnn.deterministic=True`, `cudnn.benchmark=False`, and `CUBLAS_WORKSPACE_CONFIG=:4096:8` for deterministic CUDA matmul); note the throughput cost.
- Pin dependencies (lockfile) and record framework, CUDA, and hardware in the run metadata.
- Version the data: hash or version-tag the dataset and record the exact date range and preprocessing commit.
- Track runs with the hyperparameters, metrics, dataset version, and config for every experiment (the project memory `save_backtest` / `save_decision`, or an MLflow/W&B-style logger). An untracked run did not happen.
- Make training a script driven by a committed config, not hidden notebook state, so a reviewer can rerun it and get the same numbers.

## Testing (QA discipline applies here)

- Unit-test feature transforms, the split logic (assert no index overlap between train and test), and metric functions against known inputs.
- Integration-test the train -> evaluate path end to end on a small fixture.
- Mock all external services and data feeds: no live API, exchange, or database calls in tests. Make randomness deterministic in tests via fixed seeds.
- Add explicit tests for backtest logic and parameters: cost/slippage applied, no look-ahead, correct position sizing, P&L reconciles.
- Add regression tests that fail if a known leakage pattern reappears (e.g. a transform fit on the full set).

## Common pitfalls to reject in review

- Random K-fold on time-ordered data.
- Scaler or encoder fit before the split.
- Backtest Sharpe reported without transaction costs or slippage.
- A single train/test split presented as if it were cross-validation.
- Reusing the holdout for model selection.
- Silent `NaN`/`inf` in loss masked by `nan_to_num` instead of fixing the cause.
- Unseeded runs whose numbers cannot be reproduced.
- Metrics quoted without fold variance or a baseline comparison.

## Definition of done

- [ ] Model Hypothesis committed with target Sharpe, drawdown limit, profit factor, latency/slippage, dataset/features, and architecture (or the non-trading equivalent with baseline and acceptance threshold).
- [ ] Time-aware or group-aware cross-validation done; mean and std reported across folds.
- [ ] Out-of-sample (and out-of-time) holdout evaluated exactly once and meets the acceptance thresholds.
- [ ] Leakage checklist completed with no open findings.
- [ ] Shape asserts plus divide-by-zero, overflow, and non-finite guards on all critical ops; loss verified finite during training.
- [ ] Seeds fixed, dependencies pinned, dataset version and config recorded; run logged to project memory.
- [ ] Unit and integration tests pass with all external services mocked; backtest-logic tests included.
- [ ] Beats the documented baseline and respects the latency budget.
