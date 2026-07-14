---
name: reproducibility
description: Governs seeds, environment pinning, data versioning, experiment tracking, and run manifests so that any reported number can be regenerated from a commit hash. Use when setting up a training run, auditing GPU determinism, or reviewing whether a reported result can be reproduced.
---

# Reproducibility

This skill governs seeds, environment pinning, data versioning, experiment tracking, and run manifests, so that any reported number can be regenerated from a commit hash. A result that cannot be rerun is an anecdote: an untracked run did not happen.

## Seeds, and their limits on GPU

Seed everything at process start: Python `random.seed`, NumPy (`np.random.default_rng(seed)` — pass the generator around instead of relying on the global state), `torch.manual_seed(seed)` (seeds all CUDA devices too), and `PYTHONHASHSEED` in the environment. Seed DataLoader workers via `worker_init_fn` plus a fixed `generator` so parallel data loading is reproducible; otherwise `num_workers > 0` reshuffles differently per run.

Seeds alone do not make GPU training bit-identical. Nondeterminism also comes from floating-point reduction order in parallel kernels (atomicAdd), cuDNN algorithm autotuning picking different kernels per run, and TF32 matmul defaults on Ampere-class and newer GPUs. For exact runs set:

```python
torch.use_deterministic_algorithms(True)
torch.backends.cudnn.deterministic = True
torch.backends.cudnn.benchmark = False
# plus, in the environment, for deterministic CUDA matmul:
# CUBLAS_WORKSPACE_CONFIG=:4096:8
```

Costs to accept knowingly: throughput typically drops 5 to 15 percent, and some ops have no deterministic implementation and will raise. When exact determinism is too expensive, downgrade the claim honestly: run the configuration across 3 to 5 seeds and report mean and standard deviation — statistical reproducibility, stated as such. What is never acceptable is a single unseeded number.

## Environment pinning

Pin dependencies with a committed lockfile — in this project, `uv.lock`, installed with `uv sync --frozen` in CI so drift fails loudly instead of resolving silently. Record in the run metadata: Python version, framework versions, CUDA and driver versions, and the GPU model; a cuDNN or CUDA minor bump can shift metrics at the third decimal, and you want that explanation available before you chase a ghost regression. For long-lived training jobs, build a container image and record its digest, not its tag.

## Data versioning

The dataset is an input like any other and gets versioned like code:

- Keep raw data immutable; derive, never edit in place.
- Version with content, not filenames: a sha256 manifest of the files, or DVC (3.x) pointers committed to git, so `git checkout` plus `dvc pull` reproduces the exact bytes.
- Record the exact date range, the extraction query, and the commit of the preprocessing code that produced the training table. "The June data" is not a version.
- When the upstream warehouse backfills or corrects history, a new pull is a new dataset version even if the query is identical — snapshot, do not re-query at report time.

## Experiment tracking

Track every training and evaluation run with a tracker — MLflow (3.x) or Weights and Biases — logging: hyperparameters, metrics per epoch/fold, the git commit hash, the dataset version/hash, the lockfile hash, seeds, and artifacts (the winning config, the model file, evaluation plots). In this project, also write the durable summary to project memory (`save_backtest` for backtests, `save_decision` for model choices) so the record survives outside the tracker. The tracker's run id goes in the report; a number without a run id is not reviewable.

## Run manifests

Emit one small JSON manifest per run, saved next to the artifacts and logged to the tracker, capturing in a single place: git sha, config-file path and hash, dataset version, seeds, lockfile hash, hardware (GPU model, count), wall-clock time, and final metrics. The manifest is the contract for reruns: a reviewer resolves it to commands without archaeology. This requires training to be a script driven by a committed config (YAML with a schema, or Hydra) — not hidden notebook state. Notebooks are for exploration; anything whose number appears in a report runs from the CLI.

## Common pitfalls

- Unseeded runs, or a seed set for NumPy but not for the framework or the DataLoader workers.
- Claiming bit-exact reproducibility on GPU without deterministic algorithms enabled, or hiding seed variance behind a single lucky run.
- `pip install` from unpinned requirements at training time; the environment then depends on the install date.
- Dataset referenced by filename or "latest" table instead of a content hash or DVC pointer.
- Re-querying the warehouse at report time and silently picking up backfills.
- Results produced by a notebook whose cells were run out of order.
- Metrics reported without a tracker run id or manifest, so the provenance chain breaks at the first question.

## Definition of done

- [ ] All RNGs seeded (Python, NumPy, framework, CUDA, DataLoader workers) and the seeds recorded.
- [ ] Determinism level stated explicitly: bit-exact (deterministic flags on) or statistical (mean and std across 3 to 5 seeds).
- [ ] Dependencies installed from the committed lockfile; Python, framework, CUDA, driver, and GPU model recorded.
- [ ] Dataset versioned by content hash or DVC pointer, with date range and preprocessing commit recorded; raw data immutable.
- [ ] Run logged to the experiment tracker with params, metrics, git sha, dataset hash, and artifacts; summary written to project memory.
- [ ] Run manifest emitted with git sha, config hash, data version, seeds, lock hash, hardware, and final metrics.
- [ ] Training runs as a config-driven script; a reviewer can rerun it from the manifest and match the reported numbers.
