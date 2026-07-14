---
name: production-readiness-review
description: Governs the Production Readiness Review go/no-go gate before a service serves live traffic, covering SLI/SLO/error-budget checks, actionable alerting, capacity headroom, tested rollback, on-call ownership, and dependency review. Use when launching a service or deciding a GO/GO-WITH-CONDITIONS/NO-GO verdict.
---

# Production Readiness Review

The Production Readiness Review (PRR) is the go/no-go gate a service must clear before it serves live traffic, and again before a major change to its risk profile (new region, new dependency, 10x traffic). It is a structured audit against a fixed checklist: defined SLIs/SLOs with an error budget, runbooks, actionable alerts and dashboards, capacity and load headroom, a tested rollback, named on-call ownership, and a reviewed dependency graph. The output is a single recorded decision with `save_decision` (GO, GO-WITH-CONDITIONS, or NO-GO) and a `log_handoff` to whoever owns the launch. Treat a PRR as falsifiable: every item is either demonstrated with evidence (a link, a graph, a passing test) or it fails.

## When to run, and the model

Run a PRR before first production traffic, before a service moves from internal to external users, and before any change that invalidates a prior review's assumptions. The model is Google's PRR (SRE Book, ch. 32): a reviewer who does not own the service walks the checklist with the owning team, files gaps as issues, and blocks launch until the launch-blocking gaps close. Self-review is allowed only for low-risk internal services; anything user-facing gets a second pair of eyes. File every gap with `log_issue` tagged to the launch milestone (`create_milestone`) so closure is tracked, not remembered.

Three verdicts, each recorded with `save_decision`:

- GO: all launch-blocking items pass.
- GO-WITH-CONDITIONS: non-blocking gaps remain, each with an owner and a due date logged via `log_issue`; the decision records the conditions and the date they must close.
- NO-GO: a launch-blocking item fails. Re-review after the fix; do not amend a NO-GO in place.

## SLIs, SLOs, and error budget

Every critical user journey must have an SLI (a ratio of good events to valid events), an SLO with an explicit rolling window, and a written error-budget policy. The full method is in `reliability_targets_sli_slo_sla_error_budgets` and `definition_of_done`; the PRR confirms they exist, are measured from real telemetry, and have teeth. Check each:

- The SLI is a query against live metrics, not a description. `good / valid`, computed from the same signal the alert uses.
- The SLO names an explicit rolling window; 28-day rolling is the default. "99.9%" with no period is meaningless and fails.
- The error-budget policy states what happens at exhaustion: freeze feature launches and redirect to reliability work until the budget recovers.
- The number is operationally achievable. 99.9% over 28 days is ~40 min of allowed downtime; 99.99% is ~4 min and usually demands automated failover the team has not built. A target the team cannot meet is a NO-GO, not a stretch goal.

## Alerts and dashboards

Alerts must be actionable and tied to user pain. Page on SLO burn rate, not on causes. Use multi-window, multi-burn-rate alerting (SRE Workbook): a fast page when the burn rate would exhaust the 28-day budget in hours (e.g. 14.4x over 1h and 5m windows for a ~2% budget spend), a slower ticket-level alert for sustained low burn (e.g. 1x over 24h). Every paging alert answers: what is the user impact, and what is the first runbook step. An alert with no runbook link fails the review.

Dashboards: one overview per service covering the four golden signals (latency, traffic, errors, saturation) for request-driven services, USE (utilization, saturation, errors) for resources, and RED (rate, errors, duration) per endpoint. Stack: Prometheus/OpenTelemetry metrics, Grafana or equivalent. The `observability` agent owns instrumentation depth; the PRR confirms the SLI is graphed, the alert fires from the same signal, and a responder can find the saturation and dependency-health panels in under a minute. Reject cause-based pages (CPU > 80%, single-node disk) that wake someone without indicating user impact, and reject alerts with no defined silence/inhibition for known-noisy conditions.

## Capacity and load headroom

The breaking-point hunt and the test method live in `load_and_resilience_testing` and `resilience_and_load_shedding`. The PRR confirms the capacity story is real:

- A documented expected peak (requests/sec, concurrency) with the source of the estimate.
- A recent load test demonstrating the service serves that peak within SLO, naming the bottleneck resource (CPU, connections, downstream).
- Headroom for at least N+1: survive losing one zone or instance and still serve peak. Run utilization below the saturation knee, not at it.
- Autoscaling limits set above projected peak plus growth to the next review, not at peak. A ceiling equal to peak is no ceiling.
- No load test against production-like scale is a launch-blocking gap for user-facing services.

## Rollback

