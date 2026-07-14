---
name: benchmarking-across-domains
description: Defines dated, versioned yardsticks for software engineering, software architecture, ML/DRL engineering, and quantitative trading — current Python and pytest tooling, C4 and hexagonal architecture with ADRs, vetted DRL algorithms with leakage-free validation, and Sharpe/drawdown-backed backtests. Use when tagging a delivery's competency domain and selecting the current-standard benchmark to audit it against.
---

# Benchmarking Across Domains

This skill defines the concrete, versioned yardsticks the curator measures a delivery against in each of four competency fields, so that "state of the art" is a named standard with a date rather than a moving opinion. It supplies the benchmarks that `auditing_delivered_work` applies per domain, and every yardstick named here must be confirmed through `sourcing_the_state_of_the_art` before it drives a finding. The four fields are software engineering, software architecture, ML/DRL engineering, and quantitative trading; a single delivery can touch all four, so tag the diff by field and apply the matching section.

## Software engineering

Measure delivered code against current Python practice: Python 3.12 and 3.13 (3.13 released October 2024), with new code typed and checked by `mypy --strict` or Pyright. Testing follows the test pyramid with `pytest` 8.x; coverage is tracked with `pytest-cov`, and mutation testing (mutmut 3.x or cosmic-ray) is the check on test strength rather than line coverage alone. Lint and format with Ruff 0.x as the single tool, replacing the older flake8 plus Black plus isort stack. Style baselines are PEP 8 and the Google or PEP-257 docstring conventions. Continuous integration runs on GitHub Actions with the test, type, and lint gates on every PR. Versioning is Semantic Versioning 2.0.0 and commits follow Conventional Commits 1.0.0. The working discipline is TDD red-green-refactor; a feature merged with no covering test is a high-severity gap regardless of how clean the code reads.

## Software architecture

Benchmark structure and decisions against the C4 model (Simon Brown) for context, container, and component diagrams, and against hexagonal architecture, also called ports and adapters (Alistair Cockburn, 2005), as the default boundary style in this project. Significant design choices are captured as Architecture Decision Records in Michael Nygard's 2011 format, commonly using the MADR template, stored in-repo. Long-lived qualities are guarded by fitness functions as described in Building Evolutionary Architectures, 2nd edition (2022), so that constraints such as dependency direction or layering are tested, not just documented. SOLID principles and clear design contracts at module boundaries are the unit-level baseline. A delivery that crosses a port boundary without an adapter, or that makes a structural decision with no ADR, is an architecture gap to record against the software_architect agent.

## ML/DRL engineering

For deep reinforcement learning, benchmark algorithm choice against the current vetted set: PPO, SAC, TD3, DQN, and A2C, with PPO and SAC as the strong general-purpose defaults. Prefer audited implementations over hand-rolled loops: Stable-Baselines3 2.x on top of Gymnasium 1.x (the maintained successor to OpenAI Gym), with CleanRL as a single-file reference when transparency matters. The numerical stack is PyTorch 2.x or TensorFlow 2.x with Keras 3, and scikit-learn 1.x for classical models. Reproducibility is non-negotiable: fixed seeds across NumPy, the framework, and the environment, deterministic operations where available, pinned dependency versions, and experiment tracking with MLflow 2.x or Weights & Biases. Guard against data leakage by keeping any test or future data out of training and feature construction. Validation uses cross-validation suited to the data: stratified k-fold for i.i.d. data and `TimeSeriesSplit` or purged k-fold for sequential data. A DRL or ML delivery with no fixed seed, no leakage control, or a single train/test split is a high-severity reproducibility gap.

## Quantitative trading

Benchmark strategy and backtest quality against the standard risk and validation measures. Report risk-adjusted return as the annualized Sharpe ratio (with the risk-free rate subtracted), and pair it with the Sortino ratio, maximum drawdown, the Calmar ratio, and profit factor; a Sharpe quoted without a drawdown figure is an incomplete result. Validate out-of-sample with walk-forward analysis and purged k-fold cross-validation with an embargo, as set out in Marcos Lopez de Prado's Advances in Financial Machine Learning (2018), to prevent overfitting and the look-ahead and survivorship biases that inflate backtest returns. Every backtest must model slippage and transaction costs, including commissions and market impact; a frictionless backtest is not evidence. Reference frameworks are vectorbt, backtrader, zipline-reloaded, and Nautilus Trader. A strategy delivered with an in-sample-only result, no transaction-cost model, or no drawdown limit is a high-severity gap to record against the quant_trader agent.

## Common pitfalls

- Applying a software-engineering yardstick to an ML or quant delivery (or the reverse), producing noise instead of findings, because the diff was not tagged by field.
- Naming a standard without a version or year, so the benchmark cannot be checked for currency by `sourcing_the_state_of_the_art`.
- Accepting a frictionless backtest or an in-sample-only result as evidence of a working quant strategy.
- Treating line coverage as proof of test strength instead of mutation testing, missing tests that assert nothing.
- Flagging a hand-rolled DRL loop as a gap on style grounds rather than on the concrete reproducibility and leakage risks.
- Citing a superseded reference (an older edition, a deprecated framework version) as the current benchmark.

## Definition of done

- [ ] The delivery is tagged with each of the four fields it touches before any benchmark is applied.
- [ ] Each applied yardstick is named with a version number or year, not as a bare label.
- [ ] Software-engineering work is checked against current Python, pytest 8.x, Ruff 0.x, typing, and TDD.
- [ ] Architecture work is checked against C4, ports and adapters, ADRs, and fitness functions.
- [ ] ML/DRL work is checked for algorithm fit, framework version, seeding, leakage control, and cross-validation.
- [ ] Quant work is checked for Sharpe, drawdown, profit factor, out-of-sample or walk-forward validation, and cost modeling.
- [ ] Every yardstick used is confirmed through `sourcing_the_state_of_the_art` and fed back to `auditing_delivered_work`.
