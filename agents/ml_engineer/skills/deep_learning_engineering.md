---
name: deep-learning-engineering
description: Governs training deep networks that converge and reproduce, covering architecture selection by data size, PyTorch 2.x compile and mixed-precision discipline, AdamW with warmup-plus-cosine schedules, the regularization ladder, and the overfit-one-batch smoke test. Use when designing, training, or debugging a neural network in PyTorch, or reviewing a training run for convergence and reproducibility.
---

# Deep Learning Engineering

This skill governs how deep networks are architected, trained, and checkpointed so that they converge on the first serious run and every reported number can be regenerated from config. A training run that diverges, silently underfits, or cannot be reproduced is a process failure, not bad luck; the defaults below are the ones that work before any tuning.

## Architecture selection by data shape and size

Pick the architecture from the data, not from fashion:

- Tabular, under roughly 100k rows: gradient boosting (LightGBM, XGBoost) is the bar a deep model must beat; an MLP (2-4 hidden layers, 128-512 units, residual connections past 3 layers) is the deep option only when embeddings of high-cardinality categoricals or multi-task heads justify it.
- Images and other locally structured grids: CNNs (a ResNet-family backbone) remain the sane default below about 1M images; Vision Transformers need that scale or heavy augmentation plus pretraining to match them.
- Sequences: a GRU/LSTM is the right call for short sequences and small datasets (under ~100k sequences); Transformers win with long-range dependencies and data at the 100k-plus scale, at quadratic attention cost in sequence length.
- Parameter budget: keep trainable parameters within about one order of magnitude of the number of training samples unless pretraining or strong augmentation closes the gap. A 10M-parameter model on 5k rows memorizes; the validation curve will say so early if you look.

Fine-tuning a pretrained backbone beats training from scratch whenever a relevant one exists; freezing all but the head is the cheapest first experiment.

## PyTorch 2.x training discipline

- Wrap the model with `torch.compile(model)` for long runs; expect first-step compile latency and use `mode="reduce-overhead"` for small models where kernel launch overhead dominates. Disable it while debugging shapes — tracebacks are clearer eager.
- Mixed precision: prefer bfloat16 on Ampere-class and newer GPUs — `with torch.autocast("cuda", dtype=torch.bfloat16):` — which needs no loss scaling. On fp16 hardware, use `torch.amp.GradScaler` with the standard `scaler.scale(loss).backward(); scaler.step(optimizer); scaler.update()` sequence. Dtype, epsilon, and finiteness rules live in `tensor_shape_and_numerical_safety_checks`; apply them, do not restate them.
- DataLoader: `num_workers=4-8`, `pin_memory=True`, `persistent_workers=True`, and `prefetch_factor=2` as the starting point; a GPU below ~85 percent utilization during training usually means the input pipeline, not the model, is the bottleneck.

## Optimization defaults that work

- Optimizer: AdamW with `lr=3e-4`, `betas=(0.9, 0.999)`, `weight_decay=0.01` (up to 0.1 for Transformers). Exclude biases and normalization parameters from weight decay via parameter groups.
- Schedule: linear warmup over 1-5 percent of total steps, then cosine decay to ~1e-6 (`torch.optim.lr_scheduler.OneCycleLR` covers both in one object for fixed-length runs). Skipping warmup is the most common cause of an early loss spike with Adam-family optimizers.
- Gradient clipping: `clip_grad_norm_(model.parameters(), max_norm=1.0)` every step, with the pre-clip norm logged; per `tensor_shape_and_numerical_safety_checks`, a trending norm is the earliest instability signal.

## The regularization ladder

Add regularization in order of return on effort, one rung at a time, measuring validation effect at each step: (1) more or better data, then domain-valid augmentation (flips and crops for images, jitter and window-warping for time series — never augmentation that breaks causality); (2) dropout 0.1 on Transformers, 0.2-0.5 on MLP hidden layers; (3) label smoothing 0.1 for classification (`F.cross_entropy(..., label_smoothing=0.1)`); (4) early stopping on a real validation set — constructed per `data_splitting_and_cross_validation`, never a random slice of temporal data — with patience of ~10 evaluations on the primary metric.

## Overfit one batch before any long run

Before committing GPU-days, drive the loss to ~0 on a single batch (32-64 samples, a few hundred steps, no regularization). Failure means a bug — wrong loss, broken labels, frozen weights, a shape error broadcasting silently — that no amount of training will fix. This smoke test plus a one-epoch throughput measurement is the mandatory preflight; a long run launched without it is a review defect.

## Determinism, checkpointing, and tracking

Seed everything at process start (`torch.manual_seed`, NumPy, Python, `PYTHONHASHSEED`) and set `torch.backends.cudnn.deterministic = True`, `benchmark = False` for runs whose numbers will be reported; log the seed in the run record. The full determinism policy, its GPU limits, and environment pinning live in `reproducibility` — this skill only requires that every run comply with it.

Checkpoint atomically (write to a temp file, then rename) and include model, optimizer, scheduler, and scaler state dicts plus epoch, global step, and RNG states; keep `last.pt` and `best.pt` by the validation metric. Every run is tracked (MLflow, W&B, or the project's run manifest) with its full config, git commit, data version, and metrics, so that any result reproduces from config plus commit hash.

## Common pitfalls

- No warmup with AdamW, producing an early loss spike that gets misread as a data problem.
- Weight decay applied to biases and LayerNorm parameters because parameter groups were skipped.
- A long run launched without the overfit-one-batch test, burning GPU-days on a wiring bug.
- Validation set carved randomly from temporal data, making early stopping select the most-leaked checkpoint.
- fp16 autocast without GradScaler, or bf16 assumed on hardware that lacks it, giving NaN losses blamed on the model.
- `torch.compile` left on while debugging a shape error, obscuring the faulting line.
- Checkpoints holding only model weights, so a resumed run replays the warmup schedule at the wrong step.
- GPU utilization never measured, so weeks of "slow training" trace back to `num_workers=0`.

## Definition of done

- [ ] Architecture choice justified against data size and shape, with the parameter budget stated next to the sample count.
- [ ] Overfit-one-batch test passed and its result recorded before the first long run.
- [ ] AdamW parameter groups exclude biases and normalization weights from decay; warmup plus cosine or one-cycle schedule configured.
- [ ] Gradient norm clipped at max_norm ~1.0 and logged per `tensor_shape_and_numerical_safety_checks`.
- [ ] Regularization added rung by rung with validation deltas recorded; early stopping runs on a split that respects `data_splitting_and_cross_validation`.
- [ ] Mixed-precision policy declared (bf16 or fp16 plus GradScaler) and the input pipeline profiled.
- [ ] Seeds set and logged; determinism flags set for reported runs per `reproducibility`.
- [ ] Atomic checkpoints carry optimizer, scheduler, scaler, and RNG state; the run is tracked with config, commit, and data version.
