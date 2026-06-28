# DORA Metrics and Change Management

Instrument the four DORA metrics from real delivery and incident events, read throughput and stability together rather than as a tradeoff, and gate production change on the error budget so that an exhausted budget triggers an enforced, time-bounded deploy freeze. The metrics exist to drive a decision (ship faster, or stop and stabilize); a dashboard that no policy reacts to is decoration. This skill covers measurement and change governance; the SLO, error-budget, and burn-rate definitions it leans on live in `reliability_targets_sli_slo_sla_error_budgets`, and the pipeline that enforces the gates lives in `infrastructure_and_deployment_pipelines`.

## The four metrics

DORA (DevOps Research and Assessment) tracks two throughput metrics and two stability metrics. The research finding that anchors everything below: top performers are strong on both, so a throughput/stability tradeoff is a sign of large batch sizes or weak testing, not a law of nature.

- **Deployment frequency (DF)** — how often you deploy to production. Throughput.
- **Lead time for changes (LT)** — time from code committed to that code running in production. Throughput.
- **Change failure rate (CFR)** — share of deployments that cause a degraded service requiring remediation (rollback, hotfix, fix-forward, patch). Stability.
- **Time to restore service (TTR)** — time from a production failure starting to service being restored. Stability. The 2023 report sharpened this into "failed deployment recovery time" (recovery from a bad deploy specifically) and split out a fifth, separate **reliability/operational performance** metric backed by your SLOs.

Formulas to compute per rolling window (use 28 or 30 days, the same window as your SLOs):

- `DF = count(successful prod deployments) / window`
- `LT = median(deploy_time − commit_time)` over deployments (track p90 too; the tail is where review and queue time hides)
- `CFR = failed_deployments / total_deployments`
- `TTR = median(restored_time − impact_start_time)` over incidents

Use the median and a high percentile, never the mean. LT and TTR are right-skewed; the mean is dominated by a few outliers and hides the typical experience.

## Performance bands

Approximate elite/high/medium/low thresholds. DORA recalibrates the cluster boundaries in each annual State of DevOps report, so snapshot against the current report rather than hard-coding these forever; the shape matters more than the exact cutoff.

| Metric | Elite | High | Medium | Low |
| --- | --- | --- | --- | --- |
| Deployment frequency | On-demand / multiple per day | Daily to weekly | Weekly to monthly | < once per month |
| Lead time for changes | < 1 day | 1 day – 1 week | 1 week – 1 month | > 1 month |
| Change failure rate | 0–15% | 16–30% | 16–30% | > 30% |
| Time to restore service | < 1 hour | < 1 day | 1 day – 1 week | > 1 week |

Read the band as a team's own trend over time, not as a ranking stick between teams. The lever that moves all four at once is small batch size: smaller, more frequent changes deploy more often (DF), clear the pipeline faster (LT), fail less catastrophically (CFR), and are quicker to diagnose and revert (TTR).

## Instrumenting the metrics

Derive every metric from machine events you already emit, not from spreadsheets or self-report.

- **Deployment events.** Emit a structured event on each production deploy from the CD stage: `{service, env, commit_sha, started_at, finished_at, status}`. Count only successful prod deploys for DF; exclude staging, no-op, and re-run deploys or you inflate the number into a vanity metric.
- **Lead time.** Join the deploy event's `commit_sha` back to VCS to get the commit (or PR-merge) timestamp. Measure commit-to-prod, not just the CI duration, so review latency and deploy queue time are visible. PR-merge-to-prod is an acceptable proxy if first-commit timestamps are noisy, but state which you use.
- **Change failure.** Tag every incident and rollback with the deploy that caused it. CFR is failures divided by deploys, so it needs both the deploy denominator and a reliable failure link. Count fix-forwards and silent degradations, not just explicit rollbacks.
- **Time to restore.** Pull `impact_start_time` and `restored_time` from the incident manager (PagerDuty, Opsgenie, incident.io). Start the clock at impact, not at acknowledgment, or you will systematically understate TTR and reward slow detection.

Tooling in 2026: Google's open-source **Four Keys** (deploy/VCS/incident events into BigQuery), **CDEvents** (CDF standard event schema so DORA computes across heterogeneous CI/CD tools), and the maturing **OpenTelemetry CI/CD semantic conventions** (`cicd.*` spans) for vendor-neutral pipeline telemetry. Managed options include Datadog DORA Metrics, GitLab Value Stream Analytics, Sleuth, LinearB, and Faros. Whatever the source, the deploy marker and the incident record are the two primitives; everything else is a join.

## Error-budget-based change management

