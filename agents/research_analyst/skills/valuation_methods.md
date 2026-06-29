# Valuation Methods

This skill governs how the research_analyst estimates the intrinsic worth of an asset, triangulating discounted cash flow, relative multiples, and sum-of-the-parts into a defensible value range with an explicit margin of safety.

## Intrinsic value via discounted cash flow

Build a DCF from audited statements reported under US GAAP or IFRS, normalizing for one-off items before projecting. Forecast unlevered free cash flow (EBIT times one minus the cash tax rate, plus depreciation and amortization, minus capital expenditure and the increase in net working capital) over an explicit horizon of five to ten years. Discount at the weighted average cost of capital (WACC), where the cost of equity comes from CAPM (risk-free rate plus beta times an equity risk premium of roughly 4.5 to 5.5 percent for developed markets) and the after-tax cost of debt reflects the marginal borrowing rate. Weight the two by market values, not book values.

Terminal value usually dominates the result, so treat it with suspicion. Use the Gordon growth method (final-year FCF times one plus g, divided by WACC minus g) with a perpetual growth rate g no higher than long-run nominal GDP, typically 2 to 3 percent, and never above the discount rate. Cross-check that terminal value with an exit EV/EBITDA multiple consistent with mature peers. If the terminal value is more than 75 percent of enterprise value, shorten the explicit horizon or flag the fragility in the writeup.

Run a reverse DCF to keep yourself honest: hold the current market price fixed and solve for the growth and margin path the market is implying. If the implied revenue growth or steady-state operating margin exceeds anything the company has historically achieved, the market is pricing optimism the fundamentals do not support. Always publish a two-way sensitivity table flexing WACC by plus or minus 100 basis points against terminal growth by plus or minus 50 basis points, so the reader sees the value range rather than a single false-precision point estimate.

## Relative valuation multiples

Use multiples to sanity-check the DCF and to value businesses where cash flows are hard to forecast. P/E suits stable, profitable companies but breaks down at low or negative earnings. EV/EBITDA is capital-structure neutral, which makes it the right choice when comparing firms with different gearing, though it ignores capital intensity. P/B fits banks, insurers, and asset-heavy balance sheets where book value is economically meaningful. P/S is the fallback for early-stage or loss-making firms, and must be paired with a credible path to a target margin. Select comparables within the same GICS 2023 sub-industry, adjust for differences in growth and returns on capital, and prefer forward multiples over trailing ones.

## Sum-of-the-parts and balance-sheet quality

For conglomerates and holding companies, value each segment on the multiple or DCF appropriate to it, add net cash, subtract corporate overhead capitalized at a fair multiple, and apply a holding-company discount of 10 to 20 percent where minority stakes or governance frictions warrant it. Assess balance-sheet quality before trusting any equity value: examine the debt load against EBITDA, the debt-to-equity ratio versus sector norms, interest coverage, off-balance-sheet obligations, and the maturity wall. High indebtedness amplifies both upside and downside, so stress the cash flows against a downturn and confirm covenants hold.

## Margin of safety and the quant handoff

Anchor the buy decision on a margin of safety: require a 25 to 40 percent discount of price to your central intrinsic estimate, widening the cushion when forecast uncertainty or gearing is high. The valuation produces a qualitative thesis and a value range, not a validated performance figure. Any backtested, return-attributed, or statistically validated claim is handed to quant_trader, who owns the testing harness; the research_analyst never presents an unbacktested number as if it were validated, and labels every estimate as a forward judgment until quant_trader confirms it out of sample.

## Common pitfalls

- Letting terminal value drive the answer: a tiny change in g swings the verdict, so any thesis resting on heroic perpetual growth is unreliable.
- Single-point estimates without a sensitivity table: they hide model fragility and project false precision the data cannot support.
- Mismatched multiples: applying P/E to a loss-making firm or P/B to an asset-light software business compares unlike things and misleads.
- Stale or cross-sector comparables: peers outside the same GICS 2023 sub-industry distort the implied multiple and the conclusion.
- Ignoring the debt load: valuing equity without testing indebtedness, coverage, and the maturity wall overstates resilience in a downturn.
- Presenting an unbacktested figure as validated: performance claims belong to quant_trader, and skipping that handoff misrepresents rigor.

## Definition of done

- [ ] DCF built on US GAAP or IFRS statements normalized for one-off items, with WACC inputs and weights documented.
- [ ] Terminal value cross-checked against an exit multiple and confirmed to be a defensible share of enterprise value.
- [ ] Reverse DCF run, stating the growth and margin the current price implies.
- [ ] Two-way WACC and terminal-growth sensitivity table published alongside the central estimate.
- [ ] Relative multiples (P/E, EV/EBITDA, P/B, P/S) chosen to fit the business and drawn from same-sector comparables.
- [ ] Balance-sheet quality assessed via debt-to-equity, debt load to EBITDA, and interest coverage.
- [ ] Explicit margin of safety stated, sized to forecast uncertainty.
- [ ] Every performance or backtest claim routed to quant_trader, with no unbacktested number labeled as validated.
