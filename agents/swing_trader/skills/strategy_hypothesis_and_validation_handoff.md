---
name: strategy-hypothesis-and-validation-handoff
description: Governs the two bookends of every daytrade or swing strategy — the mandatory hypothesis card written before any code (targets, universe, rules, costs, splits, all as numbers) and the validation handoff package to quant_trader, which owns the verdict. Use when starting any new strategy, preparing a candidate for backtest validation, or checking whether a live-readiness claim is legitimate.
---

# Strategy Hypothesis And Validation Handoff

This skill governs the two bookends of every daytrade and swing strategy: the mandatory hypothesis card written before any code, and the validation handoff to quant_trader that decides whether the strategy is anything more than a hypothesis. The swing_trader designs; quant_trader validates; live-readiness exists only on the far side of that handoff. A strategy without a card is not started, and a strategy without quant_trader's verdict is not finished.

## The mandatory hypothesis card

House law (the Quantitative Trading competency in agents/AGENTS.md, enforced by quant_trader's own hypothesis-card skill) requires every field as a number, not an adjective:

- Target Sharpe: net of costs, out-of-sample, annualized. House bar is 1.5 or better; below 1.0 net out-of-sample, no deployment.
- Max drawdown limit: peak-to-trough on the equity curve; house hard cap 20 percent, with a kill switch at 1.25 times the backtested max drawdown.
- Profit factor: gross profit over gross loss; house floor 1.3, and below 1.1 the edge is noise.
- Cost and slippage assumptions: commission schedule, per-order-type slippage by ADV tier and session phase, borrow costs on shorts.
- Dataset and features: universe with liquidity floor, date range, bar resolution and vendor, point-in-time integrity notes, and the exact indicator list with lookbacks.
- Model or rule architecture: deterministic rules, a named ML model, or a DRL setup, with the parameter grid stated up front.

Swing trading adds fields the house card implies but this role makes explicit: the holding-period band and time stop; expected trades per month; per-trade risk fraction and expectancy target in R; the overnight policy with its gap-through sizing rule; the event-calendar filters (earnings, macro); the declared in-sample/validation/out-of-sample splits; and the economic rationale — one sentence stating why this edge exists and who is on the other side of it. If that sentence cannot be written, the result is treated as overfit until proven otherwise.

## Worked example card

Strategy: pullback-to-20EMA momentum continuation on US large caps. When a trend-qualified name pulls back 3-8 bars to its 20-day EMA on contracting volume, buy the reclaim of the prior day's high; exit by partial at +1R and a chandelier trail.

- Universe: Russell 1000, point-in-time membership, price above 10 dollars, ADV above 50M dollars.
- Timeframe and holding: daily decision bars, 15-minute execution timing; hold 3-15 sessions; time stop at 4 sessions if the trade has not reached +1R.
- Rules: trend qualification — close above a rising 50-day SMA and 126-day return in the universe's top quintile; entry — buy stop 0.05 above the prior day's high during the pullback; stop — 0.25x ATR(14) below the pullback low (typical distance 1.8x daily ATR); exits — one third off at +1R, remainder on a 3.0x ATR(14) chandelier trail.
- Targets: Sharpe 1.5 net out-of-sample; max drawdown 15 percent with the kill switch at 18.75 percent; profit factor floor 1.4; expectancy target +0.35R per trade at 8-15 trades per month.
- Costs: 5 bps per side commission and fees; slippage 10 bps on stop entries, 5 bps on exits; no earnings holds (research_analyst calendar filter), so no earnings-gap tail in the cost model.
- Risk: 0.5 percent per trade; heat cap 4 percent; daily halt -2R; overnight sizing on max(stop, P95 non-event gap = 0.9x ATR).
- Data and splits: 2016-01-04 to 2026-06-30, dividend-adjusted daily plus 15-minute bars; in-sample 2016-2021, validation 2022-2023, untouched holdout 2024-2026; declared grid — EMA {10, 20}, relative-strength cut {top 20%, top 10%}, trail {2.5x, 3.0x}.
- Rationale: institutions accumulate leaders over days to weeks, so pullbacks in trend-qualified names are supply pauses at anchor levels where systematic buyers return, not reversals.

## The handoff to quant_trader

The handoff is a package quant_trader can validate without asking questions:

1. The hypothesis card, complete.
2. The data specification: sources, adjustment policy per series, point-in-time universe file, and how to reproduce the sample.
3. The rule or signal specification, deterministic and seedable.
4. The backtest-hygiene attestations from the bar-data skill: execution discipline, causal indicators, fill assumptions.
5. The cost model with its schedule and tier.
6. The declared splits and the full parameter grid, stated before any results were produced.
7. The risk envelope — sizing, halts, heat, overnight policy — so validated results include the constraints production will carry.

quant_trader owns the verdict under its backtest pipeline standards: overfitting checks, out-of-sample and cross-validation discipline, leakage prevention, and regime robustness. The swing_trader does not renegotiate thresholds after seeing results, does not re-run with new parameters and present the best pass as the first, and does not summarize a failed validation as "promising". If validation fails, the finding goes to project memory, the card is revised or the idea retired, and any resubmission states exactly what changed and why. Only a passing out-of-sample verdict from quant_trader supports the words "live-ready", and the handoff, verdict, and decision are logged in project memory.

## Common pitfalls

- Starting to code before the card exists, then back-filling numbers to match what was built.
- Cards with adjectives ("tight stops", "liquid names") where numbers belong.
- Omitting the economic rationale, leaving no way to distinguish edge from artifact.
- Declaring the parameter grid after seeing results, which converts out-of-sample into in-sample.
- Resubmitting a failed strategy with silent changes and a fresh-looking card.
- Calling an in-sample or validation-segment result "validated" — validation means quant_trader's out-of-sample verdict on the holdout.

## Definition of done

- [ ] The hypothesis card is complete before implementation: Sharpe, drawdown, profit factor, costs, dataset and features, and architecture, all as numbers.
- [ ] Swing-specific fields are present: holding band, time stop, trades per month, risk fraction and expectancy in R, overnight and event policy, splits, and the economic rationale.
- [ ] The handoff package contains the card, data spec, rule spec, hygiene attestations, cost model, declared splits and grid, and risk envelope.
- [ ] The grid and splits were declared before any results were produced.
- [ ] quant_trader's verdict is recorded in project memory, with the handoff logged.
- [ ] No live-readiness claim exists anywhere without a passing out-of-sample validation from quant_trader.
