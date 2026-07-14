---
name: strategy-hypothesis-and-validation-handoff
description: Governs the two bookends of a scalping strategy: the mandatory hypothesis card written before any code and the validation handoff to quant_trader deciding whether the strategy is more than a hypothesis. Use when starting a scalping strategy or handing a completed design to quant_trader for tick-level validation.
---

# Strategy Hypothesis And Validation Handoff

This skill governs the two bookends of every scalping strategy: the mandatory hypothesis card written before any code, and the validation handoff to quant_trader that decides whether the strategy is anything more than a hypothesis. The scalper designs; quant_trader validates; live-readiness exists only on the far side of that handoff. A strategy without a card is not started, and a strategy without quant_trader's verdict is not finished.

## The mandatory hypothesis card

House law (the Quantitative Trading competency in agents/AGENTS.md, enforced by quant_trader's own hypothesis-card skill) requires every field as a number, not an adjective:

- Target Sharpe: net of costs, out-of-sample, annualized. House default bar is 1.5 or better; below 1.0 net out-of-sample, no deployment.
- Max drawdown limit: peak-to-trough on the equity curve; house default hard cap 20 percent, with a kill switch at 1.25 times the backtested max drawdown.
- Profit factor: gross profit over gross loss; house floor 1.3, and below 1.1 the edge is noise.
- Latency and slippage constraints: the end-to-end reaction budget (p50 and p99) and the slippage model with its value in ticks or bps.
- Dataset and features: instruments, venue, date range, data resolution and vendor, point-in-time integrity notes, and the exact feature list with windows.
- Model or rule architecture: rules-based logic, a named ML model, or a DRL setup, with hyperparameters and search space.

Scalping adds fields the house card implies but this role makes explicit: per-trade expectancy in ticks with stop and target distances, expected trades per day, the signal half-life in seconds against the reaction budget, capacity in contracts or shares per event, the fee tier assumed, and the economic rationale — the sentence explaining why this edge exists and who is on the other side. If that sentence cannot be written, the result is treated as overfit until proven otherwise.

## Worked example card

Strategy: ES queue-imbalance take. When top-of-book queue imbalance exceeds 0.8 for 500 ms and the short side of the book has thinned below 40 contracts, take one contract in the imbalance direction; exit at plus 2 ticks or minus 2 ticks, or after 20 seconds.

- Target Sharpe: 1.8 net, out-of-sample, annualized from daily PnL.
- Max drawdown: 8 percent of allocated capital; kill switch at 10 percent (1.25x).
- Profit factor: 1.4 floor.
- Latency: retail-websocket tier; reaction p50 35 ms, p99 120 ms; signal half-life measured at 2.1 s (margin ~17x at p50). Slippage: 1 tick assumed on entry (taker), 1.5 ticks on stop exits.
- Dataset: ES front month, CME MDP 3.0 MBO capture, 2025-06-01 to 2026-05-31, roll-adjusted, halts and auction phases tagged.
- Features: QI at touch (500 ms persistence), queue depletion rate over 1 s, signed trade-flow over 2 s.
- Architecture: rules-based thresholds; threshold grid stated up front (QI 0.7 to 0.9 step 0.05; thin-side 30 to 60 step 10).
- Economics: fees 0.32 ticks per round turn; taker entry pays half to full spread; break-even 1.4 ticks gross per trade; required win rate at 2/2 tick stop/target: 60 percent plus costs margin. Expectancy target: 0.15 ticks net per trade, about 120 trades per day, capacity 1 to 3 contracts per event.
- Rationale: near-empty queues at the touch resolve into the thin side because remaining resters cancel faster than takers arrive.

## The handoff to quant_trader

The handoff is a package quant_trader can validate without asking questions:

1. The hypothesis card, complete.
2. The data specification: sources, timestamps, integrity checks, and how to obtain the same capture.
3. The signal specification or code, deterministic and seedable.
4. The fill-model assumptions from the tick-data-backtesting skill: queue model, conservative fill rules, latency injection values.
5. The cost model file, with schedule version and tier.
6. The proposed in-sample/out-of-sample split and the parameter grid searched, declared before results are discussed.
7. The intraday risk envelope, so validated results include the stops, limits, and kill-switch behavior that will exist in production.

quant_trader owns the verdict under its backtest pipeline standards: overfitting checks, out-of-sample and cross-validation discipline, leakage prevention, and regime robustness. The scalper does not negotiate thresholds after seeing results, does not re-run with new parameters and present the best pass as the first, and does not summarize a failed validation as "promising". If validation fails, the finding goes to memory, the card is revised or the idea is retired, and any re-submission states what changed and why. Only a passing tick-level validation from quant_trader supports the words "live-ready", and the handoff, verdict, and decision are logged in project memory.

## Common pitfalls

- Starting to code before the card exists, then back-filling numbers to match what was built.
- Cards with adjectives ("low latency", "tight stops") where numbers belong.
- Omitting the economic rationale, leaving no way to distinguish edge from artifact.
- Declaring the parameter grid after seeing results, which converts out-of-sample into in-sample.
- Resubmitting a failed strategy with silent changes and a fresh-looking card.
- Calling a bar-level or in-sample result "validated" — validation means quant_trader's tick-level, out-of-sample verdict.

## Definition of done

- [ ] The hypothesis card is complete before implementation: Sharpe, drawdown, profit factor, latency and slippage constraints, dataset and features, and architecture, all as numbers.
- [ ] Scalping-specific fields are present: expectancy in ticks, stop and target, trades per day, signal half-life versus reaction budget, capacity, fee tier, and the economic rationale.
- [ ] The handoff package contains the card, data spec, signal spec, fill-model assumptions, cost model, declared split and grid, and risk envelope.
- [ ] The parameter grid and out-of-sample split were declared before any results were produced.
- [ ] quant_trader's verdict is recorded in project memory, with the handoff logged.
- [ ] No live-readiness claim exists anywhere without a passing tick-level validation from quant_trader.
