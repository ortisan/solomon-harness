## Tensor-shape and numerical-safety checks


Before any matmul, reshape, broadcast, loss, or reward computation:

- Assert shapes explicitly: `assert x.shape == (batch, features), x.shape`. Prefer named checks at function boundaries over silent broadcasting. Validate batch dimension alignment and that contraction dims match.
- Divide-by-zero: never divide by a raw denominator. Add epsilon (`1e-8`) or use `np.divide(..., where=denom!=0)`. This covers Sharpe (zero variance), returns normalization, and softmax/logit denominators.
- Overflow and invalid values: clip logits and rewards to sane ranges, and use numerically stable primitives. Prefer framework `F.cross_entropy`/`F.log_softmax` over a hand-rolled softmax-then-log, use `log1p`/`expm1` for small values, and standardize inputs. Run `torch.isnan/isinf` (or `np.isfinite`) checks on inputs, loss, and gradients during training; fail fast on a non-finite loss.
- Gradient safety: clip gradient norm (e.g. `clip_grad_norm_` at 1.0), watch for exploding/vanishing gradients, and assert the loss is a finite scalar before `backward()`.
- Dtype and device discipline: keep a consistent dtype (float32 unless you have a reason), confirm tensors share a device before ops, and avoid silent int/float casts that truncate.
- Validate that probabilities sum to 1 (within tolerance) and that bounded outputs stay in range.
