# DRL and ML Safety and Robustness

Trading models fail numerically (shapes, NaNs, overflow) and behaviorally (reward hacking, leaked features, cherry-picked seeds), and this skill sets the guards for both: validate tensors at boundaries, keep every denominator and exponent finite, prove the reward measures the real objective, bound the action space inside the environment, control seeds, and evaluate on held-out regimes.

## Tensor-shape validation

- Assert shapes at every component boundary — feature builder to model, model to environment, environment to replay buffer — before critical operations: matmul, reshape, concatenation, batched env steps. Trusting broadcasting is how a `(batch, 1)` meets a `(batch,)` and silently trains on garbage.
- Prefer declared shapes over comments: jaxtyping annotations enforced with beartype, or a plain assertion at the top of `step` and `forward`:

```python
assert obs.shape == (batch, n_features), f"obs {obs.shape} != {(batch, n_features)}"
```

- Validate once per batch at boundaries, not per element inside hot loops; the goal is fail-fast, not overhead.

## NaN and inf guards

- Division: every denominator in returns, Sharpe, drawdown, and normalization gets an epsilon floor or an explicit branch — `vol = max(vol, 1e-8)` — never a silent inf. A zero-volatility window is a real market condition (halts, illiquid sessions), not a hypothetical.
- Overflow: compound in log-space (`np.log1p(r).sum()` then `np.expm1`), clip log-returns and rewards to sane bounds, and cap exponentials before they meet float32.
- Detection: check `torch.isfinite(loss)` every training step and halt on failure; use `torch.autograd.set_detect_anomaly(True)` while debugging (too slow for production runs); run numpy test suites under `np.errstate(all="raise")`.
- Ingestion: reject or impute NaN observations before they reach the model, and never let a bar containing imputed values produce a trade without an explicit flag.

## Reward-hacking checks

The agent optimizes the reward you wrote, not the PnL you meant.

- The reward must be risk-adjusted return net of transaction costs, computed inside the environment. A cost-free reward trains the agent to overtrade, because churn is free alpha to it.
- Penalize turnover and inventory explicitly when the cost model alone does not curb them.
- Reconciliation test: cumulative reward and the account's net PnL must track each other (correlation near 1, never opposite in sign over an episode). Divergence means the agent found a seam in the environment's accounting.
- Baselines: run a random-action agent and buy-and-hold through the identical environment. The trained agent must beat both net of costs; a random agent showing profit means the environment leaks or misprices.
- Audit the classic seams: marking fills to the same bar's close (self-fulfilling rewards), zero-spread position flips, and rewards on unrealized PnL with no cost of exit.

## Action-space sanity

- Bound actions in the environment, not only in the policy: clip target positions to the risk caps inside `step`, so no policy output — and no checkpoint restored without its wrapper — can breach limits.
- Map raw actions to target positions with a maximum per-step change; a flip from full-long to full-short in one step must be impossible unless the strategy's premise requires it and full costs are charged for it.
- Refuse to act on bad state: stale or NaN observations produce hold or flatten, never a trade.
- Keep the space small and interpretable (discrete {-1, 0, +1} or a bounded continuous target weight); exotic action spaces make reward hacking easier and diagnosis harder.

## Seed control and held-out regime evaluation

- Fix seeds across python, numpy, the ML framework, and the environment in one place; enable `torch.use_deterministic_algorithms(True)` for validation runs.
- Train and evaluate with at least 5 seeds and report mean and standard deviation of net OOS metrics. Selecting the best seed is a multiple-testing trial and must be counted as one (see the overfitting skill).
- Split by time and evaluate on regimes absent from training (see the regime skill): a policy trained on 2016-2019 calm must be scored on 2020, 2022, and later stress windows, with per-regime metrics, not just an aggregate.
- Feature hygiene carries over from supervised work: fit scalers, PCA, and feature selection on training folds only; prefer returns or fractionally differentiated series over raw prices and confirm stationarity with an ADF unit-root test; for supervised entries, use triple-barrier labels and meta-labeling, and size positions separately from the directional signal.

## Common pitfalls

- Trusting broadcasting across a `(batch, 1)` vs `(batch,)` mismatch; the run trains, the numbers are garbage.
- Epsilon-free denominators meeting a zero-volatility halt window in live data.
- Cost-free or gross-PnL rewards: the agent learns to overtrade by design.
- Reward accounting a random agent can profit from — an environment bug interpreted as alpha.
- One golden seed in the report, five dead seeds in the drawer.
- Smoothed HMM states or full-sample-scaled features in the observation vector: lookahead smuggled in through preprocessing.
- Action clipping only in the policy wrapper, so a checkpoint restored without the wrapper trades unbounded.

## Definition of done

- [ ] Shape assertions (or jaxtyping plus beartype) at all component boundaries; a wrong shape fails fast with the offending shape in the message.
- [ ] All denominators epsilon-floored or branched; compounding in log-space; `isfinite` checks halt training; NaN observations cannot produce trades.
- [ ] Reward is net-of-cost and risk-adjusted inside the environment; reward-vs-PnL reconciliation passes; random-agent and buy-and-hold baselines run and beaten.
- [ ] Action bounds and a maximum per-step position change enforced inside `step`; bad state yields hold or flatten.
- [ ] Seeds fixed and deterministic ops enabled for validation; at least 5 seeds reported as mean +/- std; best-seed selection counted as a trial.
- [ ] Evaluation covers held-out time and held-out regimes with per-regime metrics; feature pipeline fits on training folds only; stationarity confirmed with a unit-root test.