There must be a single, tested, automated way back to the last-known-good version that does not depend on the change being rolled back. Confirm against `infrastructure_and_deployment_pipelines`:

- Immutable, versioned artifacts and a progressive rollout (canary or blue-green) with automated SLO-based abort.
- A rollback actually executed in staging, with a measured duration the team can quote.
- Database migrations are backward-compatible (expand/contract), so a code rollback never requires a schema rollback.
- A "redeploy the old branch" plan with no tested path and no time bound is a NO-GO.

## On-call ownership

Reliability is a team property, not a person. Confirm:

- A named team holds the pager, with a staffed rotation, not a single hero. A one-person rotation is one illness away from an unstaffed pager and is a launch-blocking gap.
- The escalation path and the service's tier/SLA are documented.
- Runbooks are current and reachable from the alert itself, per `incident_response_and_runbooks`.

## Dependency review

Enumerate every hard dependency (datastores, auth, downstream APIs, DNS, secrets manager, message bus). For each, record:

- Its own SLO and tier.
- The failure mode when it is down or slow.
- The mitigation: timeout, retry budget, circuit breaker, cached or degraded response, graceful shedding.

Then check the arithmetic: your SLO can be no higher than the product of your hard dependencies' SLOs unless you decouple from them. A service promising 99.95% on top of a 99.9% datastore with no fallback is a NO-GO. Cross-check fallbacks against `high_availability` and `resilience_and_load_shedding`, and the loss-of-region or loss-of-database story against `disaster_recovery`. Any dependency with no defined timeout or no written failure mode is a gap.

## Recording the decision

Persist the verdict and its evidence with `save_decision`: the service, the verdict, the launch-blocking and non-blocking gaps with their `log_issue` ids, the reviewer, and the date a GO-WITH-CONDITIONS must reconverge. Hand the launch off with `log_handoff` to the owning on-call team, and `save_session` so the next PRR (next region, next 10x) starts from this baseline instead of re-deriving it. A PRR that ran but was never recorded did not happen; the decision must be retrievable with `get_decision` at the next incident review.

## Common pitfalls

- SLOs with no window or no backing SLI query: aspirational numbers no one measures. Reject; require a wired SLI and a 28-day window.
- Alerts that page on causes (high CPU, one disk filling) instead of user-facing symptom/burn rate: noisy, non-actionable, and they train responders to ignore the pager.
- A paging alert with no runbook link: the responder improvises at 3 a.m. Every page links its first step.
- Load test run against a toy environment, or autoscaling ceiling set at projected peak with zero headroom: the first real peak is the test.
- Rollback that depends on the thing being rolled back, or that has never been executed and has no measured duration: it is a hope, not a plan.
- Schema migration that is not backward-compatible, so code rollback is blocked by a forward-only DB change.
- Single-person on-call presented as a rotation: one illness away from an unstaffed pager.
- Dependency list that omits DNS, secrets, or auth, or lists dependencies with no timeout/failure mode: the outage will come from the one you did not write down.
- Promising an SLO above the composed availability of hard dependencies with no fallback path: arithmetically unachievable.
- Verdict reached in a meeting but never written to `save_decision`: no audit trail, and the conditions of a GO-WITH-CONDITIONS quietly lapse.

## Definition of done

- [ ] Every critical user journey has an SLI wired to a real query, an SLO with an explicit rolling window, and a written error-budget policy with an enforcement action.
- [ ] Paging alerts fire on multi-window multi-burn-rate SLO consumption, each links a runbook first step, and cause-based noise is inhibited or demoted to tickets.
- [ ] An overview dashboard exists with the four golden signals / RED / USE, and a responder can reach saturation and dependency-health panels in under a minute.
- [ ] A recent load test demonstrates the documented peak within SLO, names the bottleneck, and autoscaling limits sit above projected peak with N+1 headroom.
- [ ] Rollback is automated, independent of the change, tested in staging with a measured duration, and migrations are backward-compatible (expand/contract).
- [ ] A staffed on-call rotation, escalation path, service tier/SLA, and current reachable runbooks are documented and owned by a named team.
- [ ] Every hard dependency has its SLO, failure mode, and mitigation (timeout, retry budget, circuit breaker, degraded mode) recorded, and the composed availability supports the promised SLO.
- [ ] Every gap is filed with `log_issue` against the launch milestone; launch-blocking gaps are closed before GO.
- [ ] The verdict (GO / GO-WITH-CONDITIONS / NO-GO), its evidence, gap ids, reviewer, and reconvergence date are persisted with `save_decision`, handed off with `log_handoff`, and the baseline saved with `save_session`.
