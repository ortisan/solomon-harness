---
name: strategy-spec-intake-and-model-handoff
description: Governs the intake of trading-strategy specs from swing_trader, scalper, or long_run_strategist and the artifact set returned, covering required spec fields, rejection of incomplete specs, baseline-first model plans, and the quant_trader validation handoff. Use when receiving a strategy spec for modeling, or packaging a trained model for validation and production handoff.
---

# Strategy Spec Intake and Model Handoff

This skill governs the receiving side of the trading-strategy pipeline: what an incoming spec must contain before modeling work starts, how it is translated into a model plan, and the artifact set that goes back out. The ml_engineer is a contractor to the strategy roles, not a co-author of the strategy — gaps in the spec are returned to the sender, never filled by guessing, because a guessed lookback or an assumed cost model silently becomes the strategy.

## The intake contract: what a valid spec contains

A spec from `swing_trader`, `scalper`, or `long_run_strategist` is accepted for modeling only when every field below is present and unambiguous:

- Universe and data: exact instruments or selection rule, venue, bar or tick frequency, date range, and the data source with its point-in-time guarantees (survivorship-free, as-reported fundamentals).
- Feature definitions: each input named with its exact formula, lookback window, and the timestamp at which its value becomes known — the as-of column that feeds the audit in `data_leakage_prevention`.
- Label or target: for supervised work, the label definition with horizon and barriers; for DRL, the reward definition — and in both cases costs (per-side bps, spread model, borrow) inside the target, not appended later.
- Splits by regime: train, validation, and test windows chosen by the sender to cover distinct market regimes, with the test window embargoed from all tuning.
- Leakage constraints: any fields or transforms the sender knows to be unavailable or restated at decision time.
- Latency class: batch (daily rebalance), intraday (sub-second budget), or tick-level — this decides the feasible model families before any training starts.
- Risk envelope: maximum drawdown, position and exposure limits, and the target metrics (Sharpe, profit factor) the sender expects, matching the house thresholds in `model_hypothesis_state_before_training`.

## Reject incomplete specs — do not guess

When a field is missing or ambiguous, return the spec to the sender with the specific gaps enumerated, and do not start work. The rejection is a normal pipeline event, not friction: an ml_engineer who invents a 20-day lookback because the spec said "recent momentum" has made a strategy decision without the strategy role's context, and the resulting model tests a hypothesis nobody proposed. Log the rejection and its reasons; a spec that bounces twice on the same field signals a template problem worth raising with the sender's role.

## From spec to model plan: baseline first

Translate the accepted spec into a written model plan before training:

- Baseline ladder: the naive baseline (persistence, majority class, zero-position), then a regularized linear or logistic model, then default-parameter gradient boosting (LightGBM or XGBoost). Only when a simple model demonstrably underfits the spec's target does a deep model (per `deep_learning_engineering`) or a DRL agent (per `deep_reinforcement_learning`) enter the plan — and the simple model's score stays in the report as the bar.
- Success criteria fixed before training: the primary metric, its acceptance threshold, and the stopping rule are committed as the hypothesis card from `model_hypothesis_state_before_training`. Thresholds are copied from the spec's risk envelope, never derived from the first run's results.
- Tuning budget and split usage per `data_splitting_and_cross_validation` and `hyperparameters_and_tuning`; the test window is touched once.

## Division of labor

The pipeline separates building, productionizing, and judging, and the boundaries are not optional:

- `ml_engineer` owns model fitting, the training report, and the didactic explanation of what the model does and where it fails.
- `software_engineer` owns the production implementation — serving code, integration, deployment; research code is input to that work, not the deliverable.
- `quant_trader` owns the validation verdict: backtest execution against the cost model, robustness checks, and the go/no-go. The model builder never grades their own strategy — a self-issued "validated" is a review defect, whatever the metrics say.

## The returned artifact set

A handoff back to the sender and to `quant_trader` contains, at minimum:

- Model card: intended use, universe and data ranges actually used, primary and secondary metrics on validation and the single test pass, comparison against every baseline rung, and explicit limitations (regimes unseen, capacity assumptions, known failure modes).
- Training report: all seeds run (at least 5 for DRL and any high-variance model) with mean and dispersion, final configs, and learning curves — not the best run alone.
- Reproducibility bundle per `reproducibility`: config files, lockfile, data version, git commit, and the checkpoint with its preprocessing state, sufficient to regenerate every reported number.
- The feature as-of table and completed leakage audit from `data_leakage_prevention`.

An artifact set missing any of these is incomplete, and quant_trader is entitled to bounce it exactly as ml_engineer bounces an incomplete spec.

## Memory logging

Every intake and every handoff is recorded in project memory through the solomon-memory tools: `log_handoff` for the spec acceptance (or rejection, with the gap list) and for the outbound artifact delivery, `save_decision` for model-plan choices that deviate from defaults, and `save_backtest` references once quant_trader's validation exists. The memory record is what lets a later session reconstruct who asked for what, what was delivered, and which verdict is still pending.

## Common pitfalls

- Filling a spec gap by guessing (a lookback, a cost figure, a universe filter), which turns the model into a test of an unproposed strategy.
- Starting with a deep model because the spec sounds complex, so no one ever learns the linear baseline was 95 percent of the result.
- Acceptance thresholds set after seeing the first run, drifting to fit whatever the model produced.
- Reporting the best seed's numbers in the model card while the dispersion sits unmentioned in a notebook.
- Self-declaring the strategy validated instead of handing the verdict to quant_trader, defeating the pipeline's only independent gate.
- Shipping research code to software_engineer as if it were the production implementation.
- Handoff done in chat with nothing written to project memory, so the next session cannot tell whether a verdict is pending.

## Definition of done

- [ ] Incoming spec verified against the full intake contract; gaps returned to the sender enumerated, with nothing filled by assumption.
- [ ] Model plan written with the baseline ladder and success criteria committed before training, per `model_hypothesis_state_before_training`.
- [ ] Baselines trained and reported; any deep or DRL model justified against the simple model's measured score.
- [ ] Artifact set complete: model card, multi-seed training report, reproducibility bundle, feature as-of table with leakage audit, explicit limitations.
- [ ] Validation verdict requested from quant_trader; production implementation handed to software_engineer; no self-issued go/no-go.
- [ ] Intake, rejections, and handoffs logged in project memory with `log_handoff` and related tools.
