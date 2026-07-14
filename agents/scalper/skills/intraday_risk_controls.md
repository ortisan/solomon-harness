---
name: intraday-risk-controls
description: Governs the risk envelope a scalping strategy carries from day one: per-trade stops in ticks, a daily loss limit with a hard kill switch, position caps, fat-finger bounds, and cancel-on-disconnect. Use when designing a scalping strategy's risk controls or confirming they were fixed before the signal.
---

# Intraday Risk Controls

This skill governs the risk envelope every scalping strategy carries from design day one: per-trade stops in ticks, a daily loss limit backed by a hard kill switch, position and order-rate caps, fat-finger bounds, cancel-on-disconnect, and defined circuit-breaker behavior. A scalping edge is a small positive expectancy multiplied by thousands of trades; one uncontrolled loss erases weeks of it, so the controls are designed before the signal and are not tunable by the strategy they constrain.

## Per-trade stops, in ticks

Stop distance is a design-time number in ticks, derived from the signal's noise band, not from a dollar amount a person finds comfortable. Typical scalping stops sit within a few ticks to roughly ten ticks of entry; a stop beyond that means the trade is not a scalp. Rules: place the stop as a resting order where the venue supports it (reduce-only stop or stop-limit), not as a mental level a process might fail to act on; assume one to two ticks of slippage on stop execution in the economics, more in fast markets; and never widen a stop on an open position — widening converts a bounded loss into a discretionary one. The stop distance interacts with the cost model: with a 4-tick stop and a 1-tick target, the win rate must clear 80 percent before costs, so the card must show the stop, target, and required win rate together.

## Daily loss limit and the hard kill switch

The daily loss limit bounds the worst day. Set it from the strategy's own statistics — two to three times the expected daily standard deviation of PnL is a common calibration — or a fixed amount the account can lose without impairing operation, whichever is smaller. The limit is enforced by a hard kill switch with these properties:

- It runs outside the strategy process (separate process or venue-side risk control), so a wedged or misbehaving strategy cannot ignore it.
- On trigger it cancels all open orders, flattens the position with marketable orders, and locks trading for the rest of the session.
- Re-enable requires a human decision after review, never an automatic timer.
- It counts realized plus marked open PnL, including fees, so an open loser cannot hide the breach.

Venue- or broker-side backstops (exchange risk limits, broker daily loss settings) are set slightly wider as the last line; the local kill switch should always fire first.

## Position, rate, and fat-finger caps

- Max position: an absolute cap in contracts or shares per instrument, enforced pre-trade. Sized so a full position at the stop distance loses a small, stated fraction of the daily loss limit.
- Max order rate: orders per second and messages per second caps, below both the venue's limits and the level at which messaging-efficiency penalties start. Rate-limit breaches on the venue side lead to throttles or disconnects at the worst possible moments.
- Fat-finger bounds: a maximum single-order size, a maximum notional, and a price collar rejecting any order priced more than a stated number of ticks or percent away from the last trade or mid. These catch code bugs as often as human error — a mis-scaled signal emitting a 100-lot order should die at the risk check, not at the exchange.
- Order-count and cancel-ratio watchdogs: an abnormal burst of orders or cancels (for example, ten times the rolling baseline) trips the strategy into a quote-pulled safe state pending review.

## Cancel-on-disconnect and connectivity

Enable venue-side cancel-on-disconnect on every session that carries resting orders, so a dropped connection cannot leave live quotes unattended (CME offers it natively; most crypto venues expose a per-connection setting or a cancel-after timer). Pair it with an application-level heartbeat: if the strategy stops receiving market data for a stated interval, it must assume its view is stale, cancel what it can, and stand down. After reconnect, trading resumes only once open orders and position are reconciled against the venue — the reconnect procedure from the execution skill is itself a risk control.

## Circuit breakers, halts, and price bands

Define behavior for the market's own interruptions before they happen. On a trading halt or a limit-locked book: cancel all resting orders immediately, mark the position against the last reliable price, and do not attempt to trade the reopen without a re-baselined signal state. Equity strategies must respect limit-up/limit-down bands (orders priced through a band are rejected or repriced by the venue — handle that reject class explicitly); index-linked strategies must know the market-wide circuit-breaker levels at 7, 13, and 20 percent and stand down when one is struck. Reopens after halts are auction-like and adversarially fast; the default policy is to stay flat through them unless the strategy explicitly models them.

## Common pitfalls

- A kill switch implemented inside the strategy process, which dies with the process it was meant to police.
- Counting only realized PnL toward the daily limit, letting an open loser breach it invisibly.
- Widening a stop on an open position, converting a designed 4-tick loss into an improvised 40-tick one.
- No price collar, so a sign or scaling bug in the signal sends an order the book will happily fill far from fair value.
- Resting orders on a session without cancel-on-disconnect, leaving live quotes orphaned by a network blip.
- Automatic re-enable after a risk trip, which turns a circuit breaker into a loss oscillator.

## Definition of done

- [ ] Stop distance in ticks, target, assumed stop slippage, and the implied required win rate are on the hypothesis card.
- [ ] The daily loss limit is stated, counts realized plus marked open PnL including fees, and its calibration is documented.
- [ ] The kill switch runs outside the strategy process, cancels and flattens on trigger, and requires human re-enable.
- [ ] Max position, max order rate, max single-order size, max notional, and a price collar are enforced pre-trade.
- [ ] Cancel-on-disconnect is enabled on every session with resting orders, and the reconnect-reconciliation procedure is written.
- [ ] Halt, price-band, and circuit-breaker behavior is specified, including the reject-handling for band-priced orders.
- [ ] All limits live in configuration owned by risk review, not in strategy code that could tune its own cage.
