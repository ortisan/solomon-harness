# Quant Trader Common Pitfalls

The backtest and risk failures that let a paper edge die on contact with live markets: leakage, ignored costs, and uncapped sizing. The closing checklist is the gate proving a result carries none of them.

## Common pitfalls


- Reporting gross instead of net performance.
- Filling on the signal bar's close (lookahead).
- Survivorship bias from a current-membership universe.
- Plain k-fold on overlapping labels (leakage through the test fold).
- Scaling or selecting features on the full sample.
- Optimizing on the held-out set after a "first look."
- Ignoring capacity: an edge that vanishes above a small notional.
- Zero or flat-fee cost assumptions on a high-turnover strategy.
- One-regime PnL presented as all-weather.
- Full Kelly or uncapped gearing.

## Definition of done

- [ ] Reported performance is net of costs; the gross curve appears only as a diagnostic.
- [ ] Fills occur at bar t+1 or later; no signal fills on its own bar's close.
- [ ] The universe is survivorship-free, reconstructed from historical membership with delisted names retained.
- [ ] Splits are purged and embargoed (walk-forward or CPCV); plain k-fold never touches overlapping labels.
- [ ] Scalers and feature selection are fit inside each training fold only, never on the full sample.
- [ ] The held-out set was evaluated exactly once, with no re-optimization after a first look.
- [ ] Capacity is estimated from the impact model, and the cost model reflects the strategy's actual turnover rather than zero or flat fees.
- [ ] PnL is reported per regime, and sizing uses vol targeting or capped fractional Kelly with a hard gearing cap.
