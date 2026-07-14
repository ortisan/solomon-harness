---
name: fees-rebates-and-cost-model
description: Governs the cost model that precedes any signal work: fee structures and tiers, rebates, per-contract versus basis-point costs, and the break-even arithmetic deciding whether a scalping idea can exist. Use when sourcing a venue fee schedule, building a cost model, or checking if a strategy's edge survives real costs.
---

# Fees Rebates And Cost Model

This skill governs the cost model that comes before any signal work: fee structures and tiers, rebates, per-contract versus basis-point costs, and the break-even arithmetic that decides whether a scalping idea can exist at all. Scalping economics die on costs first — gross edges are fractions of a tick to a few ticks, costs are charged on every one of thousands of trades, and a cost error of half a tick flips a profitable book to a losing one. The cost model is therefore written, sourced from the venue's current schedule, and versioned; it is never an estimate typed from memory.

## Fee structures by asset class

- Futures: costs are per contract, per side — exchange fee plus clearing fee plus regulatory fee plus broker commission. The all-in number varies by membership tier and broker; retail all-in is commonly a few dollars per round turn on full-size index contracts and one to two dollars on micros. Fees are fixed while tick values differ per product, so always convert costs into ticks per round turn for the specific contract.
- US equities: per-share economics with venue-dependent sign. Maker-taker venues charge takers up to the Reg NMS access-fee cap (0.30 cents per share on protected quotes) and pay makers a rebate; inverted venues reverse the sign. Add SEC Section 31 fees on sells and FINRA TAF, which are small per share but real at scalping volumes. The liquidity flag on each fill (added versus removed, and on which venue) decides its cost, so the cost model needs the fill classification, not just the share count.
- Crypto: basis-point maker and taker rates on notional, tiered by rolling volume; taker commonly around 2 to 5 bps at retail tiers, maker near zero and sometimes negative (a rebate) at high tiers or on maker-incentive programs. Perpetuals add funding transfers on positions held across funding timestamps — usually irrelevant to second-scale scalps, but the model must state that assumption.

Tiers matter more than signal tweaks: moving one taker tier down can add more expectancy than a month of feature engineering. Model the tier the account will actually have during validation, and note the tier at which the strategy becomes viable.

## Per-contract versus basis-point thinking

Per-contract costs are constant in ticks regardless of price level; basis-point costs scale with notional. This changes sizing logic: on futures, cost per round turn in ticks is fixed, so edge-per-trade thresholds are stable; on crypto, the same bps fee is more ticks when volatility compresses spreads relative to price. Keep one canonical unit — ticks per round turn for the instrument under design — and convert everything into it, including expected slippage.

## Break-even math, worked example

Futures example, E-mini S&P 500 (ES): tick value 12.50 dollars. Assume retail all-in fees of 4.00 dollars per round turn, which is 4.00 / 12.50 = 0.32 ticks. A strategy that takes liquidity on both entry and exit crosses the spread twice; with ES quoted one tick wide, that is 2 ticks of spread cost. Required gross edge per round trip: 2.00 + 0.32 = 2.32 ticks just to break even, before adverse selection and stop slippage. If the signal's realistic gross edge is 1 tick, the taker-taker design is dead regardless of hit rate — the only viable shapes are passive on at least one leg (cutting spread cost to 1 tick or less, at the price of queue risk) or a longer holding period with a larger gross edge.

Micro contract check (MES): tick value 1.25 dollars, retail all-in around 1.30 dollars per round turn, which is 1.04 ticks in fees alone — micros are proportionally far more expensive, and many designs viable on ES are structurally impossible on MES. Crypto check: taker-taker at 4 bps per side is 8 bps per round trip plus roughly 1 bp expected slippage; a scalp targeting 12 bps gross keeps 3 bps — thin enough that one fee-tier assumption error erases it.

Generalize with expectancy: E = p_win x avg_win - (1 - p_win) x avg_loss - costs_per_round_trip, all in ticks. Solve for the required win rate at the designed stop and target before writing any signal code; if the required win rate is implausible for the signal class (anything above roughly 70 percent should raise eyebrows), redesign or abandon.

## Rebate capture is conditional

Rebates only accrue on fills classified as passive, and passive fills carry queue risk and adverse selection (see the spread-capture skill). A cost model that books maker rebates on 100 percent of intended-passive orders overstates PnL twice — some orders cross on arrival (no post-only protection) and some never fill at all (opportunity cost). Book rebates only at the fill rates the queue model certifies, and carry an explicit adverse-selection charge from measured markouts next to every rebate line.

## Common pitfalls

- Writing the signal first and discovering afterward that break-even is 2.3 ticks against a 1-tick edge.
- Using published headline fees instead of the account's actual tier and broker all-in.
- Booking maker rebates on every intended-passive order, ignoring crossed-on-arrival and never-filled orders.
- Comparing strategies across instruments in dollars instead of ticks per round turn, hiding that micros cost proportionally more.
- Omitting regulatory and clearing add-ons that look negligible per trade and compound over thousands of trades.
- Letting the cost schedule go stale; venues change fees, and last year's model silently corrupts this year's validation.

## Definition of done

- [ ] The cost model is written, cites the venue schedule version and date, and states the account tier assumed.
- [ ] All costs are converted to ticks (or bps) per round turn for the specific instrument, including expected slippage.
- [ ] The break-even edge per trade and the required win rate at the designed stop and target are computed before signal work.
- [ ] Rebates are booked only at queue-model-certified passive fill rates, with an adverse-selection charge alongside.
- [ ] Funding, regulatory, and clearing components are included or explicitly ruled out with a reason.
- [ ] The same cost model file is referenced by the backtest specification handed to quant_trader.
