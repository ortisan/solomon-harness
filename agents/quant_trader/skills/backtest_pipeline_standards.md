## Backtest pipeline standards


- Point-in-time data only. Use as-of joins so each bar sees only data available at that timestamp. No restated fundamentals, no forward-filled vendor revisions.
- Survivorship-free universe. Include delisted, merged, and bankrupt names. Reconstruct index membership as it was on each date.
- Realistic execution. Fill at the next bar after signal generation, never the signal bar's close. Model partial fills and liquidity caps (for example max `10%` of bar volume).
- Costs in every fill. Commission, exchange/regulatory fees, financing and borrow for shorts and leverage, and slippage. Report gross and net side by side; the net curve is the only one that counts.
- Separate signal generation from execution from accounting. Three components, clear contracts between them, each independently testable.
- Reproducibility: pin seeds, pin data snapshots, log the config and code hash with every run. A backtest you cannot rerun bit-for-bit is an opinion.
- Persist every run to project memory via `save_backtest` with parameters and metrics, so prior results and parameter history are auditable.
