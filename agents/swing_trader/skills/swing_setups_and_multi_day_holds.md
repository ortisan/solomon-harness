---
name: swing-setups-and-multi-day-holds
description: Governs multi-day swing setup design — momentum continuation versus mean reversion, pullback-to-trend entries, breakout bases, catalyst-driven swings such as post-earnings drift, multi-timeframe alignment, and holding-period selection matched to edge half-life. Use when designing a days-to-weeks setup, choosing between continuation and reversion logic, or timing a swing entry off a daily signal.
---

# Swing Setups And Multi-Day Holds

This skill governs the design of swing setups held from days to a few weeks: which of the two opposing bar-level edges (momentum continuation, short-horizon mean reversion) applies, how the canonical setups are specified, and how timeframes divide the labor so the daily chart decides, the weekly chart vetoes, and the intraday chart only times. The stance: continuation and reversion are anti-correlated edges, and applying one's rules in the other's regime is the category error that produces most swing losses.

## Continuation versus mean reversion — the regime decides

- Momentum continuation: instruments in an established trend continue over days to weeks. Qualification is mechanical, not visual: price above a rising 50-day SMA, 20-day above 50-day, and 3-6 month relative strength in the top quintile (or decile, per the card) of the tradeable universe. Continuation setups are the only ones allowed in qualified names.
- Short-horizon mean reversion: liquid large caps that extend 2-3+ daily ATRs from a reference (5-day mean, 20-day EMA) without a catalyst tend to snap back over 1-5 sessions. Reversion is forbidden on names with a fresh catalyst — a catalyst move is information, not noise, and fading information is how reversion books blow up.

One strategy, one edge. A card that mixes continuation triggers with reversion exits has no identifiable edge to validate.

## Pullback-to-trend entries

The workhorse continuation setup. Qualify the trend as above, then require: a pullback of 3-8 daily bars against the trend, on contracting volume, into a defined support zone — the 20-day EMA, the prior breakout level, or the 38.2-50% retracement of the last upswing. Trigger: a buy stop above the prior day's high (the first sign demand has returned), or a confirmed higher low on the 65-minute chart for earlier timing. Invalidation: the pullback low, minus a noise buffer of 0.25x ATR(14). Typical geometry: entry-to-stop around 1.5-2x daily ATR, targets at 2R-3R or a trailed exit, holds of 3-15 sessions. Skip pullbacks deeper than 65% of the prior swing — statistically those are reversals wearing a pullback's shape.

## Breakout bases

Buy strength leaving consolidation. A valid base: at least 4 weeks sideways, correction depth under 15-25% (tighter in strong tapes), volatility contraction — each successive pullback inside the base smaller than the last — and volume drying up near the pivot. Trigger: buy stop above the pivot, with breakout-day volume required at 1.5x the 50-day average or better; without the volume the breakout is not confirmed and the entry is skipped or cut to half size. Invalidation: a daily close back inside the base, or below the breakout day's low. Breakouts fail or retest often — roughly half return to the pivot — so the standard plan is partial size at the pivot and the remainder on the first successful retest hold.

## Catalyst-driven swings

Post-earnings-announcement drift is the canonical one: a large positive surprise with raised guidance, gapping more than 1x ATR and closing in the top third of its daily range, tends to drift in the surprise direction for weeks. The catalyst quality assessment — surprise magnitude, guidance revision, accrual quality — comes from research_analyst, sourced and timestamped; the swing_trader turns it into rules: enter day one or two after the report (never before it — holding into a report is governed by the overnight-risk skill and defaults to no), stop below the gap day's low, hold 15-40 sessions or until the trail exits.

## Multi-timeframe alignment

Three timeframes, three jobs, strict hierarchy: the weekly chart is context — trend direction, base structure, major levels — and can veto but never generate a trade; the daily chart is the decision timeframe where every setup and signal bar is defined; the intraday chart (15-65 minutes) is execution timing only — it may refine the entry and tighten the initial stop, never create or invert the daily thesis. A 15-minute signal against the daily setup is not a counter-trade; it is noise.

## Holding-period selection

Match the hold to the edge's measured half-life, not to preference: mean reversion 1-5 sessions; pullback continuation 5-15; base breakouts and earnings drift 15-40. Add a time stop from the backtest's MFE profile: if a position has not reached +1R within half the median winner's time-to-1R, exit — capital sitting in a dead trade is risk budget denied to a live one.

## Common pitfalls

- Fading a catalyst move with reversion rules, because catalyst moves are repricings and the loss tail on fading them is unbounded relative to the edge.
- Buying pullbacks in unqualified trends, because a pullback in a downtrend is a downtrend.
- Taking breakouts without the volume confirmation, because low-volume breakouts revert at a rate that erases the setup's expectancy.
- Letting the intraday chart overrule the daily thesis, because it converts a defined swing system into undisciplined daytrading.
- Holding past the time stop on hope, because the backtested edge has a half-life and the position is outside it.

## Definition of done

- [ ] The strategy commits to one edge (continuation or reversion) with mechanical regime qualification rules.
- [ ] Every setup states trigger, invalidation, typical R, and holding-period band as numbers.
- [ ] Catalyst inputs are sourced from research_analyst with timestamps; no self-originated fundamental claims.
- [ ] Timeframe roles are stated: weekly context, daily decision, intraday timing only.
- [ ] The time-stop rule is derived from backtest MFE statistics and stated on the card handed to quant_trader, with the handoff logged in project memory.
