# Market Microstructure

This skill governs how the scalper reasons about the mechanics of the venues it trades: the limit order book, queue priority, tick size regimes, fee-driven venue types, auctions and halts, and adverse selection. At holding periods of seconds to minutes, microstructure is not background detail — it is the strategy. Every design must name the mechanism it exploits and the mechanism that can kill it.

## Limit order book mechanics

A modern electronic market is a limit order book (LOB) maintained by a matching engine. Resting limit orders provide displayed liquidity at discrete price levels; incoming marketable orders consume it. The core events are add, modify, cancel, and trade, and a scalper's data model must represent all four, because signals such as order-flow imbalance are built from the event stream, not from snapshots.

Matching is deterministic and rule-bound. Most equity venues and most CME outright futures match price-time (FIFO): better price first, then earlier arrival at the same price. Some rate products and options use pro-rata or hybrid allocation, where size at a level is filled proportionally, sometimes with a top-order priority carve-out. The allocation rule changes the game entirely: under FIFO the scarce resource is time priority; under pro-rata it is displayed size, which invites oversizing and creates cancel races. Never port a strategy across allocation regimes without redesign.

## Queue position and priority

For passive strategies, queue position is the inventory. Joining a 500-lot bid at position 480 and joining at position 20 are different trades with different adverse-selection profiles: the front of the queue gets filled by routine flow, the back gets filled mostly when the level is about to trade through.

Priority rules to internalize: increasing size or changing price sends an order to the back of the queue on effectively every FIFO venue; decreasing size in place usually preserves priority (CME and major equity venues behave this way). Hidden and reserve quantity ranks behind displayed quantity at the same price. With market-by-order (MBO) data — Nasdaq TotalView-ITCH, CME MDP 3.0 MBO — queue position can be tracked exactly per order. With market-by-price (MBP) data it must be estimated: record size ahead at join time, decrement on trades at the level, and treat cancels conservatively (assume they come from behind you), because optimistic queue models are the single biggest source of fake backtest profit.

## Tick size regimes

The ratio of average spread to tick size defines the regime. Large-tick instruments (ES, most liquid front-month futures, sub-100-dollar liquid equities at a penny tick) sit at a one-tick spread most of the day; price improvement inside the spread is impossible, so competition happens in the queue, and queue-position skill dominates. Small-tick instruments (high-priced equities, many crypto pairs) run multi-tick spreads; price discovery happens inside the spread, queue priority is worth less, and quote-fading and repricing speed dominate. State the regime in the hypothesis card, because a queue-based edge evaporates in a small-tick name and a repricing edge is unusable in a large-tick one.

## Maker-taker and inverted venues

US equities fragment across venues with distinct fee models. Maker-taker venues rebate resting orders and charge takers (access fees capped by Reg NMS at 0.30 cents per share for protected quotes). Inverted venues — Cboe BYX, Cboe EDGA, Nasdaq BX — charge makers and rebate takers, so their queues are shorter and fill earlier; a fill on an inverted venue often precedes a price move on the primary, which is itself a signal. Futures trade on a single central book, so fee structure differentiates member tiers rather than venues. Routing and rebate assumptions belong in the cost model, not in a footnote.

## Auctions, halts, and session boundaries

Opening and closing auctions concentrate volume and set official prices, but continuous-session scalping signals do not extend across them: order-flow state resets. Equities carry limit-up/limit-down price bands (roughly 5 to 20 percent depending on tier and price, tightened logic near the open and close) and market-wide circuit breakers at 7, 13, and 20 percent on the S&P 500. Futures have daily price limits and velocity logic that can lock or halt the book. The design must state its behavior at these boundaries: flatten before auctions it does not explicitly model, cancel resting orders on a halt, and re-baseline all stateful signals at reopen rather than trusting pre-halt state.

## Adverse selection

Passive fills are not random samples of flow: the counterparty chose to trade with you, and informed flow chooses well. Measure this with markouts — the signed mid-price move after each fill at horizons of 100 ms, 1 s, 10 s, and 60 s. A passive strategy whose fills mark out negative at every horizon is paying adverse selection greater than the spread it captures, and no fee rebate will save it. Markout curves, split by queue position at fill and by time of day, are mandatory diagnostics for any passive design.

## Common pitfalls

- Assuming a fill whenever the backtest price touches the order's level, ignoring queue position; this overstates passive fill rates massively on large-tick instruments.
- Porting a FIFO strategy to a pro-rata product (or the reverse) without redesigning sizing and cancel behavior.
- Treating a size-increase modify as priority-preserving; it re-queues the order at the back on FIFO venues.
- Ignoring the spread-to-tick regime, so a queue-priority edge is tested on a small-tick instrument where it cannot exist.
- Carrying signal state across halts or auctions, so the first post-reopen trades fire on stale order-flow context.
- Reporting fill counts without markouts, hiding adverse selection behind a high hit rate.

## Definition of done

- [ ] The traded instrument's allocation rule (FIFO, pro-rata, hybrid) is stated and the design depends on the correct one.
- [ ] The spread-to-tick regime is stated and consistent with the edge mechanism.
- [ ] Queue-position handling is specified: exact tracking with MBO data, or a conservative estimate with MBP data.
- [ ] Venue fee model and routing assumptions are recorded in the cost model.
- [ ] Behavior at auctions, halts, price bands, and session boundaries is specified, including signal re-baselining.
- [ ] Markout analysis at 100 ms, 1 s, 10 s, and 60 s horizons is part of the evaluation plan handed to quant_trader.
