---
name: overnight-gap-and-event-risk
description: Governs what changes when a position crosses the close — gap risk voids the stop guarantee, so sizing shifts to gap-through-stop scenarios, earnings and macro calendars become hard filters, and weekend, holiday, and hedging-or-flatten rules apply. Use when deciding whether a position may be held overnight, sizing a multi-day hold, or setting rules around earnings, FOMC, CPI, or weekends.
---

# Overnight Gap And Event Risk

This skill governs the single largest structural difference between intraday and multi-day trading: once a position crosses the close, the stop-loss no longer bounds the loss. Every overnight hold is sized against the gap-through-stop scenario, screened against the event calendar, and covered by an explicit flatten-or-hedge rule — or it is not held.

## What overnight changes

Intraday, a stop-market order bounds the realized loss near the stop price plus normal slippage, because trading is continuous. Overnight, that guarantee is void: the instrument opens wherever supply and demand reprice it, and a stop resting through the close fires at or after the opening print, not at the stop price. If the stop sits 2% below entry and the name opens down 8%, the realized loss is roughly 8%, quadruple the intended 1R. Single-stock gaps of 2-4x daily ATR are routine on earnings and news; the tail runs far beyond that. So for any overnight position, "risk per trade" defined by the stop is a fiction unless the size accounts for the gap distribution.

## Sizing for gap-through-stop

The rule: size the position so that a gap through the stop at the 95th-percentile adverse overnight move for that instrument class still loses no more than the daily loss limit. Mechanically, replace the stop distance in the sizing formula with the larger of the two: shares = (equity x risk fraction) / max(stop distance, P95 adverse gap). Working numbers: liquid large-cap overnight moves on non-event nights run at roughly 0.5-1.0x daily ATR at the 95th percentile; earnings nights routinely print 5-10% moves with tails beyond 20%; index futures and broad ETFs gap least and can usually be sized on 1x their stop distance plus a modest buffer. The instrument's own gap history over 2+ years is the estimate of record — asset-class rules of thumb are the fallback, not the primary.

This is why swing risk fractions sit at the low end of the sizing skill's band: a 0.5% nominal risk with a 3x gap-through multiplier is a 1.5% realized-loss scenario, which is the real number the book carries into every close.

## Event calendars as hard filters

- Earnings: checking the report date is a mandatory pre-entry step for every equity swing. No position is held through its own earnings report unless the strategy is explicitly an earnings strategy, with gap-based sizing and the hold written on the hypothesis card. "The chart looks strong into the print" is not a strategy; it is an unsized binary bet.
- Macro events: FOMC decisions, CPI, and payrolls move index-correlated books as a unit. The book-level rule is reduce or hedge ahead of the event when net exposure exceeds half the heat cap; single-name daytrades avoid initiating inside the release window per the session-structure skill.
- The calendar itself — report dates, confirmed times, macro schedule — is sourced from research_analyst, timestamped, and refreshed before each entry, because a stale earnings date is operationally identical to no check at all.

## Weekend and illiquid sessions

A weekend hold spans two overnight boundaries plus 60+ hours of headline exposure with no exit available; holiday half-days and the sessions around them carry thin books where exits pay outsized impact. Rules: each strategy's card states its weekend policy (hold at normal size, reduce by a stated fraction, or flatten Friday) — trend-following swings usually hold, reversion trades usually do not survive the extra variance; never hold a position whose primary venue is closed while a correlated venue trades and prices news against it.

## Hedging or flattening

- Flatten is the default for daytrade setups: intraday edges are validated intraday, and carrying one overnight converts it into an unvalidated swing.
- Index hedging: when a macro event window approaches and the book is directionally heavy, short index futures or a broad ETF sized to the book's beta-weighted net exposure, on for the event window only.
- Options: holding a single name through a mandated binary uses a protective put or collar; the premium is priced into the trade's cost model, and if the put costs more than the expected post-event drift, the hold is dead on arrival and the position is flattened instead.

## Common pitfalls

- Sizing an overnight position from the chart stop alone, because the gap distribution — not the stop — is the real loss variable past the close.
- Holding through earnings "because the trend is strong", because the position becomes an unsized coin flip whose loss tail was never on the card.
- Treating index products and single names identically, because their overnight distributions differ by multiples and identical sizing overrisks the single names.
- Skipping the calendar check on entry day, because a report date discovered after the close is a forced choice between a binary hold and a panic exit.
- Hedging with an unpriced option overlay, because a hedge that costs more than the expected edge quietly flips the trade's expectancy negative.

## Definition of done

- [ ] Every overnight-eligible strategy sizes with the max(stop distance, P95 adverse gap) rule, with the gap estimate's source stated.
- [ ] The earnings filter is mandatory and explicit; any hold-through-earnings behavior is a card-level declaration with its own sizing.
- [ ] Macro-event reduce-or-hedge rules and the weekend policy are written on the card.
- [ ] Hedge instruments, sizing, and premium costs are specified and included in the cost model.
- [ ] The overnight policy ships with the hypothesis card to quant_trader, and event-driven flatten or hedge decisions are logged in project memory.
