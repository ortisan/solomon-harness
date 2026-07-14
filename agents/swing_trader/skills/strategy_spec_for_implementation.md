---
name: strategy-spec-for-implementation
description: Governs the transmission contract from a designed strategy to its builders — the machine-actionable spec handed to ml_engineer for learned models (features, labels or reward with costs inside it, regime splits, leakage constraints) and to software_engineer for rule engines (pseudocode, data dependencies, order and error handling, parameter table), converging on quant_trader validation. Use when a validated design needs a model fitted or production code written, or when reviewing a spec before handoff.
---

# Strategy Spec For Implementation

This skill governs the transmission contract between the swing_trader and the builders: the spec that lets ml_engineer fit a model or software_engineer build a rule engine without a single follow-up question, and the return path by which everything converges on a quant_trader validation before any live-readiness claim. The stance: a strategy that lives in the designer's head is not a strategy; the spec is the strategy, and an ambiguity in the spec is a bug filed against the swing_trader, not the builder.

## What stays with the swing_trader

The hypothesis and the risk envelope never transfer: the edge rationale, the acceptance thresholds, the sizing rules, the halts, and the overnight policy remain the swing_trader's, recorded on the hypothesis card. Builders may not alter them; when implementation reality makes a card value unworkable (a data feed lacks the needed frequency, a broker rejects an order type), the change comes back as a card revision, decided by the swing_trader and logged in project memory — never patched silently downstream.

## The spec to ml_engineer — learned edges

When the edge needs a learned model (statistical, ML, or DRL), the package contains:

- Feature definitions with exact lookbacks: each feature as formula, window, data source, adjustment mode, and update frequency — for example "126-day total return excluding the most recent 5 sessions, computed on dividend-adjusted closes, updated daily at the close". "Momentum" is not a feature definition.
- Label or target definition: for supervised models, a forward k-bar return net of the card's costs, or a triple-barrier label (profit target, stop, time stop) whose barriers equal the trade-management rules, so the model learns the trade that will actually be taken. For DRL, the reward function with commissions and slippage inside it per step, plus penalty terms mirroring the risk envelope (drawdown, heat); costs left outside the reward produce agents that overtrade their edge away.
- Splits by time and regime: train, validation, and test windows matching the card's declared splits, purged and embargoed around the label horizon so no label overlaps a training boundary.
- Leakage constraints: point-in-time universe, as-announced fundamentals only, every feature computable at decision time, embargo length at least the label horizon.

ml_engineer owns the fitting methodology and returns a model card — data lineage, training procedure, validation metrics, known failure modes, and limits. The fitted model then enters the assembled strategy for quant_trader's backtest; a model card alone never advances anything toward live.

## The spec to software_engineer — deterministic rule engines

For rules-based strategies (and for the harness around any model), the package contains:

- Signal pseudocode: deterministic, seedable, single pass over bars, every branch and tie-break explicit — including what happens on the first bars before indicators warm up.
- Data dependencies: instruments and universe file, bar frequencies, adjustment mode per series, calendar sources (trading calendar, earnings and macro calendars from research_analyst), vendor, and fallback behavior when a source is unavailable.
- Order handling: order type per entry and exit, time-in-force, partial-fill behavior, reject and retry policy, cancel-on-disconnect, and idempotent signal-to-order mapping so a restart cannot double-send.
- Error handling: a stale-data threshold (halt if the latest bar is older than twice the bar interval), missing-calendar behavior (fail closed — no entries), and kill-switch wiring to the daily and weekly halts and the drawdown schedule.
- A parameter table: every tunable with its default, its allowed range (exactly the card's declared grid), and the rule that any value outside the range is a card revision, not a config change.

software_engineer owns the implementation under the house TDD cycle and returns tested code whose behavior is verified against a golden backtest run — same inputs, same trades, bit-for-bit — before it is called done.

## Convergence on quant_trader

Both branches return to the same gate: the assembled strategy — fitted model or rule engine, inside the risk envelope — goes to quant_trader for validation as a whole. A validated design plus a correct implementation is still unvalidated as a system until quant_trader's verdict covers the final artifact, because integration is where lookahead, unit mismatches, and calendar bugs hide. Live-ready means quant_trader passed the thing that will actually run.

## Memory logging

Every handoff is logged in project memory with the spec version it carried; model cards, implementation sign-offs, and quant_trader verdicts are recorded and linked back to the hypothesis card. A spec that is not in memory does not exist: the next session must be able to reconstruct who holds what and which version is current.

## Common pitfalls

- Handing ml_engineer a label that ignores costs, because the model then optimizes gross patterns whose net expectancy is negative.
- Prose where pseudocode belongs ("enter on strength"), because every builder resolves the ambiguity differently and none of them match the backtest.
- Letting a builder widen a parameter range to "make it work", because the deployed strategy then runs outside everything that was validated.
- Splits without purging and embargo around the label horizon, because overlapping labels leak the test set into training.
- Skipping the golden-run verification, because a compiling implementation that trades differently from the backtest is a new, unvalidated strategy.
- Treating the model card or the merged implementation as the finish line, because the gate is quant_trader's verdict on the assembled system.

## Definition of done

- [ ] The hypothesis and risk envelope are marked as retained by the swing_trader; any change routes back as a logged card revision.
- [ ] The ml_engineer package (when applicable) has exact feature lookbacks, a cost-inclusive label or reward, purged and embargoed regime splits, and explicit leakage constraints.
- [ ] The software_engineer package has deterministic pseudocode, data dependencies with fallbacks, order and error handling, and a parameter table bound to the declared grid.
- [ ] Return artifacts are defined: model card from ml_engineer, golden-run-verified implementation from software_engineer.
- [ ] The assembled strategy goes to quant_trader for validation before any live-readiness claim.
- [ ] Every handoff, artifact, and verdict is logged in project memory with its spec version.
