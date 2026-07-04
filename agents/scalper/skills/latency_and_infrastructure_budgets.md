# Latency And Infrastructure Budgets

This skill governs the latency budget of a scalping strategy: how to decompose it, what numbers are realistic per infrastructure tier, and why every strategy must state its latency tolerance on the hypothesis card before any code is written. Latency is not an implementation detail — it decides which signals are tradable at all, and a design that is honest about its tier avoids building a colo strategy on a retail connection.

## Budget decomposition

Decompose end-to-end reaction time into four measurable hops:

1. Feed: matching-engine event to your process holding a decoded update. Includes exchange publication, network transit, and feed-handler decode.
2. Signal: decoded update to a trading decision. Feature computation and model inference.
3. Order: decision to order on the wire. Serialization, pre-trade risk checks, gateway hop.
4. Ack: wire to exchange acknowledgment (and, for takers, to fill report). Network transit plus matching-engine processing.

The sum, feed-to-order-on-wire, is the tick-to-trade time; adding the ack leg gives the full reaction loop. Measure each hop separately with timestamps at the boundaries, because optimization effort goes where the budget says, not where intuition says. In most self-built systems the surprise is that hops 1 and 3 dominate while the model in hop 2 was micro-optimized for nothing.

## Realistic ranges by tier

- Retail REST API: 50 to 300 ms per request round trip, with jitter of the same magnitude. Polling REST for market data adds seconds of staleness. Viable only for signals with half-lives of minutes.
- Retail websocket (streaming data, websocket or FIX order entry over the public internet): roughly 10 to 100 ms reaction loops depending on geography and venue. The workable floor for hobby and small-account scalping of minute-scale signals.
- Cloud near the venue (a VPS or cloud instance in the same region or data center as the venue's gateways — the standard tier for crypto): 0.5 to 10 ms loops. Many crypto venues publish their region; being anywhere else donates milliseconds to competitors.
- Colocation with cross-connect, software stack (kernel-bypass networking, pinned cores, C++ or equivalent): tick-to-trade in the 10 to 100 microsecond range for a disciplined build.
- Hardware acceleration (FPGA parsing and triggering): sub-microsecond to a few microseconds tick-to-trade. This tier is an arms race with seven-figure budgets; a solo or small-team project should not design strategies that require it.

Numbers drift as venues upgrade; re-measure per venue rather than trusting a table, including this one.

## Clock synchronization

Latency numbers are only as good as the clocks. NTP over the public internet holds around 1 to 10 ms of error — useless for microsecond claims and marginal even for single-digit-millisecond ones. PTP (IEEE 1588) with hardware timestamping holds sub-microsecond error and is the standard in colo. Regulation sets the bar too: MiFID II RTS 25 requires venues and HFT members to sync within 100 microseconds of UTC with microsecond-granularity timestamps. Practical rule: cross-tier comparisons (your receive time versus exchange timestamps) are only meaningful within the sync error, so state the sync method next to every latency measurement. One-way latencies measured with unsynced clocks are fiction; measure round trips instead.

## Jitter and tails

Medians flatter systems; races are lost in the tails. Report p50, p99, and p99.9 for every hop. A system with a 200-microsecond median and 20 ms p99 loses precisely the bursts where scalping opportunities cluster — volatility spikes generate both the signal and the load that produces the latency tail. Common tail sources: garbage collection (use GC-free languages or arenas on the hot path), CPU migration and power states (pin and isolate cores), cold instruction and data caches after idle periods (keep-warm traffic), and coalesced timers. Backtests must be run at tail latency as well as median: an edge that exists at p50 latency and not at p99 will underperform live in exactly the moments that matter.

## Latency tolerance goes on the hypothesis card

Every strategy states, up front: the signal half-life (from the order-flow skill), the required reaction time with margin (reaction time at p99 no worse than roughly a third of the half-life is a sound default), and the infrastructure tier that delivers it. This single line kills fantasy designs early: a queue-position spread-capture strategy that must cancel before adverse ticks needs colo-class cancels and is not buildable on a 50 ms retail loop, while an imbalance-momentum strategy with a 30-second half-life tolerates retail websocket latency comfortably. The backtest handed to quant_trader must simulate the stated latency (median and tail), so the validation tests the strategy on the infrastructure it will actually have.

## Common pitfalls

- Designing the strategy first and discovering the required tier afterward, instead of stating latency tolerance on the card up front.
- Quoting one-way latencies measured with NTP-synced clocks as if they were microsecond-accurate.
- Optimizing the signal computation while the feed handler and order path hold 90 percent of the budget, because no one measured per hop.
- Reporting median latency only; the p99 tail is where races are decided and where money is lost.
- Backtesting at zero or median latency for a strategy whose edge depends on cancel speed.
- Assuming a venue's geography instead of verifying it, then donating milliseconds from the wrong region.

## Definition of done

- [ ] The latency budget is decomposed into feed, signal, order, and ack, each with measured numbers.
- [ ] p50, p99, and p99.9 are reported per hop, with the clock-sync method stated.
- [ ] The hypothesis card states signal half-life, required reaction time with margin, and the infrastructure tier.
- [ ] The stated tier is one the project can actually operate; no colo-dependent design on a retail budget.
- [ ] The backtest specification handed to quant_trader injects the stated median and tail latencies.
- [ ] Latency is re-measured after any infrastructure or venue change, and the card is updated.
