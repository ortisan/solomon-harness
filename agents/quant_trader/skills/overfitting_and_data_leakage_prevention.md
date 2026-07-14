---
name: overfitting-and-data-leakage-prevention
description: Defines the statistical controls against backtest overfitting and leakage: deflated Sharpe, probability of backtest overfitting, multiple-testing haircuts, and the holdout contract of touching out-of-sample data exactly once. Use when validating a backtest's significance or auditing a pipeline for leakage.
---

# Overfitting and Data-Leakage Prevention

Backtest overfitting and information leakage are the two ways a strategy dies in production, and this skill defines the statistical controls (deflated Sharpe, PBO, multiple-testing haircuts) and the leakage audits every result must pass before it is believed. With enough trials a Sharpe of 2 arises from pure noise, so a raw backtested Sharpe carries no evidential weight until it is deflated by the search that produced it.

## The holdout contract

Hold out a true out-of-sample period and touch it exactly once, at the end, after every design decision is frozen. If you peek and re-tune, it is training data: log it as such and either carve a new holdout from unused history or accept that only live incubation remains. For everything before that single touch, use walk-forward or CPCV with purging and embargo (see the backtest pipeline skill) — never plain k-fold, because financial rows are serially dependent and overlapping label horizons leak across folds.

## Deflated Sharpe Ratio (DSR)

The Sharpe of the best of N trials is inflated by selection. Bailey and Lopez de Prado ("The Deflated Sharpe Ratio", Journal of Portfolio Management, 2014) correct for it: DSR is the probability that the true Sharpe exceeds zero after accounting for the number of trials, the variance of Sharpe across trials, the sample length, and the skewness and kurtosis of the returns.

- Compute the expected maximum Sharpe under the null from N effective trials, then test the candidate against that benchmark instead of zero. Cluster correlated variants first: 200 near-identical parameter sets are far fewer than 200 effective trials.
- Acceptance bar: DSR >= 0.95. Report N alongside it; an unrecorded trial count makes DSR unverifiable, which is one reason every run must be persisted via `save_backtest`.
- Non-normality matters: negative skew and excess kurtosis (option-selling profiles) widen the Sharpe estimator's variance and lower DSR at the same headline Sharpe.

## Probability of Backtest Overfitting (PBO)

PBO (Bailey, Borwein, Lopez de Prado, Zhu, "The Probability of Backtest Overfitting", Journal of Computational Finance, 2017) asks how often the in-sample winner underperforms the median configuration out-of-sample. Compute it with CSCV: split the trials' returns matrix into S submatrices (S = 16 typical), form all C(S, S/2) train/test combinations, rank the in-sample winner's out-of-sample performance in each combination, and take the fraction of combinations where the logit of its relative rank falls below zero.

- Target PBO < 0.10; treat PBO >= 0.50 as an outright rejection (selection is anti-correlated with skill).
- PBO and DSR are complements: DSR corrects a single reported number, PBO measures the health of the selection process itself.

## Multiple-testing haircuts

Every additional configuration tested raises the bar the winner must clear.

- Harvey and Liu ("Backtesting", Journal of Portfolio Management, 2015) give haircut Sharpe ratios from Bonferroni, Holm, and BHY corrections; at realistic trial counts a 50% haircut on the reported Sharpe is common.
- For claims that a variant beats a benchmark, run White's Reality Check (2000) or Hansen's SPA test (2005) over the full set of tried variants, not just the survivor.
- Cap degrees of freedom at the source: fewer parameters, economic priors, and regularization beat a 12-parameter grid search every time. Prefer the simpler model whenever the Sharpe difference is within noise.

## Lookahead and survivorship traps

Audit these explicitly on every pipeline; each has produced a fake edge in the wild:

- Filling on the signal bar's close, or computing a signal from a bar labeled at its open but built from the full bar.
- Full-sample normalization: scalers, PCA, and feature selection fit on all data, then "tested" on a subset they have already seen. Fit on the training fold only, inside the CV loop.
- Survivorship: a current-membership universe, or backfilled vendor histories for late-added tickers.
- Restatement leakage: fundamentals or macro series revised after first release, joined by report period instead of publication date.
- Label overlap: targets built from future bars (for example triple-barrier horizons) straddling the train/test boundary without purging and embargo.
- Corporate-action and index-membership foresight: adjusting or selecting with information dated after the decision timestamp.

## Feature-leakage audits

Run these mechanical checks before believing any ML result:

- Shuffled-target test: train on permuted labels; performance must collapse to chance. If it does not, the pipeline leaks.
- Lag-one test: shift all features one extra bar into the past; net performance should degrade only mildly. If performance improves, or was only ever positive without the extra lag, a same-bar leak exists.
- Timestamp assertion: for each feature, assert `max(feature_timestamp) <= decision_timestamp` in code, not by convention.
- Importance smell test: one feature dominating importance, or test metrics above train metrics, are leakage signatures, not genius.

## Common pitfalls

- Reporting the best trial's Sharpe with no trial count, which makes deflation impossible.
- Treating correlated parameter variants as independent trials (overstates N) or ignoring them entirely (understates N); cluster first.
- Plain k-fold on overlapping labels; leakage through the fold boundary produces beautiful, fake OOS curves.
- Optimizing on the holdout after a "first look" and still calling it out-of-sample.
- Scaling or selecting features on the full sample before splitting.
- Accepting PBO around 0.4 because DSR looked fine; the two controls catch different failure modes.

## Definition of done

- [ ] A single-touch holdout existed and its verdict is recorded, favorable or not.
- [ ] Trial count N logged (all variants, all reruns) via `save_backtest`; correlated trials clustered into effective trials.
- [ ] DSR computed with skewness and kurtosis inputs; DSR >= 0.95.
- [ ] PBO computed via CSCV (S >= 16); PBO < 0.10.
- [ ] Multiple-testing haircut (Harvey-Liu; Reality Check or SPA for benchmark claims) applied and reported.
- [ ] Lookahead audit passed: next-bar fills, point-in-time joins, survivorship-free universe, purged and embargoed splits.
- [ ] Feature audits green: shuffled-target collapses to chance, lag-one test does not improve results, feature timestamps asserted in code.
