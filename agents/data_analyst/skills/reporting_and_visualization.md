---
name: reporting-and-visualization
description: Governs chart-type selection, deceptive-visualization rules such as zero-baseline axes, no dual y-axes, and colorblind-safe palettes, dashboard design, and answer-first narrative structure for stakeholder reports. Use when building a chart, dashboard, or stakeholder report, or reviewing one for misleading encodings or a buried headline.
---

# Reporting and Visualization

Charts and reports that let a stakeholder make a decision in seconds without being misled: the right chart form for the question, hard rules against deceptive encodings, dashboards built around one question each, and a narrative that leads with the answer. The stance: a visualization is an argument, and the same integrity rules apply as to a number in a financial statement. Statistical inference behind a claim (significance, confidence intervals, causal language) is validated with the `ml_engineer` agent before it ships.

## Chart-type selection

Choose the form from the question, not from the tool's gallery:

- Comparison across categories: horizontal bar, sorted by value (alphabetical order is for lookup tables, not analysis). Limit to the top N plus an explicit "other" bar.
- Change over time: line for continuous series, bar for discrete periods with few buckets. One line per series, at most 4-5 series; beyond that, small multiples.
- Distribution: histogram or ECDF; box plots only for audiences that read them. Never report only a mean when the distribution is skewed — show a percentile table (p50/p90/p99) alongside.
- Relationship: scatter, with a trend line only if you are prepared to defend it; correlation claims that carry decisions go through `ml_engineer`.
- Part-of-whole: stacked bar or a plain table. Pie charts only for 2-3 slices summing to a meaningful 100%; humans compare angles badly.
- Ranked change between two points: slope or dumbbell chart, not two pies.

Prefer direct labels on series ends over legends; the eye should never ping-pong. Round display numbers to 2-3 significant figures ("4.7M", not "4,689,214") — precision beyond decision-relevance is noise.

## Deceptive-visualization rules

These are hard rules; a chart violating them does not ship.

- Bar chart value axes start at zero, always — bar length **is** the encoding. Line charts may zoom the y-range to show variation, but the axis must be labeled and the zoom must not manufacture drama out of a 0.3% wiggle.
- No dual y-axes. Two scales on one plot let the author fabricate any correlation by choosing ranges. Use two aligned panels.
- No 3D, no area/volume encodings of linear quantities (a 2x value drawn as a 2x-radius circle is a 4x area lie).
- Time axes are linearly spaced; skipping missing periods without a gap flattens seasonality and hides outages.
- One color = one meaning across the entire report; a category never changes color between charts.
- Log scales are allowed and labeled loudly ("log scale" in the axis title), never silent.
- Normalize when populations differ: absolute counts across regions of different size need a per-capita or per-account companion, or the chart just re-draws the population map.
- Colorblind-safe palettes (Okabe-Ito for categorical, viridis for sequential); never encode a distinction with color alone — pair with position, shape, or a direct label. Roughly 1 in 12 male viewers cannot separate red from green.

## Dashboard design

A dashboard answers one operating question for one audience; "everything for everyone" dashboards get zero decisions made off them.

- Five-second test: the primary KPI, its target or prior-period comparison, and its direction must be readable in five seconds, top-left.
- Every number carries context: vs target, vs same period last year, or a sparkline. A lone "Revenue: 4.7M" is decoration.
- Layout follows the reading order: summary KPIs on top, drivers below, drill-down detail last or behind a click. Keep it to roughly 9 tiles; past that, split the dashboard.
- State freshness on the face of the dashboard ("data through 2026-07-03 23:59 UTC"). A dashboard silently showing stale data is worse than a broken one — pair with checks from `data_quality_and_validation`.
- Default the time window and filters to the decision cadence (weekly review = trailing 13 weeks), not "all time".
- Refresh at the cadence decisions are made; real-time pipelines for a weekly meeting are cost without value.

## Narrative structure for stakeholders

Reports follow answer-first (BLUF / Minto pyramid), not the chronology of the analysis:

1. **Headline**: the finding and the recommended action in one or two sentences with the key number.
2. **Evidence**: 2-4 charts, each titled with an assertion ("Churn is concentrated in month-2 SMB cohorts"), not a topic ("Churn by cohort"). If the title is not a sentence someone could disagree with, rewrite it.
3. **Cause and confidence**: what explains the finding, what was ruled out, and what the data cannot tell you. State denominators, date ranges, and exclusions explicitly.
4. **Recommendation and next step**: who should do what by when, and what metric will confirm it worked.

Write two altitudes: a one-page executive summary and an appendix with methodology, queries, and robustness checks (see `analytics_workflow_and_reproducibility`). Never bury a caveat that changes the decision in the appendix.

## Common pitfalls

- Truncated bar-chart axes or dual y-axes manufacturing a trend that is not in the data.
- Chart titles that name a topic instead of asserting the finding, forcing the reader to do the analysis.
- Pie charts with 8 slices, unsorted bar charts, or 12-line spaghetti time series where small multiples were needed.
- Reporting a mean over a skewed distribution (revenue per account, latency) with no percentiles.
- Absolute counts compared across differently sized populations with no normalization.
- Red/green as the only encoding of good/bad.
- Dashboards with no freshness stamp, no comparisons, or 25 tiles nobody reads.
- The narrative built as a mystery novel — method first, answer on page 9.

## Definition of done

- [ ] Every chart form is justified by the question type; categorical bars are sorted; series count per line chart is 5 or fewer.
- [ ] No zero-baseline violations on bars, no dual y-axes, no 3D, no silent log scales; every zoomed line axis is labeled.
- [ ] Colors are colorblind-safe, consistent across the report, and never the sole encoding.
- [ ] Every chart title is an assertion; every number has a comparison; display precision is 2-3 significant figures.
- [ ] Denominators, date ranges, timezone, and exclusions are stated on or beside each chart.
- [ ] The dashboard passes the five-second test and shows its data-freshness timestamp.
- [ ] The report leads with the answer and recommendation; caveats that could change the decision are in the summary, not the appendix.
- [ ] Statistical claims (significance, causality) were checked with `ml_engineer`; the reproducibility appendix links the exact queries and data snapshot.
