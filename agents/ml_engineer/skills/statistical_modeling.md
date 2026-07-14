---
name: statistical-modeling
description: Governs hypothesis testing and effect estimation, requiring the analysis plan written before outcomes are inspected and results reported as effect sizes with confidence intervals rather than a bare p-value. Use when designing a statistical test, checking test assumptions, or reviewing a reported p-value or effect size.
---

# Statistical Modeling

This skill governs hypothesis testing, effect estimation, and the choice between classical statistics and machine learning. The analysis plan — hypotheses, test, significance level, and the minimum effect worth acting on — is written before outcomes are inspected, and results are reported as effect sizes with confidence intervals, with the p-value as one input rather than the verdict.

## Hypothesis testing discipline

Before running any test, declare in writing: the null hypothesis H0, the alternative Ha (one- or two-sided), the significance level (alpha = 0.05 unless justified otherwise), the test statistic, and the minimum effect of interest. Deciding these after seeing the data converts an honest test into a formality that confirms what you already found.

Verify the test's assumptions before trusting its output: normality (Q-Q plot; Shapiro-Wilk on small samples), equal variances (Levene), independence (know the sampling design; clustered or repeated measurements violate it silently). When assumptions fail, do not force the textbook test:

- Unequal variances: Welch's t-test (`scipy.stats.ttest_ind(equal_var=False)`) — a sane default over Student's t even when variances look similar.
- Non-normal, small n: Mann-Whitney U, or better, a permutation test (`scipy.stats.permutation_test`, `n_resamples=9999`), which tests the actual statistic you care about with no distributional assumption.
- Transformations (log for right-skewed positives) are acceptable when the transformed scale is the natural one; report on the scale you tested.

## Effect sizes and confidence intervals over p-values

A p-value conflates effect magnitude with sample size: with n large enough, a meaningless 0.1 percent difference is "significant". Every result therefore reports an effect size with a 95 percent confidence interval — Cohen's d or Cliff's delta for group differences, risk or odds ratios for rates, the raw metric delta for model comparisons — and the decision is made against the pre-declared minimum effect of interest, not against p < 0.05 alone.

Run a power analysis before collecting data (`statsmodels.stats.power.TTestIndPower().solve_power(effect_size=d, power=0.8, alpha=0.05)`); an underpowered study mostly produces noise, and its "significant" findings are inflated by winner's curse. Statistical significance without practical significance is a non-finding; say so plainly.

## Multiple comparisons

Testing many hypotheses at alpha = 0.05 guarantees false positives: 20 independent tests give a 64 percent chance of at least one. Correct explicitly with `statsmodels.stats.multitest.multipletests`: Holm for a handful of confirmatory tests (controls family-wise error with more power than plain Bonferroni), Benjamini-Hochberg FDR (`method="fdr_bh"`) for exploratory screens across many features or model variants. Comparing k models on the same test set is k comparisons — correct for it, and remember every peek at the holdout joins the family.

## Bootstrap

The bootstrap turns any metric into a confidence interval without normality assumptions. Use `scipy.stats.bootstrap` with `method="BCa"` and `n_resamples=9999` for metric CIs. For comparing two models evaluated on the same test set, use the paired bootstrap: resample test indices, compute the metric delta per resample, and read the CI of the delta — pairing removes the shared sample noise that unpaired intervals double-count. For temporal data, use a block bootstrap (resample contiguous blocks) so autocorrelation is preserved; strategy-level significance for trading results (deflated Sharpe, reality checks across many backtests) is `quant_trader`'s gate.

## When classical statistics beat ML

Reach for statsmodels before a gradient-boosted model when:

- n is small (below roughly 1,000 rows), where flexible models mostly fit noise;
- the question is inference — "does X affect Y, by how much, with what uncertainty" — rather than prediction; a GLM gives coefficients, CIs, and testable assumptions;
- observations are clustered or repeated (patients, users over time): mixed-effects models (`statsmodels MixedLM`) handle the correlation structure that naive models and naive CV both ignore;
- the effect is plausibly linear-ish and interpretability is a requirement, not a nice-to-have.

Always fit the regularized linear model as a baseline regardless; when the boosted model beats it by less than the linear model's own CI width, ship the simple one.

## Common pitfalls

- Choosing the hypothesis, test, or alpha after inspecting the outcomes.
- Reporting p-values without effect sizes or confidence intervals.
- "Significant" used as a synonym for "large" or "important".
- Many uncorrected comparisons across features, segments, or model variants.
- Student's t on clearly unequal variances or heavy tails when Welch or a permutation test was available.
- Unpaired comparison of two models scored on the same test set.
- Ordinary bootstrap on autocorrelated series instead of a block bootstrap.
- Treating regression coefficients from observational data as causal effects.

## Definition of done

- [ ] H0, Ha, alpha, the test, and the minimum effect of interest declared in writing before outcomes were inspected.
- [ ] Test assumptions checked, with the robust alternative (Welch, Mann-Whitney, permutation) used where they fail.
- [ ] Every reported result carries an effect size and a 95 percent confidence interval, not a bare p-value.
- [ ] Power analysis done before data collection, or the post-hoc power limitation stated.
- [ ] Multiple comparisons corrected (Holm or Benjamini-Hochberg) and the family of tests enumerated.
- [ ] Bootstrap CIs computed with BCa and >= 9999 resamples; paired bootstrap for same-test-set model deltas; block bootstrap on temporal data.
- [ ] Classical-versus-ML choice justified; the linear baseline fit and reported either way.
- [ ] Trading-strategy significance testing handed off to quant_trader.
