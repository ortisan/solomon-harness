---
name: slippage-and-transaction-costs
description: Sets the minimum transaction-cost model of half-spread plus square-root market impact plus explicit fees, conservative defaults by asset class and trading frequency, and the mandatory cost-sensitivity analysis. Use when modeling fills, estimating costs, or reviewing a backtest for a zero-cost or fixed-cents assumption.
---

# Slippage and Transaction Costs

Transaction costs decide whether a paper edge is a real one, and this skill sets the minimum cost model (half-spread plus square-root impact plus explicit fees), the conservative defaults per asset class and trading frequency, and the mandatory sensitivity analysis. Zero-cost or fixed-cents assumptions are the single most common way a backtest lies.

## The minimum cost model

Every fill pays three components; model each explicitly:

```
cost_per_fill = half_spread + market_impact + fees_and_financing
```

- Half-spread: trading at the touch costs half the quoted spread on entry and half on exit. Use time-of-day spreads if available — spreads at the open and close differ from midday by 2-5x on many instruments — otherwise a conservative per-instrument constant.
- Market impact: scales with participation, not raw notional (next section).
- Fees and financing: commissions, exchange and regulatory fees, borrow for shorts, and margin interest on borrowed capital.

## Impact: the square-root law

Empirically, impact grows with the square root of order size relative to available liquidity (Almgren, Thum, Hauptmann, Li, "Direct Estimation of Equity Market Impact", 2005; Toth et al., 2011; the relationship holds across asset classes and decades of data):

```
impact ~= Y * sigma_daily * sqrt(Q / ADV)
```

where Q is the order size, ADV the average daily volume, sigma_daily the daily volatility, and Y an empirical constant of 0.5-1.0 (use 1.0 when uncalibrated). Linear-impact assumptions understate cost for large orders and overstate it for small ones. Split impact into temporary (decays after your order; paid by you) and permanent (moves the price; paid by your later fills), and use Almgren-Chriss (2000) when scheduling execution across a session. Capacity falls out of the same law: the notional at which modeled impact consumes the expected edge per trade is the strategy's capacity, and it belongs on the hypothesis card.

## Fee schedules

Fees are lookup-able facts; never guess them at zero.

- US equities: commission 0.0005-0.005 USD per share at institutional and pro-retail brokers, plus SEC and TAF fees on sells; exchange maker rebates and taker fees around +/-0.2-0.3 bps.
- Futures: roughly 0.85-2.50 USD per contract all-in (commission plus exchange and NFA fees) for liquid CME contracts.
- Crypto: taker 2-10 bps, maker 0-2 bps on major venues, tiered by volume; add funding for perpetuals (funding can run to tens of bps per day in stressed regimes) and withdrawal costs.
- FX: the cost lives in the spread; majors 0.1-1 bps, minors and EM pairs materially wider.
- Borrow: general-collateral equities cost about 25-50 bps annualized to short; hard-to-borrow names run 2% to 50%+ with recall risk. Model HTB names explicitly or exclude them from the shortable universe.

## Conservative defaults by asset class and frequency

When uncalibrated, use these one-way slippage defaults (half-spread plus impact at modest size) and state them on the hypothesis card:

| Asset and frequency | Default one-way cost |
| --- | --- |
| US large-cap equities, daily rebalance | 5 bps |
| US small-cap equities, daily | 20-30 bps |
| Liquid index futures (ES, NQ), intraday | 0.25-0.5 ticks plus fees |
| Crypto majors (BTC, ETH), intraday | 5-10 bps |
| Crypto alts | 20-50 bps |
| FX majors | 0.5-1 bps |

Intraday, high-turnover strategies sit at the top of each range; monthly-rebalance portfolios at the bottom. Replace defaults with calibration from your own fills as soon as live data exists.

## Mandatory sensitivity analysis

- Rerun the full backtest at 1x, 2x, and 3x modeled slippage. If the edge disappears at 2x, the strategy is cost-fragile and likely not viable at scale; at minimum, flag it and size it down.
- Report cost share of gross PnL. Above 30-40% of gross eaten by costs, redesign or slow the strategy down; past that point the edge belongs to the broker and the exchange.
- Report the break-even cost: the one-way cost per trade at which net PnL is zero, compared against both the modeled and the stressed cost.
- High-turnover strategies are cost-dominated: annualized turnover times per-trade cost is a hard floor on the gross alpha required. Compute that floor before optimizing anything else.

## Common pitfalls

- Zero, or flat fixed-cents, cost assumptions on a high-turnover strategy.
- Linear impact extrapolated to large orders; under the square-root law the first slice of ADV costs far more per share than a linear model predicts at size.
- Midday spread estimates applied to strategies that trade the open or the close.
- Borrow ignored on the short book; a 10% HTB fee erases most short alphas.
- Funding omitted on perpetual futures; in trending regimes funding alone can exceed the edge.
- Capacity quoted without an impact model; capacity is a cost statement, not a hope.

## Definition of done

- [ ] Cost model applied inside every fill: half-spread + square-root impact (Y stated) + full fee schedule + borrow and financing.
- [ ] Fee and borrow numbers sourced from the actual venue or broker schedule, not guessed.
- [ ] Asset-class defaults table applied, or instrument-specific calibration cited, and recorded on the hypothesis card.
- [ ] Sensitivity run at 1x/2x/3x slippage; the edge survives 2x or the strategy is flagged cost-fragile and resized.
- [ ] Cost share of gross PnL and break-even cost per trade reported; cost share within the 30-40% budget.
- [ ] Capacity estimated from the impact model and stated on the hypothesis card.
