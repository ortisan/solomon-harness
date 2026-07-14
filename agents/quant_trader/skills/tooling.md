---
name: tooling
description: Names the 2026 reference stack for quantitative trading by stage: data handling, vectorized screening, event-driven confirmation, metrics, quant ML, and DRL, plus which once-standard tools to avoid as unmaintained. Use when choosing a library or tool for a quant trading task or reviewing a dependency pin.
---

# Tooling

The 2026 reference stack for this role, with when-to-use guidance: what to reach for at each stage — data handling, vectorized screening, event-driven confirmation, metrics, quant ML, and DRL — and which once-standard tools to avoid because they are unmaintained. Pin versions in the lockfile; a floating quant stack is a reproducibility bug.

## Data layer

- pandas 2.x with PyArrow-backed dtypes for general research; enforce strict dtype and index hygiene: a tz-aware UTC DatetimeIndex, sorted, unique.
- Polars for large datasets and production feature pipelines: lazy scans over Parquet keep 100GB-scale tick and bar data workable on one machine, and the expression API removes a class of index-alignment bugs pandas invites. Rule of thumb: exploratory notebooks in pandas, production feature pipelines in Polars.
- DuckDB for SQL over Parquet and for as-of joins — its built-in `ASOF JOIN` is the point-in-time join primitive the backtest pipeline standard requires — with no database server to run.
- ArcticDB for versioned time-series storage when you need snapshot semantics to back the data-hash reproducibility rule.

## Backtesting engines

- vectorbt for the vectorized pass: parameter sweeps over thousands of configurations in seconds. Know its limits — no real order state — and never quote its fills as final (see the backtest pipeline skill). The PRO fork is more current than the open-source line; confirm the license fits the project before adopting it.
- nautilus_trader for the event-driven pass and the deployment path: Rust core, nanosecond-resolution event loop, the same strategy code for backtest and live, and first-class crypto and futures adapters. The house default for new event-driven work in 2026.
- backtrader is readable and battle-tested but in maintenance mode, with no active feature development for years; acceptable for a small EOD study, wrong for new infrastructure.
- QuantConnect Lean when the bundled multi-asset point-in-time data and cloud runners justify the heavier C#-core platform with Python bindings.
- zipline-reloaded only to maintain older research; do not start new work on it.

## Metrics and reporting

- quantstats for tearsheets, or empyrical-reloaded when you want a functions-only dependency: Sharpe, Sortino, drawdown tables, and underwater plots cover most of the reporting minimums.
- Deflated Sharpe and PBO are not in tearsheet libraries: implement them from Bailey and Lopez de Prado's papers as a small audited in-house module, unit-tested against published worked examples, and treat that module as core IP.

## Quant ML

- scikit-learn plus LightGBM or XGBoost as the supervised baseline before anything deep; a boosted tree over honest features is the benchmark any neural model must beat net of costs.
- Purged CV/CPCV, fractional differentiation, and triple-barrier labels: mlfinlab-style utilities implement Lopez de Prado's toolkit, but licensing and quality vary across forks — audit the implementation you adopt, or implement from the book with tests.
- Portfolio construction: skfolio (scikit-learn-compatible API, actively maintained) as the modern default; cvxpy when the mandate needs custom convex constraints; Riskfolio-Lib for its broad catalog of risk measures. PyPortfolioOpt is aging — fine for a quick Markowitz baseline, not for a new production allocator.
- statsmodels for regression diagnostics and ADF unit-root tests; the arch package for GARCH-family volatility models; hmmlearn for HMM regime detection.

## DRL

- Gymnasium is the environment API (legacy gym is dead). Write the trading environment yourself so costs, action bounds, and accounting are yours to test — environment correctness is the whole game (see the DRL safety skill).
- Stable-Baselines3 (PyTorch) for standard agents (PPO, SAC, DQN): mature, seedable, well documented. Ray RLlib only when you genuinely need distributed rollouts; its API churn is a maintenance tax.
- FinRL and similar research bundles are idea sources, not deployable infrastructure: audit any borrowed environment for cost handling and lookahead before trusting a single reward it emits.

## Cross-cutting rules

- Seed everything — python, numpy, the ML framework, and the environment — in one place, logged with the run.
- Pin the stack: exact versions in the lockfile, and record library versions inside every `save_backtest` payload so old results stay interpretable.
- Prefer boring, testable code over framework magic, per the house simplicity principle: a 200-line NumPy backtest you fully understand beats a framework feature you half understand. But once order state matters, use the event-driven engine rather than reimplementing an order-management system badly.

## Common pitfalls

- Quoting vectorbt fills as final results; it has no order book, queue, or partial-fill state.
- Starting new work on unmaintained engines (zipline-reloaded, effectively frozen backtrader) and inheriting their stale dependency pins.
- Mixing pandas and Polars frames casually across a pipeline; convert at explicit boundaries or ordering and index assumptions rot.
- Trusting a borrowed DRL environment's reward accounting without auditing its costs and lookahead.
- An unpinned stack, where a minor pandas or numpy upgrade changes results and nobody can say why.
- Reimplementing DSR and PBO ad hoc per project, without tests against published worked examples.

## Definition of done

- [ ] Stage-appropriate engine used: pandas/Polars/DuckDB for data, vectorbt for sweeps, nautilus_trader (or Lean) for the event-driven verdict.
- [ ] As-of joins done with a real primitive (DuckDB `ASOF JOIN` or equivalent), not merge-then-shift hacks.
- [ ] Metrics from quantstats or empyrical-reloaded; DSR and PBO from the audited in-house module with its own tests.
- [ ] ML work baselined against LightGBM/XGBoost with purged CV before any deep model; portfolio construction on an actively maintained optimizer.
- [ ] DRL environments are Gymnasium-API, house-written or fully audited; agents from Stable-Baselines3 unless distributed rollouts are justified.
- [ ] Versions pinned in the lockfile and recorded in every `save_backtest`; seeds fixed and logged.
