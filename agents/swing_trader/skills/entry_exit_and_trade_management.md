---
name: entry-exit-and-trade-management
description: Governs the mechanics of getting into and out of daytrade and swing positions — entry order selection, structure- and ATR-based initial stops with concrete multiples, scaling rules, trailing methods, time stops, partial profits, and R-multiple accounting. Use when specifying how a setup's entries, stops, and exits execute, or when auditing trade-management rules before validation.
---

# Entry Exit And Trade Management

This skill governs the execution mechanics of a swing or daytrade position: which order type carries each entry, where the initial stop goes and how it sizes the trade, how positions scale and trail, and how results are accounted in R multiples. The stance: management rules are part of the strategy, fixed on the hypothesis card before validation — a trade managed by feel is a different, unvalidated strategy.

## Entry order choice

The order type follows the edge, not convenience:

- Momentum triggers (breakouts, pullback reclaims, ORB) use stop-market or stop-limit orders placed at the trigger. Paying slippage to guarantee participation is correct here because momentum entries suffer adverse selection in reverse: a resting limit at the trigger fills preferentially on the attempts that fail. A stop-limit's cap is set 10-20 bps beyond the stop price in liquid names; wider caps in thin names or none at all (accept the market fill) when missing the trade costs more than the slippage.
- Reversion entries use limit orders at the band or level. Getting paid the spread by providing liquidity is part of a reversion edge's economics; chasing a reversion entry with a market order gives that component back.
- Naked market orders are replaced by marketable limits capped 5-15 bps through the touch, which bounds the fill in a fast tape without materially reducing fill probability in names above $50M average daily dollar volume.

## Initial stop placement

The stop is placed where the setup is falsified, then sized from — never the reverse:

- Structure-based (preferred): beyond the level that invalidates the thesis — below the pullback low, below the breakout pivot or breakout-day low, beyond the opening range — plus a noise buffer of 0.25-0.5x ATR(14) of the decision timeframe, because exact structural levels are where stops cluster and get swept.
- ATR-multiple fallback (when structure is far or absent): daytrade setups 1.0-1.5x ATR(14) of the intraday timeframe; swing setups 1.5-2.5x daily ATR(14). Below 1x daily ATR on a multi-day hold, normal noise stops the trade regardless of thesis; above 3x, the R denominator is so large that realistic targets cannot deliver 2R.
- The stop exists before the entry order is sent, defines position size via the position-sizing skill, and is never widened after entry. Widening a stop converts a defined 1R loss into an undefined one, which is the single behavior that invalidates R accounting.

## Scaling in and out

- Scaling in happens only on confirmation, never against the position: for example half size at the breakout pivot, the remainder on the first successful retest hold. Averaging down toward the invalidation level is forbidden — it concentrates size at the point of maximum thesis failure.
- Scaling out: a standard split takes one quarter to one third off at +1R, moving the stop on the remainder to breakeven at that point — not at entry. Moving to breakeven immediately after entry measurably degrades expectancy by converting normal post-entry noise into scratched winners; tying it to +1R keeps the initial R intact while removing tail risk on the remainder.

## Trailing methods

Pick exactly one per strategy on the card; switching trails mid-trade is live curve-fitting:

- Chandelier: highest close since entry minus 2.5-3.0x daily ATR(14) for swings, 2.0x intraday ATR for daytrades. Robust default; it widens in volatility and never moves down.
- Structure trail: exit on a close below the most recent confirmed higher low (or a 2-bar low for daytrades). Tighter and more regime-aware, but requires an unambiguous pivot definition.
- Moving-average trail: close below the 20-day EMA for momentum swings. Simplest; appropriate when the backtest shows the edge persists as long as the trend anchor holds.

## Time stops and R-multiple accounting

If a position has not reached +1R within half the median winner's time-to-1R from the backtest (typically 2-4 sessions for pullbacks, 20-40 minutes for ORB), exit at market: dead trades consume portfolio heat that live setups need. All results are recorded in R, where 1R equals the per-trade risk at entry: expectancy = win rate x average win (R) - loss rate x average loss (R). MFE and MAE distributions per setup are kept and reported, because they audit whether stops are too tight (large MAE on winners) and targets too near (large MFE beyond exit). Reports to quant_trader are stated in R and trade counts, not dollars.

## Common pitfalls

- Entering momentum triggers with resting limits, because the limit fills preferentially on failing attempts and misses the runners — inverted selection.
- Sizing first and placing the stop to fit the size, because the stop then sits at an arbitrary price instead of the falsification level.
- Widening a stop after entry, because it destroys the R definition that every downstream statistic depends on.
- Moving the stop to breakeven at entry, because normal noise then scratches trades the backtest counted as winners.
- Changing the trailing method mid-trade, because the exit distribution no longer matches anything that was validated.

## Definition of done

- [ ] Every entry states its order type (stop-market, stop-limit with cap, limit, marketable limit) matched to the edge type.
- [ ] The initial stop rule is explicit — structural level plus buffer, or ATR multiple within the stated bands — and is set before entry.
- [ ] Scaling, partial-profit, and breakeven rules are written with their R triggers.
- [ ] Exactly one trailing method is specified per strategy, with its parameters.
- [ ] Time-stop values are derived from backtest time-to-1R statistics.
- [ ] All management rules appear on the hypothesis card handed to quant_trader; R-based accounting (expectancy, MFE/MAE) is the reporting format.
