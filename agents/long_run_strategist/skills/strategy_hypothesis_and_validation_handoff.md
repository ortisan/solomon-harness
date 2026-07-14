---
name: strategy-hypothesis-and-validation-handoff
description: Governs the two documents bounding every piece of the long_run_strategist's work — the hypothesis card that pre-registers a strategy's targets and assumptions before design, and the validation handoff that hands the backtest and verdict to quant_trader. Use when drafting a hypothesis card's required fields, closing out a design phase, or recording a pass/fail verdict and a failed hypothesis in project memory.
---

# Strategy Hypothesis and Validation Handoff

This skill governs the two documents that bound every piece of this agent's work: the hypothesis card that starts a strategy and the validation handoff that ends the design phase. The stance: per the house rules in agents/AGENTS.md, a model hypothesis must state its targets, constraints, data, and architecture before implementation, and the agent that designed a strategy never grades it — quant_trader owns the backtest and the verdict. A strategy without a card is not started; a strategy without a handoff is not finished.

## Why a card

The card is a pre-registration. Written before any performance is observed, it fixes the acceptance criteria so they cannot drift to fit the results, it makes the design reviewable by stating every assumption a reviewer would otherwise have to guess, and it gives quant_trader an unambiguous pass/fail contract. It also disciplines the strategist: a hypothesis that cannot be written down concretely — with numbers — is not yet a hypothesis.

## The card fields

Per the house competency block, every card states the following, calibrated for long horizons:

- Target Sharpe ratio, net of the card's own cost assumptions. For a diversified long-horizon strategy, a net Sharpe of 0.6 to 1.0 is a credible ambition; a claimed net Sharpe above 1.5 at monthly-scale turnover is a red flag that should send the design back for a data-mining review before it goes anywhere near validation.
- Drawdown limit, consistent with the volatility target: over decades, expect maximum drawdowns of roughly two to three times annualized volatility, so a 10 percent volatility strategy carries a drawdown limit in the 20-to-30-percent region, plus the de-risking ladder from the sizing skill.
- Profit factor (gross gains over gross losses) measured at the strategy's decision frequency — monthly for most long-horizon designs. At low frequency, modest values (roughly 1.3 to 1.8, stated qualitatively) are realistic; extreme values again suggest overfitting.
- Latency and slippage constraints. Long-horizon designs measure latency in days, not milliseconds, but the assumption must still be explicit: state the implementation lag between signal computation and execution (for example, trade on the close of day T+1 for a signal computed on day T's close) and the slippage model per asset class from the costs skill.
- Dataset and features: the universe and its point-in-time construction, the sample period and its regime coverage, every input series with its source and lag, and the hygiene requirements from the backtest-hygiene skill as acceptance criteria.
- Model or rule architecture: the exact signal definitions, the portfolio construction method, the sizing policy, and the rebalancing rules — or, where a fitted model is involved, the architecture plus a note that ml_engineer owns the fitting and its validation.
- Variant accounting: how many parameterizations were or will be examined, so significance can be judged honestly.

## A worked long-horizon example

Hypothesis: a time-series momentum ensemble (3-, 6-, and 12-month lookbacks, equal-weighted, skip-month applied) across roughly 50 liquid global futures (equity index, government bond, currency, commodity), positions scaled to equal ex-ante risk with a floored 40-day EWMA volatility estimate, portfolio volatility targeted at 10 percent annualized, gross exposure capped at 200 percent, monthly rebalance with trade-to-band-edge execution. Targets: net Sharpe 0.7; drawdown limit 25 percent with the standard de-risking ladder; profit factor at monthly granularity of at least 1.4. Latency and slippage: signals on month-end close, execution over the first two trading days of the month; costs of 1 to 3 basis points half-spread plus square-root impact at a 5 percent ADV participation cap, per asset class. Dataset: back-adjusted continuous futures with documented roll methodology, multi-decade sample spanning rate and inflation regimes, per-regime reporting required. Architecture: rules as stated, no fitted parameters beyond the volatility estimator. Variants examined: the three lookbacks were fixed in advance from the published evidence base; no grid search performed.

## The handoff contract to quant_trader

The strategist delivers the card, the full rule specification, and the data requirements. quant_trader owns the backtest implementation, the cost modeling, the statistical validation (including overfitting and leakage checks, walk-forward execution, and the baseline comparison), and the verdict against the card's numbers. Fundamental or qualitative inputs cited by the design carry research_analyst's sourcing; any fitted model inside the strategy arrives already validated by ml_engineer, never raw. The verdict comes back as pass or fail per card criterion. A failed hypothesis is recorded in the project memory with its card and verdict — failures are reusable knowledge — and a redesign starts a new card version rather than quietly editing the old one. The strategist may iterate, but each iteration increments the variant count, and the holdout period is spent exactly once. Under no circumstance does this agent run its own validation and present the result as final; self-graded numbers are candidates by definition.

## Common pitfalls

- Starting implementation before the card exists, because acceptance criteria written after the results are not criteria.
- Setting a target Sharpe above what the strategy class has historically supported, because an ambitious card just guarantees a meaningless failure or an overfit pass.
- Omitting the implementation-lag assumption because the strategy is "slow", because even monthly strategies lose measurable edge to execution timing.
- Editing the card after seeing results instead of versioning it, because silent revision destroys the pre-registration and the audit trail.
- Presenting a self-run backtest as the verdict, because validation belongs to quant_trader and self-grading is the one non-negotiable this skill exists to prevent.
- Discarding failed hypotheses without recording them, because unrecorded failures get re-run by the next session and the variant count silently resets.

## Definition of done

- [ ] The card states target Sharpe, drawdown limit, profit factor, latency and slippage constraints, dataset and features, and model or rule architecture, with long-horizon-calibrated numbers.
- [ ] Hygiene requirements from the backtest-hygiene skill appear on the card as acceptance criteria, and the variant count is recorded.
- [ ] Fundamental inputs carry research_analyst sourcing; fitted models arrive validated by ml_engineer.
- [ ] The handoff to quant_trader includes the card, the full rule specification, the data requirements, and the required validation outputs (per-regime results, realized turnover, realized costs, baseline comparison).
- [ ] The verdict is recorded per criterion in the project memory, pass or fail, with failed cards preserved and redesigns versioned.
- [ ] No self-graded result is presented as validated anywhere in the deliverable.
