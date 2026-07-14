---
name: common-pitfalls
description: Lists the review-reject defects across metrics, tracing, sampling, alerting, and dashboards that break the three-signal correlation model, paired with the definition-of-done gate proving they were avoided. Use when reviewing observability code or configs, or auditing whether telemetry work is actually complete.
---

# Observability Common Pitfalls

The review reject list for telemetry work: the metric, tracing, sampling, alerting, and dashboard defects that break the three-signal model. Each bullet names a failure a reviewer must block, and the Definition of done below is the gate proving the instrumentation avoided every one of them.

## Common pitfalls


- Averaging latency or alerting on the mean instead of percentiles.
- High-cardinality labels (`user_id`, `request_id`, raw paths) that detonate the TSDB.
- Synchronous logging or span export on the request hot path.
- Lost context across async/queue boundaries (no span links, no propagated `traceparent`).
- Cause-based alerts that generate fatigue while real SLO burns go unnoticed.
- Sampling that discards error or slow traces.
- Three disconnected signals with no shared `trace_id`/`service.name`, so no pivoting is possible.
- Dashboards with no SLO/error-budget context.

## Definition of done

- [ ] Latency panels and alerts read server-side histogram percentiles (p50/p95/p99); nothing averages a percentile or alerts on the mean.
- [ ] Every metric label has enumerable values inside the cardinality budget; no `user_id`, `request_id`, or raw-path labels reach the TSDB.
- [ ] Span and log export is batched and asynchronous (`BatchSpanProcessor`, async appenders); nothing exports synchronously on the request hot path.
- [ ] W3C `traceparent` propagates across every async and queue boundary, with span links where a new trace starts.
- [ ] Pages fire on SLO burn-rate symptoms; cause signals live on dashboards or as inhibited context.
- [ ] Tail sampling retains 100 percent of error and slow traces regardless of the head-sampling ratio.
- [ ] All three signals share `trace_id` and `service.name`, and the log-to-trace-to-metric pivot has been exercised.
- [ ] Every dashboard shows SLO state and error budget alongside the golden signals.
