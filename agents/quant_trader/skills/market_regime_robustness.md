## Market-regime robustness


- Tag the sample into regimes: trending vs mean-reverting, high vs low volatility (VIX terciles or realized-vol buckets), risk-on vs risk-off, rising vs falling rates. Report Sharpe, drawdown, and hit rate per regime.
- The test window must include at least one full stress event, scored out-of-sample: 2008 GFC, May 2010 flash crash, Aug 2015 selloff, Feb 2018 vol spike (volmageddon), March 2020 COVID crash, 2022 rate shock. A strategy untested through a crisis is untested.
- Reject strategies whose entire PnL comes from one regime unless that regime is the explicit thesis (and then size for its absence).
- Check parameter stability: small parameter perturbations should produce small performance changes. A sharp performance cliff means you fit the peak of a noisy surface.
