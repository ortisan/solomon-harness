---
name: rebalancing-and-turnover-control
description: Governs when and how a long-horizon portfolio trades back toward its targets — calendar versus threshold triggers, no-trade bands, annual turnover budgets, and the cost-benefit math that decides whether a trade is worth making. Use when designing a rebalancing policy, setting band widths or a turnover budget on a hypothesis card, or evaluating whether a drifted position is worth the round-trip cost to correct.
---

# Rebalancing and Turnover Control

This skill governs when and how a long-horizon portfolio trades back toward its targets: calendar versus threshold triggers, no-trade bands, turnover budgets, and the cost arithmetic that decides whether a trade is worth making. The stance: at long horizons, trading is a cost center, not a return source — every rebalance buys tracking accuracy with real money, so the policy must make that purchase explicit, bounded, and cheap.

## Calendar versus threshold rebalancing

Calendar rebalancing trades back to target on a fixed schedule (monthly, quarterly, annually). Its virtues are simplicity, auditability, and predictable operational load; its vice is that it trades when nothing needs trading and waits when something does. Threshold rebalancing trades only when a weight drifts outside a band around its target, which concentrates trading where drift is real. The empirical record, stated qualitatively, is that the two approaches deliver similar risk control before costs, and threshold policies usually win after costs because they trade less for the same tracking error. A sound default for long-horizon portfolios is the hybrid: check drift on a calendar (say monthly), but trade only the positions outside their bands. The checking frequency should match the horizon — a strategy with a twelve-month signal does not need daily drift checks, and aligning checks with signal-refresh dates avoids trading twice for one piece of information.

## No-trade bands

Set a band around each target weight inside which no trade occurs. Two conventions: absolute bands (target plus or minus, say, 5 percentage points) suit large core allocations; relative bands (plus or minus 20 to 25 percent of the target weight itself) scale sensibly across positions of very different sizes — a 2 percent position gets a 40-to-50-basis-point band rather than the same 5-point band as a 40 percent position. The width trades tracking error against turnover: wider bands mean fewer, larger trades and more drift. Critically, when a band is breached, trade back to the nearest band edge, not to the exact target. Trading to the edge roughly halves turnover relative to trading to target for a modest increase in average drift, because it does not spend money buying the last increment of precision that the next day's drift will destroy anyway. Band widths are design parameters: set them from the cost model and the asset's volatility (more volatile positions breach more often, so give them wider relative bands), and record them in the specification.

## Turnover budgets

Give every strategy an explicit annual one-way turnover budget on the hypothesis card, and design the rebalancing policy to live inside it. Reasonable orders of magnitude: a drifting strategic allocation can live under 20 percent a year; a long-horizon factor sleeve typically needs 50 to 100 percent; a medium-speed trend sleeve can need multiples of that, which is exactly why its cost assumptions must be stated rather than waved at. The budget converts to a cost floor: annual turnover times the round-trip cost per unit traded is the minimum performance drag, and the strategy's expected edge must clear it with margin for error. When a design wants more turnover than the budget allows, the options are, in order of preference: widen the bands, slow the signal (longer lookbacks decay slower), tranche the trading over several days, or accept the strategy is a different, more expensive product and re-underwrite the card. Silently exceeding the budget is not an option; realized turnover is one of the numbers quant_trader's validation must report against the card.

## Cost-aware rebalancing math

Every candidate trade should pass a benefit-versus-cost test. The cost side is concrete: half the bid-ask spread plus expected market impact plus fees, per unit traded, from the costs_taxes_and_capacity skill. The benefit side is the value of reduced drift: the expected improvement in risk-adjusted return, or the reduction in tracking-error penalty, from moving the weight back toward target. A practical formulation: estimate the drag of the drifted portfolio versus target (from the covariance matrix and, where the design claims one, the expected-return difference), and trade only when that drag, accumulated over the expected holding period until the next natural trading opportunity, exceeds the round-trip cost of correcting it. This test is what justifies band edges over exact targets and it generalizes: cash flows in or out of the portfolio are free rebalancing opportunities (direct new cash at the most underweight positions before trading anything), and tax-sensitive accounts raise the effective cost of selling winners, which widens the optimal bands on exactly those positions.

## Common pitfalls

- Rebalancing to the exact target instead of the band edge, because it buys precision that immediate drift destroys and roughly doubles turnover.
- Checking drift daily for a twelve-month-horizon strategy, because the checking frequency should match the information frequency, and needless checks manufacture needless trades.
- Publishing a design with no turnover budget, because unbounded turnover converts a positive gross edge into a negative net one without anyone deciding it.
- Ignoring cash flows as rebalancing opportunities, because directing contributions and withdrawals at the largest drifts is turnover-free tracking control.
- Setting one absolute band width across positions of very different sizes, because it over-trades small positions and under-controls large ones; use relative bands.
- Tuning band widths by in-sample backtest optimization alone, because band parameters overfit like any others; derive them from the cost model and volatility, then validate through quant_trader.

## Definition of done

- [ ] The trigger policy (calendar, threshold, or hybrid) is stated, with checking frequency aligned to the signal horizon.
- [ ] Every position has an explicit band (absolute or relative, with the choice justified), and execution trades to the band edge.
- [ ] The annual one-way turnover budget is on the hypothesis card, with the implied cost floor computed against the claimed edge.
- [ ] The benefit-versus-cost test for trades is specified, including the treatment of cash flows and any tax-sensitivity adjustments.
- [ ] Band widths and trigger parameters derive from the cost model and asset volatility, not from in-sample optimization.
- [ ] Realized turnover is listed among the validation outputs quant_trader must report against the card.
