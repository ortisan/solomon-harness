---
name: model-hypothesis-state-before-training
description: Governs the written hypothesis card that must be committed before any training run starts, covering the decision served, primary metric, baseline to beat, dataset, architecture, stopping rule, and resource constraints. Use when starting a new model or DRL training effort, or reviewing whether a hypothesis was pre-registered before training began.
---

# Model Hypothesis: State Before Training

This skill governs the written hypothesis that must be committed before any training run starts. If the acceptance bar is not written down first, the model will be judged by whatever number it happens to produce, and every threshold will drift to fit the result; the hypothesis card is the pre-registration that prevents that.

## The hypothesis card

One short committed document (markdown or YAML next to the training config) with these fields, filled in before training:

- Decision served: what action changes based on the model's output, and who takes it.
- Primary metric and acceptance threshold: one metric, one number, chosen from the decision's costs — not from what the first run achieved.
- Baseline to beat: the naive baseline (persistence, mean, majority class) and the strongest simple model (regularized logistic/linear regression or default-parameter gradient boosting), with their measured scores. A model that does not beat the documented naive baseline is not shippable.
- Dataset and features: exact source, date range, sampling frequency, label definition, and the feature list with how each is computed and when it becomes known (feeds the leakage audit).
- Model and architecture: family, layer sizes, activations, loss, optimizer; for RL, the observation and action spaces and the reward definition.
- Stopping rule: the tuning budget (trials, wall-clock) and the kill criterion — the point at which the honest outcome is a documented negative result.
- Resource constraints: inference latency budget, memory ceiling, training compute budget.
- Risks: suspected leakage vectors, shift between training and serving distributions, known label noise.

## Trading and DRL models

For trading and DRL models the card is mandatory and carries the house numbers unless the card argues otherwise:

- Target Sharpe ratio (annualized): out-of-sample Sharpe >= 1.5 to accept; reject anything below 1.0.
- Maximum drawdown limit: <= 20 percent on the OOS window; state the figure and enforce it.
- Profit factor: >= 1.3 OOS (gross profit / gross loss); below 1.0 is a losing model — discard it.
- Latency and slippage constraints: an inference budget (e.g. < 50 ms p99) and the assumed cost model (e.g. 2 bps per side plus spread). A backtest without transaction costs is invalid.

The card states these targets; validating them — the cost model's realism, capacity, deflated Sharpe against the number of trials — is `quant_trader`'s gate. Hand the card over with the backtest artifacts.

## Worked example (non-trading)

```yaml
# hypothesis: churn-lgbm-v3
decision: weekly batch selects subscribers for a retention offer (budget 5k offers/week)
metric: PR-AUC on the out-of-time test month
accept_if: PR-AUC >= 0.42 AND beats baseline_lr by >= 0.03 with a 95% bootstrap CI excluding 0
baselines:
  majority_class: PR-AUC 0.11 (base rate)
  logistic_l2_12_features: PR-AUC 0.36 (current system)
data:
  source: events warehouse, snapshots 2024-01-05..2026-05-29, weekly
  label: cancel within 60 days of snapshot date
  features: 38 listed in features.md, each with an as-of timestamp <= snapshot date
model: LightGBM 4.x, <=2000 trees with early stopping (50 rounds), monotone constraint on tenure
stopping_rule: 100 Optuna TPE trials; if best CV PR-AUC < 0.37 after 100 trials, stop and file the negative result
constraints: batch scoring of 2M rows in < 10 min on one 8-core node
risks: support-ticket features may be backfilled; verify point-in-time before trusting importance
```

Every field is checkable after the fact, which is the point: the run either met the pre-declared bar or it did not.

## Using the card

Commit the card in the same PR as the training config, and log it to project memory (`save_decision`) so the acceptance bar is timestamped before results exist. When results arrive, the report quotes the card verbatim next to the outcome. Changing the threshold after seeing results is allowed only as a new, explicitly versioned hypothesis with a written justification — never as an edit to the old one. A model that misses the bar produces a negative-result note referencing the card; that note has real value, because it stops the next person from rerunning the same dead end.

## Common pitfalls

- Writing the "hypothesis" after training, fitted to the achieved number.
- An acceptance threshold with no baseline measurement, so "good" floats free of context.
- Vague dataset clauses ("recent data") instead of exact ranges and label definitions.
- No stopping rule, so the search runs until something eventually clears the bar by luck.
- Quietly editing the card's threshold after a miss instead of versioning a new hypothesis.
- A trading card without cost and slippage assumptions, making the backtest unfalsifiable.
- Multiple primary metrics, letting the report pick whichever one passed.

## Definition of done

- [ ] Hypothesis card committed before the first training run, with metric, threshold, baselines, data spec, architecture, stopping rule, constraints, and risks all filled in.
- [ ] Naive baseline and strongest simple baseline measured and recorded on the card.
- [ ] Trading/DRL cards carry Sharpe >= 1.5 (reject < 1.0), drawdown <= 20 percent, profit factor >= 1.3, latency and slippage assumptions — and are handed to quant_trader for backtest validation.
- [ ] Card logged to project memory with a timestamp preceding the results.
- [ ] Final report quotes the card verbatim next to the outcomes; any threshold change exists as a new versioned hypothesis with justification.
- [ ] Misses filed as negative-result notes referencing the card.