Change governance is the point of measuring stability. Gate promotion to production on error-budget health (see `infrastructure_and_deployment_pipelines` for the pipeline gate, and `reliability_targets_sli_slo_sla_error_budgets` for how the budget and burn rate are computed). Run a tiered policy, signed off by product, enforced in the pipeline rather than by honor system:

- **Budget healthy (e.g. > 50% remaining):** normal or elevated velocity. Ship freely, take experiments, this is what the budget is for.
- **Budget low (e.g. < 25% remaining, or a sustained fast burn):** heightened scrutiny. Smaller batches, mandatory canary analysis, a reliability reviewer on risky changes.
- **Budget exhausted (≤ 0):** **feature deploy freeze.** The pipeline blocks any non-exempt deploy to the affected service. The only changes that pass are reliability fixes, security patches, and rollbacks.

Freeze mechanics that make it real:

- **Enforce at the gate.** A pre-deploy check queries the current SLO/budget state and fails the pipeline for non-exempt changes. A Slack announcement is not a freeze; an unfreezable freeze is a gate.
- **Exemptions are explicit and logged.** P1 security and active-incident remediation may bypass, but each bypass needs a named approver and a record. If everything is "urgent," the freeze is meaningless.
- **Objective exit criterion.** The freeze lifts automatically when the budget recovers above a stated threshold over the rolling window. An indefinite freeze with no exit condition is a process smell and a morale sink.
- **Calendar freezes are separate.** Peak-traffic windows (sales events, holidays) justify their own scheduled freeze; codify it alongside the budget freeze so both are enforced the same way.

Persist the governance state through the project memory tools so the decision survives the on-call rotation: `save_decision` for the freeze policy and each enter/exit decision (with `get_decision` read by the gate to know current state), `log_issue` when the budget is exhausted so the freeze is tracked to closure (`get_open_issues` answers "are we frozen?"), `save_session` to snapshot budget and DORA values at the moment of the decision, and `log_handoff` so the next on-call inherits the freeze status and its exit criterion rather than rediscovering it. Use `get_latest_activity` at shift start to surface a freeze entered on the previous rotation.

## Common pitfalls

- Counting non-prod, re-run, or no-op deploys toward deployment frequency. Inflates a vanity number while real throughput is flat.
- Measuring lead time from PR-open or only across the CI stage, hiding review queue and deploy wait. Measure commit-to-prod.
- Computing CFR from rollbacks alone, ignoring fix-forwards and silent degradations, so the rate reads artificially clean.
- Starting the TTR clock at acknowledgment instead of impact start, which rewards slow detection and understates recovery time.
- Using the mean for lead time or time to restore. Both are right-skewed; report median plus a high percentile.
- Treating throughput and stability as a tradeoff and deliberately slowing deploys to "improve" stability. That grows batch size and degrades all four metrics.
- Benchmarking against last year's band cutoffs. DORA recalibrates them annually; track your own trend.
- Org-level aggregation that averages a failing service into a healthy fleet. Compute per service or per delivery stream.
- A deploy freeze enforced by announcement rather than a pipeline gate, or a freeze with no objective exit criterion.
- Exempting so many changes from the freeze that it stops constraining anything.
- Using DORA scores as a cross-team performance-management stick. Goodhart's law applies; the metrics get gamed the moment they are weaponized.

## Definition of done

- [ ] All four metrics are derived from machine events (deploy markers, VCS commits, incident records), not self-report, and computed over the same rolling window as the SLOs.
- [ ] Deployment frequency counts only successful production deploys; staging, no-op, and re-run deploys are excluded.
- [ ] Lead time is measured commit-to-prod (or merge-to-prod, stated explicitly) and reported as median plus p90.
- [ ] Change failure rate has a reliable deploy-to-failure link and counts fix-forwards and degradations, not only rollbacks.
- [ ] Time to restore starts at impact, not acknowledgment, and is reported as median plus a high percentile.
- [ ] Metrics are computed per service or delivery stream and presented as a trend, not a cross-team ranking.
- [ ] A signed-off, tiered error-budget policy exists: healthy → ship, low → heightened scrutiny, exhausted → feature freeze.
- [ ] The freeze is enforced by a pre-deploy pipeline gate that reads current budget state; exemptions require a named approver and are logged.
- [ ] The freeze has an objective, automatic exit criterion and a documented owner; calendar freezes are codified the same way.
- [ ] Freeze entry/exit, the exhausted-budget issue, and the on-call handoff are persisted via `save_decision`, `log_issue`, and `log_handoff`, and the gate reads current freeze state via `get_decision`/`get_open_issues`.
