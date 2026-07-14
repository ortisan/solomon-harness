---
name: position-sizing-and-risk-limits
description: Governs how daytrade and swing positions are sized and bounded — fixed-fractional risk of 0.25-1% per trade, daily and weekly loss halts, portfolio heat and correlated-exposure caps, sizing from stop distance rather than conviction, and a pre-committed drawdown de-risking schedule. Use when sizing any position, setting loss limits for a strategy, or reviewing whether an open book is inside its risk envelope.
---

# Position Sizing And Risk Limits

This skill governs how much the swing_trader risks per trade, per day, per week, and per book: fixed-fractional sizing from stop distance, hard loss halts, heat and correlation caps, and a de-risking schedule written before the drawdown. The stance: sizing is where strategies die — a correct signal at the wrong size still ruins the account — so every size is derived from the stop distance and the risk fraction, and conviction is never an input.

## Fixed-fractional risk per trade

Risk a fixed fraction of current equity per trade, in the 0.25-1.0% band. The arithmetic behind the band: losing streaks are a certainty, not a tail case — at a 45% win rate, a 10-loss streak has better-than-even odds of appearing somewhere in a 500-trade sample. At 1% risk, ten consecutive losses draw the account down about 9.6%; at 2%, about 18.3%, which sits against the house 20% maximum-drawdown cap with no room for the next trade. So: 1.0% is the ceiling for a strategy with a live, quant_trader-validated track; 0.5% is the standard working size; 0.25% is where every new or re-validated strategy starts and stays until live results track the backtest.

The size formula is mechanical: shares = floor((equity x risk fraction) / (entry price - stop price)). The stop comes from the trade-management skill's falsification level; the size follows. A wide stop produces a small position automatically — that is the design, not a defect. Conviction, recent wins, and "obvious" setups change nothing: any sizing input other than equity, risk fraction, and stop distance is untestable and therefore unvalidatable.

## Daily and weekly loss halts

- Daily: stop initiating at -2R or -2% of equity on the day, whichever hits first. The halt is hard — no new entries, existing positions run their stops. Loss clusters are information: either the regime shifted against the playbook or execution is degraded, and both are diagnosed flat, not mid-fight.
- Weekly: -4R to -6R (or -4% of equity) halts the week and triggers a review against the strategy's backtest loss distribution. If the week's sequence sits outside the 95th percentile of backtested weekly losses, the strategy is suspended pending a quant_trader re-check rather than resumed on hope.

Halts are also tilt control: the empirical failure mode after a losing streak is size escalation to "get it back", and a hard halt removes the opportunity.

## Portfolio heat and correlated exposure

- Portfolio heat — the sum over open positions of (distance to stop x position size), the loss if every stop is hit simultaneously — is capped at 4-6% of equity for a swing book, 2-3% for a daytrade book. New entries that would breach the cap are skipped or sized down, best setup first.
- Correlated positions count as one slot: names in the same sector, or with 60-day return correlation above 0.7, share a cluster; a cluster holds at most 2 positions and its combined risk counts once against heat. Ten "independent" half-percent risks in one sector are a single 5% sector bet wearing ten names.
- Net directional exposure (long risk minus short risk) is capped as well, typically at the heat cap, so the book cannot become one implicit index trade.

## Drawdown-triggered de-risking schedule

Pre-committed, from peak equity: at -5%, cut per-trade risk to half its normal fraction; at -8%, to one quarter; at -12%, halt entirely and take the strategy back through review with quant_trader before any resumption. Re-risking uses hysteresis: restore one step only after recovering half of the drawdown that triggered the cut, so the schedule does not oscillate across a boundary. Two properties make the schedule legitimate: it is written before live losses (a de-risking rule invented mid-drawdown is emotion with arithmetic), and its steps sit inside the backtested drawdown envelope so normal fluctuation does not lock the strategy permanently under-sized.

Overnight holds add a gap adjustment on top of everything above — sizing against the gap-through-stop scenario is specified in the overnight-gap-and-event-risk skill and is mandatory for any position crossing the close.

## Common pitfalls

- Sizing by conviction or equal dollar amounts instead of stop distance, because risk per trade then varies silently by multiples between trades.
- Risking 2%+ per trade because the backtest win rate looks high, because the streak arithmetic above turns an ordinary losing run into a drawdown that breaches the house cap.
- Ignoring correlation and filling the book with one sector, because the positions win and lose together and the effective risk is the cluster, not the line items.
- Trading through a daily halt "because the next setup is clean", because the halt exists precisely for the state of mind that produces that sentence.
- Writing the de-risking schedule during the drawdown, because a rule invented under stress is a rationalization, not a rule.

## Definition of done

- [ ] Per-trade risk fraction is stated (0.25-1.0%), with the strategy's current tier and the criteria for moving tiers.
- [ ] The size formula is stop-distance-based and appears on the hypothesis card.
- [ ] Daily and weekly halt levels are stated in both R and percent of equity.
- [ ] Heat cap, cluster definition, per-cluster limits, and net-exposure cap are explicit.
- [ ] The drawdown de-risking schedule with hysteresis is written and dated before live exposure.
- [ ] The full sizing policy ships with the card to quant_trader, and any halt or de-risk event is logged in project memory.
