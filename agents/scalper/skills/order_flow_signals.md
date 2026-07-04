# Order Flow Signals

This skill governs how the scalper constructs short-horizon signals from order flow: book imbalance, aggressor-classified trade flow, and footprint delta, each with a measured half-life in seconds and an honest account of alpha decay and crowding. A signal without a measured horizon and a stated decay assumption is a chart pattern, not an input to a strategy.

## Order-book imbalance

The simplest and most studied predictor is queue imbalance at the touch: QI = (Qb - Qa) / (Qb + Qa), where Qb and Qa are displayed bid and ask sizes at the best levels. On large-tick instruments QI predicts the direction of the next mid-price move over horizons of roughly one to ten seconds, with predictive power concentrated when one queue is nearly empty. Depth-weighted variants extend the sum over the top three to five levels with exponentially decaying weights, trading a small gain in stability for exposure to spoofable deep levels.

Order-flow imbalance (OFI, in the sense of Cont, Kukanov, and Stoikov) is the event-based refinement: net signed change in liquidity at the touch from adds, cancels, and trades over a window. OFI relates near-linearly to contemporaneous price change and is more robust than raw QI on venues with heavy quote churn. Both families require an event-level feed; conflated or snapshot data destroys them.

## Aggressor classification

Trade-flow signals need each trade signed by aggressor. Prefer the exchange's own flag: CME MDP 3.0 carries the aggressor side, and most crypto venues mark the taker. When no flag exists, classify:

- Lee-Ready: sign by the quote rule (above mid is a buy, below mid is a sell) and fall back to the tick test at the mid. Accuracy on modern data is imperfect — expect a high-single-digit to mid-teens percent error rate, worse when quotes are stale relative to trade timestamps — so align trades to the prevailing quote with care.
- Bulk volume classification (BVC): allocate each bar's volume between buys and sells using the CDF of the standardized price change. BVC needs no per-trade quotes and behaves well on aggregated or noisy data, but it is a statistical allocation, not a per-trade truth, and per-trade logic must not be built on it.

State which classifier the strategy uses and carry its error rate into the evaluation: a signal that survives only under perfect classification does not survive.

## Footprint and delta

Footprint charts organize aggressor volume per price level per bar; delta is aggressive buy volume minus aggressive sell volume. Useful constructs: cumulative delta and its divergence from price (price rises while cumulative delta falls suggests passive absorption of buying), and absorption events, where heavy aggressive volume hits a level that keeps refreshing without price progress. These are readable, mechanical descriptions of the same event stream as OFI; treat them as features to test, not as a discretionary art form. Every footprint construct used must reduce to a computable definition on the tick stream.

## Half-lives measured in seconds

Every signal gets an information-decay curve: correlation of the signal with forward mid-price returns at horizons of 250 ms, 1 s, 5 s, 10 s, 30 s, and 60 s. The half-life is where predictive power drops to half its peak. Book-imbalance signals typically live in the one-to-ten-second range; trade-flow bursts can be shorter. The half-life is a hard constraint on the whole design: if the end-to-end reaction time (feed to order to ack) is not comfortably shorter than the half-life, the strategy trades on expired information and its backtest edge is an artifact. This number goes on the hypothesis card next to the latency budget.

## Alpha decay and crowding

Be honest about what these signals are worth in the present, not in the papers that made them famous. Queue imbalance and OFI are public knowledge and heavily traded; on major futures and large-cap equities, the residual edge after competition is small, short-lived, and capacity-constrained to a handful of contracts or a few hundred shares per event. Expect live performance below backtest even with a conservative fill model, and measure the gap: recompute the signal's realized edge on live fills monthly, and retire it when the edge is statistically indistinguishable from costs. Crowding also raises tail risk — crowded signals fail together in fast markets, exactly when fills are worst. The hypothesis card must state assumed capacity and the expected live-versus-backtest haircut, and the review must treat an unexplained edge on a famous public signal as overfitting until proven otherwise.

## Common pitfalls

- Building imbalance signals from conflated or snapshot feeds, which erase the add/cancel events the signal is made of.
- Trusting Lee-Ready signs as ground truth and building per-trade logic on BVC's statistical allocations.
- Reporting a signal's strength at one horizon chosen after looking at the results, instead of the full decay curve.
- Trading a signal whose half-life is shorter than the system's measured reaction time.
- Ignoring spoofing and layering in deep-book features: displayed size that never intends to trade is a poisoned input, so weight-decay or touch-only variants must be compared.
- Assuming published-paper effect sizes still hold; competition has taken most of them.

## Definition of done

- [ ] Every signal has a computable definition on the tick or event stream, including the exact windows and weights.
- [ ] The aggressor-classification method is named (exchange flag, Lee-Ready, BVC) with its expected error rate.
- [ ] An information-decay curve exists per signal, and the half-life in seconds is on the hypothesis card.
- [ ] The half-life exceeds the measured end-to-end reaction time with stated margin.
- [ ] Assumed capacity and the expected live-versus-backtest haircut are stated.
- [ ] A retirement rule exists: the signal is dropped when live edge falls below costs at a stated confidence.
