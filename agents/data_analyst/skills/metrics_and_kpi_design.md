---
name: metrics-and-kpi-design
description: Governs designing and defending KPIs through metric trees, ratio-metric denominator traps, Simpson's paradox decomposition, and a versioned metric definitions registry. Use when proposing a new KPI, defining or changing a metric formula, or investigating a ratio metric that moved unexpectedly.
---

# Metrics and KPI Design

Designing metrics that survive scrutiny: a metric tree that connects every reported number to the outcome it drives, ratio metrics with explicit denominators and weighting, segment-level checks that catch Simpson's paradox before a stakeholder does, and one versioned definitions registry so two dashboards can never disagree about what "active user" means. The stance: a metric is a contract — name, formula, grain, filters, owner — and changing any part of it is a versioned event, not a quiet edit.

## Metric trees

Structure metrics as a tree, not a list. One north-star outcome metric at the root (e.g. weekly completed orders), decomposed into driver metrics via arithmetic identities, down to input metrics teams can actually move:

```
weekly_completed_orders
= visitors x signup_rate x activation_rate x orders_per_active
```

Rules: every decomposition is an identity you can verify numerically each week (the product of the children reconciles to the parent within rounding); every leaf has an owning team; anything on a dashboard that cannot be placed on the tree is a candidate for deletion. The tree is also the diagnosis path — when the root moves, walk down level by level to find which factor moved, instead of guessing from twenty unrelated tiles.

Pair every growth metric with a guardrail counter-metric that catches the cheap way to game it: orders with refund rate, activation with 30-day retention, tickets closed with reopen rate. A target without a guardrail is an instruction to cut corners.

## Ratio-metric traps

Most KPI incidents are denominator incidents.

- **Average of ratios vs ratio of averages.** Per-user conversion averaged across users weights a 1-session user the same as a 400-session user; total conversions / total sessions weights by traffic. They answer different questions and can move in opposite directions. State which one the metric is, in the definition.
- **Moving denominators.** "Revenue per active user" can rise because revenue rose or because a login bug silently shrank active users. Always chart numerator and denominator next to the ratio; a ratio shown alone is unauditable.
- **Mix shift.** A blended metric can improve while every segment worsens, purely because the mix moved toward a stronger segment. Any blended ratio on an executive dashboard needs a standing per-segment breakdown.
- Undefined-denominator rows (0/0) must have a policy — excluded, or counted as zero — chosen once and written into the definition, because the two choices produce different trends.

## Simpson's paradox

The aggregate trend and every within-segment trend can point in opposite directions whenever segment sizes are unequal and the mix changes. Classic shape: conversion falls 6% overall while rising in both mobile and desktop, because traffic shifted toward mobile, whose baseline is lower. Operational rule: before reporting a change in any ratio metric, decompose it into **within-segment change** and **mix change** across the 2-3 segmentations that matter (platform, region, customer tier). Report which component drove the move — "conversion fell because the traffic mix shifted to mobile" and "mobile conversion itself fell" demand different actions. If the decomposition needs formal treatment (weighting, standardization, causal claims), hand it to `ml_engineer`.

## Definitions registry

One source of truth for every metric definition, versioned in git:

- Preferred: a semantic layer where BI tools consume the same compiled definition — dbt MetricFlow metrics, or a `metrics/` directory of YAML plus the canonical SQL. Second best: a registry document with the exact SQL inlined. Not acceptable: definitions living as SQL snippets inside individual BI dashboards, where they fork silently.
- Each entry: name, plain-language definition, formula/SQL, grain, inclusion filters (test accounts? internal users? refunds?), null/zero-denominator policy, owner, and a changelog.
- Changes are pull requests. A definition change that alters history (e.g. tightening "active") ships with a restated back-series or an annotated discontinuity marker on every chart that shows it — never a silent step in the trend.
- New metric names must be checked against the registry first; the second, slightly different "activation_rate" is how organizations end up arguing about arithmetic in a quarterly review.

## Avoiding vanity metrics

A metric earns a dashboard slot only if someone can name the decision that changes when it moves. Standard rejections: cumulative anything (monotonically increasing curves cannot show deterioration — plot the increment per period instead); registered users instead of active users; page views instead of task completions; averages over heavy-tailed quantities without percentiles. For each proposed KPI ask: who acts on it, at what threshold, doing what? No answer, no tile.

## Common pitfalls

- A ratio reported without its numerator and denominator series, making mix effects and denominator bugs invisible.
- Averaging per-entity ratios when the business question is traffic-weighted (or the reverse), and not saying which was done.
- Reporting a blended improvement that is pure mix shift — Simpson's paradox surfaced by a stakeholder instead of the analyst.
- Two dashboards computing the same metric name from different SQL; both owners certain theirs is canonical.
- Silent definition changes producing a step in the trend that gets investigated as a real event.
- Growth targets with no guardrail counter-metric, rewarding quality erosion.
- Cumulative charts used to demonstrate "growth" that stalled two quarters ago.
- 0/0 rows handled differently by two tools (SQL NULL vs BI-tool zero), making the same metric differ by tool.

## Definition of done

- [ ] The metric sits on the metric tree; its parent identity reconciles numerically for the latest period.
- [ ] The registry entry exists: definition, formula/SQL, grain, filters, null/zero-denominator policy, owner, changelog.
- [ ] Ratio metrics ship with numerator and denominator series and a per-segment breakdown for the standard segmentations.
- [ ] Reported changes in ratio metrics are decomposed into within-segment vs mix components before publication.
- [ ] Every growth KPI has a named guardrail metric displayed with it.
- [ ] Definition changes went through review and include a restated back-series or an annotated discontinuity.
- [ ] The decision and decision-maker for the metric are written in the registry entry; vanity candidates were rejected.
- [ ] Formal weighting/standardization or causal analysis is handed to `ml_engineer`, with the registry entry linked.
