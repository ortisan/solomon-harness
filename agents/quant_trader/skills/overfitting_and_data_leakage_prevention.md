## Overfitting and data-leakage prevention


This is where most strategies die in production. Treat it as the primary risk.

- Hold out a true out-of-sample period that you touch exactly once, at the end. If you peek and re-tune, it is no longer out-of-sample.
- Use walk-forward analysis for time series, never plain k-fold (rows are not independent).
- For ML labels, use purged k-fold or Combinatorial Purged Cross-Validation (CPCV) with purging and an embargo (Lopez de Prado) to remove train/test leakage from overlapping label horizons.
- Quantify selection bias. Report the Deflated Sharpe Ratio and the Probability of Backtest Overfitting (PBO); deflate the Sharpe by the number of trials you ran. Target PBO well under `0.5`, ideally `< 0.1`.
- Multiple-testing control: when comparing many variants, apply White's Reality Check or Hansen's SPA test before claiming significance. Each extra backtest you run raises the bar the winner must clear.
- Common leakage sources to audit explicitly: using the signal bar's close to fill; normalizing features with full-sample statistics (scale on training data only); target built from future bars without purging; lookahead in corporate actions or index membership; train/test split that straddles overlapping label windows.
- Cap degrees of freedom. Fewer parameters, economic priors, and regularization beat a 12-parameter grid search every time. Prefer the simpler model when Sharpe is within noise.
