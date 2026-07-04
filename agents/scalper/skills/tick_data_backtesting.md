# Tick Data Backtesting

This skill governs what a backtest must look like before the scalper hands it to quant_trader: tick or order-book event data, a queue-position model, conservative fill assumptions, simulated latency, exact fees and rebates, and sample sizes large enough to mean something. At second-to-minute horizons, a bar-level backtest is not a weaker version of the truth — it is a different, fictional strategy, because the entire edge lives inside the bar.

## Data requirements

- Resolution: tick-by-tick trades plus order-book updates. Market-by-price (MBP) depth is the minimum for passive strategies; market-by-order (MBO) is strongly preferred because it makes queue position exact. Taker-only strategies can survive on trades plus top-of-book quotes, but still need event-level data.
- Timestamps: both the exchange (matching-engine) timestamp and the local receive timestamp, at microsecond or better granularity. The difference between them is the feed latency the simulation must inject.
- Integrity: beware vendor conflation and aggregation — consolidated feeds that merge updates destroy the event sequences order-flow signals are built from. For crypto, capture websocket streams yourself and store raw messages; venue REST candles and even vendor "tick" exports are frequently reconstructed. Validate sequence numbers and document gap-handling; a silent gap becomes a silent look-ahead.
- Sessions and symbology: sessions, halts, auction phases, and contract rolls must be represented, because the strategy's boundary behavior (from the risk skill) is part of what is being tested.

## Queue-position modeling

Passive fills are the product being tested, so the fill model is the backtest. With MBO data, replay the book and track the order's exact position: fills occur when executions at the level consume the queue ahead. With MBP data, estimate conservatively: on join, queue-ahead equals the displayed size at the level; executions at the level reduce it; cancellations are assumed to come from behind the simulated order, so cancels never improve its position. This assumption is deliberately pessimistic — the optimistic alternative (pro-rata attribution of cancels) is the classic source of backtests that print money and live systems that do not.

## Conservative fill assumptions

- No fill at touch without a queue model. Price touching the order's level fills nobody in particular; the simulated order fills only when the modeled queue ahead is exhausted while the level still stands.
- A strictly pessimistic variant — fill only when price trades through the level — is the stress case every passive strategy should also be run under; an edge that survives trade-through-only fills is real with high confidence.
- Aggressive orders fill against the book as seen after the simulated latency, walk the displayed depth (no hidden-liquidity gifts), and pay the spread; unfilled remainders follow the strategy's stated partial-fill contract.
- The simulated order must not affect history it did not create: assume no market impact at small size, but cap tested size at a small fraction of displayed depth so the assumption stays defensible.

## Latency simulation

Inject the measured budget from the latency skill into the event loop: market data arrives late by the feed latency (the strategy decides on a stale book), and orders arrive at the exchange late by the order-path latency (the book has moved by the time the order lands). Run the backtest at least twice — at measured p50 and at measured p99 — and report both. The gap between the two results is the strategy's latency sensitivity, and it belongs on the hypothesis card. A cancel-dependent strategy simulated at zero latency is unfalsifiable marketing, not research.

## Fees, rebates, and cost accuracy

Apply the exact venue schedule for the account tier that will trade: per-contract exchange, clearing, and regulatory fees for futures; per-share fees or rebates by venue and liquidity flag for equities; basis-point maker and taker rates for crypto, at the realistic tier, not the best published one. Model rebates only on fills the queue model marks as passive. Include borrow or funding costs where positions can cross funding events. The cost model must be the same one from the fees skill, referenced, not re-invented.

## Minimum sample sizes

Scalping edges are fractions of a tick, so noise swamps small samples. Floors, not targets:

- Trades: at least 1,000 round trips; prefer 3,000 or more. With per-trade edge around a tenth of a tick and per-trade standard deviation of several ticks, a thousand trades barely resolves the sign of the mean.
- Days: at least 60 trading days, preferably 120 or more, so day-of-week and intraday seasonality do not masquerade as edge.
- Regimes: the window must span at least two volatility regimes — include scheduled-event weeks (CPI, FOMC) and quiet stretches — and results must be reported per regime, not only pooled.
- Independence: overlapping or re-sampled trades are not independent observations; count distinct round trips only.

An edge that only exists in one month, one regime, or one parameter setting is a fitting artifact until quant_trader's out-of-sample process says otherwise.

## Common pitfalls

- Backtesting a scalping strategy on bars, then citing the result as evidence of anything.
- Optimistic queue models that let cancels improve the simulated order's position.
- Zero-latency simulation of cancel- or race-dependent behavior.
- Applying published headline fees instead of the account's actual tier, or crediting rebates on fills the queue model cannot certify as passive.
- Vendor data with conflated updates or silent gaps feeding event-sequence signals.
- Declaring victory on 200 trades from three calm weeks.

## Definition of done

- [ ] Data is tick/event level with both exchange and receive timestamps; gaps and conflation are checked and documented.
- [ ] The queue model is stated (exact MBO replay, or conservative MBP estimate with cancels-behind assumption).
- [ ] No fill occurs at touch without queue exhaustion; the trade-through-only stress variant has been run.
- [ ] Measured p50 and p99 latencies are injected on both the data and order paths, with both results reported.
- [ ] Fees and rebates match the account's real schedule and the fees skill's cost model, per fill classification.
- [ ] Sample floors are met: 1,000+ round trips, 60+ days, two or more volatility regimes, reported per regime.
- [ ] The full specification (data, fill model, latency, costs, samples) is packaged in the handoff to quant_trader.
