# Backtest Pipeline Standards

A backtest is an experiment, and this skill defines the protocol that makes its result admissible: which engine class to use and when, what the data must look like, how fills and costs are simulated, how the strategy is validated across time, and the minimum contents of the report. A pipeline that skips any of these produces a number, not evidence.

## Event-driven vs vectorized engines

Use both, in sequence, and know what each is for.

- Vectorized engines (vectorbt, plain NumPy/Polars) evaluate the whole signal matrix at once. They are 100-1000x faster and are the right tool for coarse parameter sweeps, universe scans, and killing bad ideas early. They cannot model order state: queue position, partial fills, latency, path-dependent sizing, or intrabar stop/limit interaction beyond crude approximations.
- Event-driven engines (nautilus_trader, backtrader, QuantConnect Lean) replay the market bar-by-bar or tick-by-tick through an order-management layer. They are the only engine class whose fills you may quote in a hypothesis-card verdict, because stops, limits, partial fills, and margin calls resolve in causal order.
- Rule: prune with a vectorized pass, confirm with an event-driven pass. The two must agree within tolerance on the surviving configuration (net Sharpe within ~0.2, trade count within ~5%); a larger gap means the vectorized approximation was hiding an execution effect, so investigate before trusting either number.

## Point-in-time data discipline

- Point-in-time only. Join every input with an as-of join on the timestamp the data became public, not the period it describes. Fundamentals use first-reported values, never restated ones; vendor revisions must carry revision timestamps.
- Survivorship-free universe. Include delisted, merged, and bankrupt names, and reconstruct index membership as it stood on each historical date. A current-membership S&P 500 universe adds roughly 1-4% of annual return bias to long equity strategies.
- Corporate actions: apply split and dividend adjustments as of the ex-date, computed only from information available then.
- Timestamps: store everything in UTC with explicit exchange-session calendars. A bar labeled by its open time but treated as fully known at the open is a full-bar lookahead.
- Snapshot the dataset: hash the exact files (or the database as-of version) used by the run and log the hash with the run.

## Fill assumptions

- Signals computed on bar t fill at bar t+1 at the earliest, typically the next open plus modeled slippage. Filling on the signal bar's close is lookahead.
- Liquidity cap: no fill may exceed a stated participation cap, default 10% of bar volume; the remainder becomes a partial fill carried forward or cancelled per the strategy's order policy.
- Limit orders fill only when the market trades through the limit price, not when it merely touches it; a touch-fill assumption grants free queue priority you will not have live.
- Stops fill at the stop price plus adverse slippage, and gap through: if the bar opens beyond the stop, fill at the open, not at the stop.
- Every fill carries full costs: commission, exchange and regulatory fees, half-spread plus impact slippage, and financing and borrow for shorts and margin. Report gross and net side by side; the net curve is the only one that counts.

## Walk-forward and CPCV validation

- Walk-forward: rolling (fixed-length train window) by default; anchored (expanding) only when the strategy's premise is a slowly accumulating structural relationship. Refit on each train window, trade the adjacent test window, and concatenate the test segments into the out-of-sample curve.
- Combinatorial Purged Cross-Validation (CPCV, Lopez de Prado, "Advances in Financial Machine Learning", 2018) for ML-labeled strategies: split the sample into N groups (N = 6-10 typical), test on every combination of k groups, purge training samples whose label windows overlap any test sample, and add an embargo after each test block of at least the label horizon (or 1% of the sample if longer) to absorb serial correlation.
- The final out-of-sample window is touched once, after all design decisions are frozen. Its verdict is recorded whether or not it is favorable.

## Reporting minimums

Every backtest report includes, at minimum:

- Equity curve, gross and net, log scale, with the out-of-sample segment visually marked.
- Drawdown table: the five deepest drawdowns with depth, start date, trough date, recovery date, and duration, plus the underwater plot.
- Trade-level statistics: trade count, hit rate, average win, average loss, payoff ratio, profit factor, average holding period, turnover, and time-in-market.
- Risk metrics: annualized net Sharpe and Sortino, annualized volatility, max drawdown, and cost share of gross PnL.
- Configuration block: parameters, data snapshot hash, code commit hash, seeds, engine and version.

Persist every run to project memory via `save_backtest` with parameters and metrics, so prior results and parameter history stay auditable and the trial count used for Sharpe deflation (see the overfitting skill) is honest. Reproducibility is absolute: pinned seeds, pinned data snapshot, logged config and code hash. A backtest you cannot rerun bit-for-bit is an opinion.

## Common pitfalls

- Quoting vectorized-engine fills as final results; without order state, stops and partial fills are fictions.
- Filling on the signal bar's close, or letting a limit order fill on a touch.
- A current-membership universe (survivorship) or restated fundamentals (restatement lookahead).
- Costs bolted on as a flat haircut after the run instead of inside each fill, which misprices high-turnover configurations.
- Walk-forward segments that overlap label horizons without purging; the OOS curve quietly becomes in-sample.
- Signal, execution, and accounting tangled in one module; keep three components with clear contracts, each independently testable.

## Definition of done

- [ ] Engine choice recorded: vectorized pass for the sweep, event-driven pass for the verdict, agreement within the stated tolerance.
- [ ] All inputs point-in-time via as-of joins; universe survivorship-free with historical index membership; corporate actions applied as of ex-date.
- [ ] Fills at t+1 or later, participation-capped (default 10% of bar volume), conservative limit/stop semantics, full costs in every fill.
- [ ] Walk-forward or CPCV with purging and embargo executed; final OOS touched exactly once and reported regardless of outcome.
- [ ] Report contains equity curve (gross and net), drawdown table, trade-level stats, risk metrics, and the full configuration block.
- [ ] Run reproduces bit-for-bit from the logged config, data hash, and seeds, and is persisted via `save_backtest`.
