## Reproducibility


- Seed everything: Python `random`, `numpy`, framework RNG (`torch.manual_seed`, `cuda` seeds), and set `PYTHONHASHSEED`. Seed DataLoader workers via `worker_init_fn` and a fixed `generator` so parallel data loading is reproducible. For exact runs set deterministic flags (`torch.use_deterministic_algorithms(True)`, `cudnn.deterministic=True`, `cudnn.benchmark=False`, and `CUBLAS_WORKSPACE_CONFIG=:4096:8` for deterministic CUDA matmul); note the throughput cost.
- Pin dependencies (lockfile) and record framework, CUDA, and hardware in the run metadata.
- Version the data: hash or version-tag the dataset and record the exact date range and preprocessing commit.
- Track runs with the hyperparameters, metrics, dataset version, and config for every experiment (the project memory `save_backtest` / `save_decision`, or an MLflow/W&B-style logger). An untracked run did not happen.
- Make training a script driven by a committed config, not hidden notebook state, so a reviewer can rerun it and get the same numbers.
