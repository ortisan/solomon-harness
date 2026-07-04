# Tensor-Shape and Numerical-Safety Checks

This skill governs shape assertions, dtype discipline, and numerical guards around every matmul, reshape, broadcast, loss, and reward computation. Silent broadcasting and non-finite values are the two ways a model trains to convergence on garbage; both are cheap to catch at the boundary and expensive to catch in production.

## Shape assertions at function boundaries

Assert shapes explicitly where tensors enter and leave a function; prefer a named check over trusting broadcasting:

```python
def score(x: torch.Tensor, w: torch.Tensor) -> torch.Tensor:
    assert x.ndim == 2 and x.shape[1] == w.shape[0], (x.shape, w.shape)
    ...
```

- Use einops (0.8.x) for rearrangement: `rearrange(x, "b t (h d) -> b h t d", h=heads)` documents intent and raises on mismatch, unlike `view`/`reshape`, which happily reinterpret the wrong buffer. `reduce(x, "b t d -> b d", "mean")` beats an unlabeled `x.mean(1)`.
- For signatures, jaxtyping annotations (`Float[Tensor, "batch seq dim"]`) checked at runtime with beartype turn shape contracts into enforced types on the hot paths that matter; enable them in tests at minimum.
- Never rely on implicit broadcasting for rank changes: write the `unsqueeze`/`expand` explicitly. The classic silent bug is `(n,) - (n,1)` producing `(n,n)` and a loss that still "works". Validate batch-dimension alignment and that contraction dims match before `matmul`/`einsum`.

## Dtype discipline: float32 versus float64

Default to float32 for training; it is the hardware-native dtype and halves memory versus float64. Use float64 deliberately where accumulation error compounds: long-running sums, covariance/variance of large samples, metric aggregation over millions of rows, and money. NumPy defaults to float64 and PyTorch to float32 — a pipeline crossing both must convert explicitly or it will silently mix precisions.

For mixed precision, prefer bfloat16 over float16: bf16 keeps float32's exponent range, so overflow guards rarely trigger; fp16 (max ~65504, min normal ~6e-5) needs `torch.amp.GradScaler` and overflows a hand-rolled softmax easily. Epsilons must match the dtype: `1e-8` is fine in fp32 but flushes toward zero in fp16 — use `1e-6` or larger where half-precision tensors flow. Avoid silent int/float casts that truncate (integer division, indexing arithmetic), and confirm tensors share a device before ops; a stray CPU tensor in a CUDA graph costs a sync per step when it does not simply crash.

## NaN/inf guards: fail fast

Check finiteness at three points — inputs at ingestion, the loss every step, gradients when debugging — and fail fast on violation:

```python
loss = criterion(logits, target)
assert loss.ndim == 0 and torch.isfinite(loss), f"non-finite loss: {loss}"
loss.backward()
```

`torch.nan_to_num` on a loss or reward is masking, not fixing: it converts a detectable failure into a silent bias, and it is grounds for review rejection. Reserve `torch.autograd.set_detect_anomaly(True)` for debugging sessions only (it traces every op and slows training by an order of magnitude); in production training, log `torch.isfinite` checks on inputs and loss, and stop the run on the first hit.

## Numerically stable primitives

- Divide-by-zero: never divide by a raw denominator. Add a dtype-appropriate epsilon or use `np.divide(a, b, out=..., where=b != 0)`. This covers Sharpe on a zero-variance window, returns normalization, and softmax/logit denominators.
- Log-sum-exp: never compute `log(sum(exp(x)))` directly — `exp` overflows fp32 at x ~ 88.7. Use `torch.logsumexp` / `scipy.special.logsumexp`, which shift by the max first.
- Prefer framework-fused losses: `F.cross_entropy` / `F.log_softmax` over a hand-rolled softmax-then-log; `F.binary_cross_entropy_with_logits` over sigmoid-then-BCE. The fused forms are the stable forms.
- Use `log1p`/`expm1` for values near zero; clamp inputs to `log` and `sqrt` (`x.clamp_min(eps)`); standardize inputs so activations start in a sane range; clip logits and rewards to declared bounds in RL, where one exploding reward corrupts the return estimate.

## Gradient safety

Clip the global gradient norm every step — `torch.nn.utils.clip_grad_norm_(model.parameters(), max_norm=1.0)` after `backward()` and before `step()` — and log the pre-clip norm: a rising trend flags instability before the loss shows it, and a norm collapsing toward zero flags vanishing gradients or a dead head. The loss must be a finite scalar before `backward()` (assert both, as above).

## Output validation

Validate model outputs against their contracts: probabilities sum to 1 within 1e-5 and lie in [0, 1]; bounded regressors and RL actions stay inside their declared ranges; count-like outputs are non-negative. These checks belong in the evaluation harness and in unit tests (see `testing_qa_discipline_applies_here`), not just in ad hoc notebook cells.

## Common pitfalls

- Silent `(n,) - (n,1) -> (n,n)` broadcasting producing a plausible but wrong loss.
- `reshape`/`view` used where a labeled einops `rearrange` would have caught a mismatched layout.
- `nan_to_num` (or `errstate(all="ignore")`) hiding a non-finite loss instead of fixing its cause.
- Hand-rolled softmax/log-softmax overflowing where the fused primitive was available.
- fp16 training without GradScaler, or an `eps=1e-8` that underflows in half precision.
- Raw division by variance, norm, or count that can be zero.
- No gradient-norm clipping or logging on a recurrent or RL model.
- Mixing NumPy float64 with Torch float32 and losing or gaining precision silently.

## Definition of done

- [ ] Shape assertions or runtime-checked jaxtyping annotations at every public function boundary; einops used for nontrivial rearrangements.
- [ ] Dtype policy declared (fp32 default, fp64 for sensitive accumulations, bf16/fp16 policy with scaler); no implicit cross-library dtype mixing.
- [ ] Epsilons sized to the dtype; no raw division by a possibly-zero denominator.
- [ ] Stable primitives used: logsumexp, fused cross-entropy/BCE-with-logits, log1p/expm1, clamped log/sqrt inputs.
- [ ] Finiteness checks on inputs and loss with fail-fast behavior; no nan_to_num masking; anomaly mode confined to debugging.
- [ ] Gradient norm clipped (max_norm ~1.0) and logged; loss asserted to be a finite scalar before backward.
- [ ] Output contracts validated: probability simplex within 1e-5, bounded outputs in range, devices consistent.
