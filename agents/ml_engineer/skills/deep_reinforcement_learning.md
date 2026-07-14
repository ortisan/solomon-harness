---
name: deep-reinforcement-learning
description: Governs when deep reinforcement learning is warranted and how it is applied, covering Gymnasium environment design, cost-inclusive reward engineering, PPO/SAC/DQN selection with the hyperparameters that matter, and multi-seed evaluation against random and buy-and-hold baselines. Use when proposing, building, or evaluating a DRL agent, especially in a trading environment.
---

# Deep Reinforcement Learning

This skill governs when DRL is the right tool and how it is applied when it is: environment design, reward engineering, algorithm defaults, and an evaluation protocol strict enough to survive the field's reputation for unreproducible results. DRL is the highest-variance technique in the toolbox — treat every trained agent as a hypothesis to be falsified, not a product to be shipped.

## When DRL is warranted at all

Use DRL only when the problem has sequential decisions whose actions change the future state or the data the agent sees next, and feedback arrives as a scalar signal rather than labels. If the decision is a one-step prediction, use supervised learning; if the optimal policy can be written down (threshold rules, inventory bands, a deterministic rebalance), implement the rule and skip learning entirely. The burden of proof runs against DRL: it demands orders of magnitude more samples than supervised learning, its results vary heavily across seeds, and its failure modes are silent. A DRL proposal must state why the sequential-feedback structure is essential and why the best deterministic rule is insufficient — otherwise reject the approach at the design stage, which is cheaper than at the evaluation stage.

## Environment design against the Gymnasium API

Build environments on Gymnasium 1.x: `reset(seed=...)` returns `(obs, info)`, `step(action)` returns `(obs, reward, terminated, truncated, info)`. Keep the `terminated` (MDP-end: bankruptcy, episode goal) and `truncated` (time-limit cutoff) distinction honest — conflating them corrupts bootstrapped value targets. Declare spaces exactly: `spaces.Box(low, high, shape, dtype=np.float32)` for continuous observations with real bounds, `spaces.Discrete(n)` for small action sets. Run `gymnasium.utils.env_checker.check_env(env)` in the test suite. Define episode boundaries from the problem (a trading day, a fixed horizon), not from arbitrary buffer sizes, and use `gymnasium.vector.AsyncVectorEnv` (or SB3 `SubprocVecEnv`) with 8-16 copies to feed on-policy algorithms. Normalize observations (running mean/std, as in `VecNormalize`) and persist the normalization statistics with the checkpoint — a policy restored without them acts on garbage.

## Reward design: the highest-risk surface

The agent optimizes the reward you wrote, not the objective you meant, and it will find every seam. Rules:

- All cost terms live inside the reward, computed in `step`: transaction costs (per-side bps plus spread), and risk penalties such as a drawdown term (for example, reward = delta log equity minus lambda times new drawdown, with lambda tuned so the penalty binds). Costs bolted on after training produce a policy optimized for a world without them; it overtrades by construction.
- Keep the reward dense enough to learn from but derived from the true objective; shaping terms must provably not change the optimal policy (potential-based shaping) or be removed before final evaluation.
- Reconcile cumulative reward against the account's net PnL every evaluation; divergence means the agent is farming an accounting seam, per `quant_trader`'s safety standards.
- Clip rewards to declared bounds and guard the arithmetic per `tensor_shape_and_numerical_safety_checks`.

## Algorithm selection and the hyperparameters that move results

Default to PPO (stable-baselines3 2.x) — it is the most robust to hyperparameters and works for discrete and continuous actions. Use SAC for continuous control where sample efficiency matters, and double/dueling DQN only for small discrete action spaces. The knobs that actually change outcomes:

- `n_steps` times `n_envs` (PPO rollout size): 2048x8 as a start; too small gives noisy advantage estimates, too large stales the policy. `batch_size` 64-256 must divide the rollout.
- Entropy coefficient `ent_coef`: 0.0-0.01; raise it when the policy collapses early to a degenerate action (in trading, permanently flat or permanently long).
- `gamma` versus horizon: effective horizon is roughly 1/(1-gamma), so gamma=0.99 sees ~100 steps and 0.999 sees ~1000 — set it from the decision horizon in environment steps, not by habit.
- Learning rate 3e-4 with linear decay; `clip_range` 0.2; `gae_lambda` 0.95. For SAC: `tau=0.005`, replay buffer ~1e6, `learning_starts` ~10k.

## Evaluation protocol

Train and evaluate at least 5 seeds and report mean and dispersion (standard deviation, or interquartile mean for heavy-tailed results); a single-seed result is an anecdote and best-seed selection is a multiple-testing trial. Evaluate in a separate environment instance the agent never trained on, with the deterministic policy, on a schedule (SB3 `EvalCallback`). Mandatory baselines through the identical environment and cost model: a random-action agent (a profitable random agent means the environment leaks), buy-and-hold, and the best deterministic rule from the design stage. The trained agent must beat all three net of costs, across seeds, or the honest outcome is a documented negative result.

## Trading-specific hazards

A DRL trading agent overfits to its simulator, not to the market. Split data by time and regime — train, validation, and test windows covering distinct volatility and trend regimes, with tuning decisions taken on validation only. Enforce the no-lookahead rule on every observation field (as-of audit per `data_leakage_prevention`), including normalization statistics fit on training data only. Name the sim-to-live gaps explicitly: fill assumptions, latency, market impact absent from the simulator, and regime drift after the data ends. A trained agent is a hypothesis; the live-readiness verdict — backtest standards, cost realism, capacity — belongs to `quant_trader`, and this agent's builder never grades their own strategy.

## Common pitfalls

- DRL applied to a one-step prediction problem where supervised learning fits the structure, wasting samples and adding seed variance for nothing.
- `terminated` and `truncated` conflated, corrupting value bootstrapping at time limits.
- Cost-free reward, so the policy learns to overtrade; costs added only in the backtest afterward.
- Reward shaping left in the final evaluation, so the reported score measures the shaping, not the objective.
- One golden seed reported, the other seeds unmentioned — the field's classic reproducibility failure.
- Baselines skipped; a random agent would have exposed the environment leak the "alpha" came from.
- Observation normalization statistics not saved with the checkpoint, so the restored policy misbehaves silently.
- Gamma chosen by convention rather than from the decision horizon, making the agent myopic or noise-driven.

## Definition of done

- [ ] Written justification that the problem is sequential-feedback and the best deterministic rule is insufficient, pre-registered per `model_hypothesis_state_before_training`.
- [ ] Environment passes `check_env`; spaces, episode boundaries, and terminated/truncated semantics documented and tested.
- [ ] Reward includes transaction costs and risk penalties inside `step`; reward-versus-PnL reconciliation passes.
- [ ] Algorithm and hyperparameters recorded (rollout size, batch size, ent_coef, gamma with its horizon rationale, learning rate and schedule).
- [ ] At least 5 seeds trained; mean and dispersion reported; evaluation ran in a separate environment with the deterministic policy.
- [ ] Random, buy-and-hold, and best-deterministic-rule baselines run through the identical environment and beaten net of costs.
- [ ] Data split by time and regime; per-feature as-of audit done; normalization fit on training data only and persisted with the checkpoint.
- [ ] Sim-to-live gaps listed in the report; live-readiness verdict handed to `quant_trader`, not self-issued.
