---
name: execution-and-order-types
description: Governs the execution layer of a scalping strategy: the order types it may use, the venue-level protections it must enable, and the contracts for partial fills, rejects, and reconnects. Use when designing or reviewing a scalping strategy's order-type policy or execution contract.
---

# Execution And Order Types

This skill governs the execution layer of a scalping strategy: the order types it may use, the venue-level protections it must enable, and the contracts it must define for partial fills, rejects, and reconnects. At scalping horizons the execution specification is part of the strategy, not plumbing: the same signal with a different order-type policy is a different strategy with different economics.

## Core order types and when each is correct

- Limit (day or session): the default resting order. Its economics are queue economics; see the microstructure skill. Every resting limit needs an owner-defined maximum rest time or invalidation condition — a forgotten resting order is an unpriced option granted to the market.
- IOC (immediate-or-cancel): take liquidity now, cancel any unfilled remainder. The correct type for signal-triggered aggressive entries and for inventory shedding, because it cannot rest and get adversely selected later. Partial fills are normal and must be handled (see below).
- FOK (fill-or-kill): all-or-nothing immediacy. Use only when a partial position is strictly worse than none (for example, a two-legged trade where one leg alone is an unwanted exposure). On thin books FOK mostly kills; do not use it as a default.
- Post-only: guarantees maker treatment by rejecting or repricing the order if it would cross the book. Mandatory for spread-capture strategies whose economics assume the rebate; without it, a stale view of the book turns intended maker orders into taker fills at taker fees. Know the venue's variant: reject-if-cross versus reprice-to-best-passive behave differently under fast markets.
- Reduce-only: the order may only decrease position; common on derivatives venues. Mandatory for stops and exits, so a stale or duplicated exit cannot flip the position. If the venue lacks reduce-only, the OMS must enforce the equivalent check.
- Iceberg / display quantity: shows a slice, holds the remainder hidden. Hidden quantity ranks behind displayed quantity, and on most venues each refreshed slice re-enters the queue at the back — so icebergs trade queue priority for size concealment. For typical scalping sizes, icebergs are rarely justified; state the reason if used.

## Self-trade prevention

Any system running quoting and taking logic together, or multiple strategies on one account, must enable venue-side self-trade prevention (STP). Know the configured mode: cancel-newest, cancel-oldest, cancel-both, or decrement-and-cancel. The mode changes strategy behavior — cancel-oldest can silently kill a resting quote the spread-capture logic believes is alive, so the order-state tracker must consume STP cancels like any other unsolicited cancel. Wash trades are a compliance problem as well as an economic one; STP is not optional.

## Venue routing

Futures and most crypto products trade one central book, so routing reduces to connection and session management. Fragmented equities require a routing policy: which venues to rest on (fee versus queue-length trade-offs, inverted venues for urgency-sensitive fills), whether to use exchange routable orders or route in the OMS, and how the cost model accounts for per-venue fees and rebates. The routing policy is part of the hypothesis card's cost assumptions; a backtest that assumes primary-only fills while production sprays venues is testing a different strategy.

## Partial-fill handling contracts

Every order the strategy can send needs a written contract answering: what happens on partial fill, on full fill, on reject, on unsolicited cancel, and on timeout. The default contracts:

- Aggressive IOC entry partially filled: accept the partial as the position, recompute intended size from the signal, and do not chase more than a stated number of repricings (typically one).
- Resting quote partially filled: remainder stays with its queue priority; inventory logic updates immediately on each execution event, not when the order completes.
- Exit order partially filled: remainder must be re-sent or escalated (limit to marketable limit to market) within a stated time bound; an unfilled exit remainder is an unbounded risk.
- Reject: rejects are never retried blindly. Classify (risk-check reject, price-band reject, rate-limit reject) and route each class to a defined action; repeated rejects trip the strategy into a safe state.

Order-state tracking must be an explicit state machine (pending-new, acked, partially-filled, filled, pending-cancel, canceled, rejected), keyed by execution IDs with idempotent fill processing, because gateways redeliver. Position truth comes from reconciling execution events against the venue's position or drop-copy feed; never infer position from what was sent. After a disconnect, the first action is reconciliation — cancel-on-disconnect (see the risk skill) bounds the exposure, but open-order and position state must be rebuilt from the venue before trading resumes.

## Common pitfalls

- Using plain limit orders for exits where reduce-only (or an OMS equivalent) is available, allowing a duplicated exit to flip the position.
- Assuming post-only semantics without checking the venue's reject-versus-reprice variant.
- Treating rejects as retryable by default; a risk-check reject retried in a loop is how accounts blow through rate limits and bans.
- Processing fills keyed by order ID instead of execution ID, double-counting on gateway redelivery.
- Ignoring STP cancels in the order-state tracker, leaving the quoting logic convinced a dead order is alive.
- Backtesting with a routing and fee model different from the production routing policy.

## Definition of done

- [ ] Every order type the strategy uses is listed with the reason it is the correct type for that action.
- [ ] Post-only, reduce-only, and STP configuration (including mode) are specified per venue.
- [ ] The partial-fill, reject, unsolicited-cancel, and timeout contract is written for every order the strategy can send.
- [ ] Order state is an explicit state machine with idempotent, execution-ID-keyed fill processing.
- [ ] Position is reconciled against the venue feed, including a defined reconnect procedure.
- [ ] The routing policy and its fee consequences match between the backtest handed to quant_trader and production.
