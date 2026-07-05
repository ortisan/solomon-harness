# Data-Driven Reporting

This skill governs the structure and honesty of analytical and model-evaluation reports. A report exists so a reader can weigh the evidence and reproduce it: every number carries its baseline, its uncertainty, and its provenance, and the report's conclusions survive the reader checking any one of them.

## Report structure

Fixed order, so reviewers know where to look:

1. Executive summary: the findings and the recommendation, in plain language, first. State the decision the evidence supports and its confidence; the reader who stops here should leave with the correct conclusion.
2. Setup: data (source, date range, version hash), split protocol, metrics with definitions, and the baselines.
3. Results: the main table.
4. Ablations and sensitivity.
5. Error analysis.
6. Limitations.
7. Reproduction pointer: the experiment-tracker run ids, config, and manifest (see `reproducibility`) that regenerate every table.

Every claim in the body is immediately backed by a referenced table, statistical figure, or visualization — no orphan claims, and no orphan charts either: each figure earns one sentence stating what it shows and why it matters.

## Baselines and uncertainty

A metric without a baseline is unreadable. The results table always includes:

- the naive baseline (majority class, mean, persistence) — this is the floor, and it calibrates the metric's scale for the reader;
- the strongest simple model (regularized logistic/linear or default-parameter gradient boosting) — this is what the complexity must justify itself against;
- the proposed model(s).

Every headline metric carries uncertainty: a 95 percent bootstrap confidence interval on the holdout (BCa, >= 9999 resamples), and mean plus standard deviation across CV folds and across 3 to 5 seeds where applicable. An improvement claim requires the paired-bootstrap CI of the delta to exclude zero (see `statistical_modeling`) — "0.84 vs 0.83" without an interval is a difference in typography, not in models. Report 2 to 3 significant digits; more implies precision the intervals do not support.

## Ablations

Every component you claim matters gets an ablation: remove it, retrain under the identical protocol, and report the delta with its interval. Feature groups, augmentations, architecture pieces, and loss terms all qualify. Credit only what the ablation supports; "the attention layer helps" with no ablation row is an opinion. Keep the ablation grid honest by running it under the same budget and seeds as the main result, not under a cheaper protocol that quietly disadvantages the variants.

## Error analysis

Aggregate metrics hide the failure modes that decide deployment. Slice the holdout metric by the segments the business runs on (region, tenure, product tier, time period) and report the worst slices next to the average; a model at 0.85 overall and 0.61 on new users is a finding, not a footnote. Include a short inspection of the highest-confidence errors — a table of a dozen concrete failures teaches the reader more about the model's behavior than another decimal of AUC.

## Limitations

Dedicate a section — not a sentence — to what would weaken the conclusions: data constraints and known biases, assumptions made and where they might fail, correlation-versus-causation boundaries on any observational claim, distribution-shift risk between the evaluation window and deployment, and the validity horizon (when the numbers should be re-measured). Cherry-picking is the failure mode this section exists to prevent: if a time window, segment, or metric was excluded, the exclusion and its reason appear here. For trading results, the cost and capacity caveats are written with `quant_trader`, who owns their validation.

## Common pitfalls

- Headline metric with no naive baseline, so the reader cannot tell 0.84 from luck.
- Metrics without confidence intervals, or improvement claims whose interval includes zero.
- The best seed or the best time window reported as "the result".
- Component claims with no ablation rows behind them.
- Only aggregate metrics, hiding a collapsed segment that decides real-world viability.
- Limitations reduced to a boilerplate sentence, with excluded data left unmentioned.
- A report that cannot be reproduced because run ids, configs, or data versions are missing.
- Charts without a stated takeaway, or takeaways without a chart or table behind them.

## Definition of done

- [ ] Executive summary opens the report with findings and recommendation in plain language.
- [ ] Setup section names data version, split protocol, metric definitions, and baselines.
- [ ] Results table includes naive baseline, strongest simple model, and the proposed model, each with 95 percent CIs and seed/fold variance.
- [ ] Improvement claims backed by paired-bootstrap deltas whose intervals exclude zero.
- [ ] Every claimed component supported by an ablation run under the identical protocol.
- [ ] Error analysis reports worst business-relevant slices and inspects concrete high-confidence failures.
- [ ] Limitations section covers biases, assumptions, causal boundaries, shift risk, exclusions, and the validity horizon.
- [ ] Reproduction pointer resolves to tracker run ids, configs, and the data version; a reviewer can regenerate every table.
