---
name: daytrade-setups-and-session-structure
description: Governs intraday setup design around session structure — opening range breakouts, VWAP reversion and trend-day continuation, gap and relative-volume classification, time-of-day liquidity, and explicit no-trade filters, each setup with trigger, invalidation, and R multiple. Use when designing or reviewing a daytrade setup with minutes-to-hours holds or deciding whether a session is tradeable at all.
---

# Daytrade Setups And Session Structure

This skill governs how the swing_trader designs intraday setups with minutes-to-hours holds around the structure of the trading session: which phase of the day supplies which edge, how gaps and relative volume classify the day before the first trade, and which conditions mean not trading at all. Every setup ships with three numbers — an entry trigger, an invalidation level, and the typical R multiple it must deliver to clear costs — or it is not a setup.

## Session phases

The cash session is three regimes, not one market:

- Open and first 30-60 minutes: the day's highest volume and volatility; in liquid US equities roughly a quarter to a third of full-day volume prints in the first hour. Directional edges (opening range breakouts, gap continuation) live here. Spreads are widest in the first minutes; entries before roughly 9:35 ET pay measurably more slippage, so triggers either wait out the first 5 minutes or budget the extra cost explicitly.
- Midday, roughly 11:30-14:00 ET: volume drops to a fraction of the open, ranges compress, and mean reversion toward VWAP dominates. Breakout entries fired midday have the lowest follow-through of the day. The default midday stance is flat, or managing positions opened earlier — not initiating breakouts.
- The close, from about 15:00 ET and the 15:50 ET MOC imbalance publication: volume returns; trend days tend to accelerate into the close while range days pin near VWAP or large strikes. The close is also the decision point where an intraday hold either flattens or becomes an overnight hold — that decision belongs to the overnight-risk skill, and its default answer for daytrade setups is flatten.

## Day-type classification before the first trade

- Gap classification: measure the overnight gap as a multiple of daily ATR(14), never in raw percent alone. Below 0.25x ATR: noise, run the normal playbook. Between 0.25x and 0.75x without a catalyst: gap-fill odds are material, reversion setups are eligible. Above 0.75x ATR with an identifiable catalyst (earnings, guidance — from research_analyst's calendar): continuation regime, fading is forbidden, only gap-and-go setups qualify. A large gap with no identifiable catalyst is a warning, not an edge.
- Relative volume (RVOL): cumulative volume at time t divided by the 20-session average cumulative volume at the same time of day. RVOL below about 1.0 disqualifies breakout setups — a breakout without participation is a fade in disguise. RVOL above 1.5-2.0 alongside a catalyst marks a day worth full-size participation.

## Core setups

- Opening range breakout (ORB): fix the range as the first 15 or 30 minutes' high and low (one choice per strategy, fixed on the hypothesis card). Entry: buy stop (or sell stop) at the range extreme plus one tick, only if RVOL > 1.5 and gap classification permits continuation. Invalidation: price back inside the range beyond its midpoint, or a fixed stop of 0.5-1.0x the opening-range height beyond the break level, whichever is tighter. Typical R: 1.5R-2.5R targets; historical win rates run 35-45%, so expectancy dies unless winners are allowed to reach 2R or better.
- VWAP reversion: on non-trend days (gap < 0.25x ATR, RVOL near 1.0), fade extensions of 1.5-2.0 intraday standard-deviation bands away from VWAP, back toward VWAP. Entry: limit order at the band, not a market chase. Invalidation: a 5-minute close beyond the 2.5-3.0 band. Typical R: 1R-1.5R at a 55-65% win rate. Forbidden on classified trend days — reversion against a trend day is the single most expensive intraday error.
- Trend-day continuation: when the day classifies as a trend day (catalyst gap that holds, price persistently on one side of VWAP, RVOL > 1.5), buy pullbacks to VWAP or the 20-period EMA on 5-minute bars in the trend direction. Invalidation: a 5-minute close through VWAP against the trend. Typical R: 1.5R-3R, since trend days close near their extreme far more often than random days.

## When not to trade

No-trade filters are part of the strategy, not discretion: the first 5 minutes unless the setup explicitly prices the spread; FOMC, CPI, and payroll release windows per the event calendar; half-days and option-expiry pins; RVOL below 0.8; any name whose spread exceeds 10% of the intended stop distance. A no-trade decision on a signal day is logged in project memory like any other decision.

## Common pitfalls

- Trading midday like the open, because the follow-through statistics that justify breakout entries do not exist between 11:30 and 14:00.
- Fading a catalyst gap above 0.75x ATR, because catalyst gaps resolve by continuation often enough that the fade's loss tail destroys its win rate.
- Running ORB without the RVOL filter, because low-participation breakouts revert and turn a positive-expectancy setup into a coin flip with costs.
- Measuring gaps in dollars or raw percent, because the same 2% gap is noise in a high-beta name and a regime event in a utility; ATR multiples normalize it.
- Quoting stop distance without the opening-spread slippage, because a stop hit at 9:32 fills materially worse than the chart price implies.

## Definition of done

- [ ] Every setup states entry trigger, invalidation, and typical R multiple as numbers, plus the session phase in which it is allowed to fire.
- [ ] Gap classification (ATR multiples, catalyst check) and RVOL thresholds are explicit and fixed on the hypothesis card.
- [ ] No-trade filters are enumerated, including event windows sourced from research_analyst's calendar.
- [ ] The end-of-day flatten-or-hold rule is stated and consistent with the overnight-risk skill.
- [ ] The setup sheet is part of the hypothesis card handed to quant_trader for validation, and the handoff is logged in project memory.
