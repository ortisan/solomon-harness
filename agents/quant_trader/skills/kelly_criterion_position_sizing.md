---
name: kelly-criterion-position-sizing
description: Derives the Kelly-optimal position-size fraction from an estimated trading edge — the discrete and continuous Kelly formulas, fractional Kelly rationale under estimation error, edge estimation from trade history with confidence-interval discounting, and multi-position correlation adjustment. Use when sizing a candidate position from an estimated win rate, payoff ratio, or return distribution, before the enforcement caps in risk_parameter_enforcement apply.
---

# Kelly Criterion Position Sizing

The Kelly criterion is the fraction of capital that maximizes the long-run geometric growth rate of an account given a known, stationary edge. This skill governs deriving that candidate fraction from an estimated win rate, payoff ratio, or return distribution — the math of optimal sizing, not its live enforcement, which stays in risk_parameter_enforcement. Adapted from agiprolabs/claude-trading-skills (MIT). Full Kelly is a theoretical ceiling nobody should trade at: every rule below turns an uncertain edge estimate into a fraction that survives real data.

## The discrete and continuous formulas

For a binary win/lose outcome, `f* = (b*p - q) / b`, where p is the probability of winning, q = 1-p, and b is the payoff ratio (average win / average loss). Edge = `b*p - q`; Kelly recommends betting only when edge > 0, and when edge <= 0 the correct fraction is zero, never a small positive size chosen out of optimism. An equivalent form, `f* = p - q/b`, collapses at even money (b=1) to `f* = 2p - 1`: a 55% win rate at 1:1 payoff gives f* = 10%, the same win rate at 2:1 payoff gives f* = 27.5%. For a continuous return stream — an equity curve rather than a trade ledger — use `f* = (mu - r) / sigma^2`, with mu the expected return, r the risk-free rate (0 for a self-funded book), and sigma^2 the return variance. This equals `Sharpe^2 / (2*sigma)`, so a strategy backtested to Sharpe 1.5 at 20% annualized volatility implies a full-Kelly fraction near 5.6 — unusable, and itself a sign the Sharpe estimate is optimistic.

## Why fractional Kelly, never full Kelly

Estimation error dominates every real edge estimate. A win-rate estimate from 100 trades carries a standard error of roughly sqrt(p*(1-p)/n), on the order of 5 percentage points; a true 55% edge sampling as 60% pushes full Kelly to overbet by roughly 50%, and overbetting *reduces* long-run growth below what a smaller, honest fraction would deliver. The penalty is asymmetric: betting at 2x the true optimum drives long-run growth to zero — the same as not trading — while betting at half the optimum still captures roughly 75% of the achievable growth rate. Full Kelly's drawdown is intolerable in practice: expected max drawdown runs 50-80% of the account, versus roughly 25-40% at half Kelly and 12-20% at quarter Kelly, for about 75% and 50% of full Kelly's growth respectively. Quarter Kelly (0.25x) is the default for 30-100 trades of unvalidated history; half Kelly (0.5x) is defensible only past 100+ trades of consistent, regime-tested performance. Below 30 trades, size at 0.10x or use fixed-fractional instead.

## Estimating the edge honestly

Compute directly from a net-of-cost trade ledger: `win_rate = wins / total_trades`, `payoff_ratio = mean(win_pnl) / abs(mean(loss_pnl))`, `edge = win_rate*payoff_ratio - (1 - win_rate)`; an edge computed on gross returns overstates every downstream fraction. Discount the win rate to the lower bound of a 95% Wilson score interval rather than the raw proportion — it shrinks toward 50% faster for small samples, the conservatism an undertested strategy needs. Minimum samples: 50 trades before computing Kelly at all, 100+ before half Kelly, 200+ before trusting an "excellent" edge above 20% as real rather than overfit. Edge below 2% sits inside the noise band of realistic costs and should not be sized; 2-10% is marginal and belongs at the smallest fractions; 10-20% supports standard sizing; above 20% warrants a search for a data leak or survivorship artifact before it is trusted.

## Multiple and correlated positions

Kelly fractions are additive only across independent bets; the sum of every open position's fraction must not exceed 1.0, and if it does, scale every fraction down proportionally. Correlated positions are one larger bet wearing several tickers: discount with an effective-bet-count adjustment, `n_eff = n / (1 + (n-1)*rho_avg)`, `scale = n_eff / n`, applied across the cluster — three positions on one macro theme at rho ~ 0.7 have an n_eff near 1.4, not 3. Cap total Kelly allocation at 0.6-0.8 of capital even when the arithmetic clears 1.0, to leave a cash buffer. Kelly's proof assumes a known, stationary edge; real trading violates that assumption as the edge decays with the regime and fees erode it below the gross estimate, so recalculate on a fixed cadence — weekly for anything faster than a multi-week hold — and subtract a conservative cost estimate before sizing.

## Wiring into the house workflow

Kelly sizing produces a candidate ceiling, not a deployable order. Any candidate sized this way still requires the mandatory model-hypothesis card (target Sharpe, drawdown limit, profit factor) and must clear quant_trader's backtest validation under backtest_pipeline_standards before it trades a dollar. Kelly's output is never the last word on size: risk_parameter_enforcement's position caps, drawdown governor, VaR/ES limits, and kill-switch conditions apply independently downstream and may cut a Kelly-derived size further; the tighter of the two numbers wins, always.

## Common pitfalls

- Full Kelly, or anything above half Kelly, sized off fewer than 100 trades — estimation error alone can double the true optimal fraction.
- Kelly computed on gross PnL, so the sized position rests on an edge fees and slippage have already erased.
- Treating correlated positions as independent bets and summing their Kelly fractions without an effective-bet-count discount.
- A stale Kelly fraction carried forward after the regime shifted, sizing a trade to an edge that no longer exists.
- Reading a Kelly fraction above 20-30% as a strong signal rather than as evidence the input estimate is wrong.
- Letting Kelly output bypass risk_parameter_enforcement's caps instead of feeding into them as one candidate input.

## Definition of done

- [ ] Kelly fraction computed with the correct formula for the data (discrete `f* = (bp - q)/b` for trade ledgers, continuous `f* = (mu - r)/sigma^2` for return streams), from net-of-cost PnL.
- [ ] Win rate discounted to its 95% Wilson lower bound, computed from at least 50 trades (100+ before half Kelly, 200+ before trusting an edge above 20%).
- [ ] Fractional Kelly applied per sample size and confidence (0.10x under 30 trades, 0.25x at 30-100, 0.5x at 100+), full Kelly never deployed.
- [ ] Correlated positions discounted by an effective-bet-count adjustment; total portfolio Kelly allocation capped at 0.6-0.8 even when the raw sum clears 1.0.
- [ ] Edge recalculated on a fixed cadence and re-derived after any regime shift, not set once at inception.
- [ ] Resulting candidate registered on the mandatory model-hypothesis card and validated through quant_trader's backtest pipeline before use; final position size deferred to risk_parameter_enforcement's caps and kill-switch conditions.
