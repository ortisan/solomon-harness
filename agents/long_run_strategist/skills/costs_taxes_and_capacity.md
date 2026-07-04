# Costs, Taxes and Capacity

This skill governs how the long_run_strategist prices the frictions that separate paper returns from realized ones: the cost stack paid at every rebalance, the tax posture of the design, and the capacity at which the strategy stops working. The stance: a long-horizon strategy's edge is usually small and its life is long, so frictions compound into the dominant term — every hypothesis card states its cost, tax, and capacity assumptions as numbers, and a design whose edge does not clear its friction floor with margin is rejected at the design stage, before anyone spends a backtest on it.

## The cost stack at rebalance

Each trade pays, at minimum: half the bid-ask spread (crossing from mid to touch), expected market impact, and commissions or fees. Spread is observable and should be sourced per asset class rather than assumed — a handful of basis points for large-cap equities and liquid futures, materially more for small caps, credit, and emerging markets. Impact grows with trade size relative to available liquidity; the standard working model is the square-root law, in which impact scales with volatility times the square root of the trade's fraction of average daily volume (ADV), stated here qualitatively as the shape to use rather than a calibrated constant. Two design consequences: costs are convex in trade size, so tranching a rebalance across several days cuts impact for slow strategies (long-horizon designs can afford patience — that is one of their genuine advantages); and the cost per unit of turnover belongs on the hypothesis card next to the turnover budget from the rebalancing skill, because their product is the annual friction floor the edge must clear. Realized-versus-assumed cost is a mandatory validation output from quant_trader: if live or simulated fills run worse than the card's assumption, the card is wrong and the strategy must be re-underwritten.

## Taxes: posture, not advice

Tax treatment is jurisdiction-specific, and this agent does not give tax advice; the rule is to defer to the account's jurisdiction and its professional advisers, and to design so that the strategy is not silently pre-committed to a tax-hostile shape. What the strategist owns is the tax posture of the design. Turnover converts unrealized gains into realized ones, and in taxable accounts under many regimes, short holding periods are taxed more heavily than long ones — so a high-turnover strategy can be attractive pre-tax and inferior after-tax to a duller, slower one. Design levers that respect this: keep holding periods long where the signal allows; harvest losses where the jurisdiction permits, while respecting its wash-sale-type repurchase restrictions; choose tax-aware lot selection (such as highest-in-first-out where allowed) so forced sales realize the smallest gains; widen no-trade bands on positions with large embedded gains, because their effective cost of sale is higher; and route naturally high-turnover sleeves into tax-advantaged wrappers where the mandate has them. The hypothesis card states whether targets are pre-tax or after-tax, and for taxable mandates it carries an explicit tax-drag assumption, marked as jurisdiction-dependent.

## Capacity estimation

Capacity is the asset level at which expected friction consumes the expected edge. Estimate it before anyone asks. The working method: fix a participation limit per name per day (commonly 5 to 10 percent of ADV, so the strategy's own trading does not dominate the tape), compute days-to-trade for a full rebalance at a candidate asset size, and push the candidate size up until either the days-to-trade breaks the signal's decay profile (the position cannot be built before the information is stale) or the square-root impact of the required trades erodes the edge below the card's minimum. Capacity therefore shrinks with turnover, with concentration, and with the illiquidity of the traded names — a small-cap value strategy has a small fraction of the capacity of a large-cap trend strategy, and premia discovered in illiquid corners degrade first as money arrives. State capacity as a range with its assumptions, not a single flattering number.

## When a strategy stops scaling

Scaling failure is gradual and measurable, not a cliff. The monitoring contract: track realized slippage against the card's cost model every period; track days-to-trade at current size; and pre-commit the response ladder — at the first sustained breach, slow the trading (more tranching, wider bands); at the second, cap inflows or shrink the sleeve; beyond that, close the strategy to new capital rather than let impact eat the existing investors' edge. The wrong response is quietly relaxing the cost assumptions on the card to make the numbers still work. Capacity decisions are design decisions and belong to this agent; the measurements that trigger them come from quant_trader's validation and live reconciliation.

## Common pitfalls

- Backtesting with zero or token costs, because a small edge times decades of turnover makes friction the first-order term, not a rounding error.
- Assuming linear impact, because impact is convex (square-root shaped) in trade size and linear models understate the cost of scaling exactly where it matters.
- Ignoring the tax posture of a taxable mandate, because a pre-tax winner with high short-term turnover can be an after-tax loser; state pre-tax versus after-tax targets on the card.
- Giving jurisdiction-specific tax advice instead of deferring, because the agent owns posture and design levers, not tax law.
- Quoting capacity as a single optimistic number without participation and decay assumptions, because capacity is a function of turnover, concentration, and liquidity, and it must be stated as such.
- Responding to realized slippage above model by editing the cost assumptions, because the card is the contract; the honest responses are slowing, shrinking, or closing.

## Definition of done

- [ ] The hypothesis card carries explicit per-asset-class spread, a square-root-shaped impact assumption, and fees, with the annual friction floor computed against the turnover budget.
- [ ] The edge claimed on the card clears the friction floor with stated margin.
- [ ] The card declares pre-tax or after-tax targets; taxable mandates carry a jurisdiction-dependent tax-drag assumption and the design's tax levers (holding period, loss harvesting, lot selection, band widening) are documented.
- [ ] Capacity is estimated as a range from participation limits, days-to-trade, and signal decay, with assumptions written down.
- [ ] The scaling monitors (realized slippage versus model, days-to-trade) and the pre-committed response ladder are specified.
- [ ] Cost and capacity validation outputs are named in the handoff to quant_trader.
