---
name: definition-of-done
description: Defines the acceptance gate for observability deliverables covering structured logging, RED/USE metrics, tracing coverage, tail sampling, dashboards, SLIs and alerts, and TDD, plus the ways work gets falsely marked complete. Use when deciding whether instrumentation, alerting, or dashboard work is ready to ship.
---

# Observability Definition of Done

The acceptance gate for observability deliverables: every item below must hold before instrumentation, alerting, or dashboards ship. The pitfalls list the ways telemetry work gets falsely marked complete against this checklist.

## Common pitfalls

- Structured logging ticked while ERROR events are still sampled or PII survives in log bodies and span attributes — the item requires redaction and the ERROR sampling exemption, not just JSON formatting.
- RED/USE coverage claimed from whatever auto-instrumentation happened to emit, with no cardinality budget written down — coverage without the budget math leaves the TSDB one label away from an outage.
- Span coverage verified only on the happy path, with exceptions never passed to `record_exception` or given ERROR status — the failed requests are exactly the traces the checklist exists to keep.
- Tail sampling marked done because a Collector policy exists, but never fed a sample payload in a test — an unvalidated config can silently drop the error traces it was meant to retain.
- Burn-rate alerts shipped without severity, owner, or runbook — the multi-window rule fires correctly and still strands the responder, so the alerting item is not met.
- Dashboards delivered as panels with no SLO state or error budget, so the golden signals cannot be read against a target.
- The TDD item ticked with tests that assert only "no exception raised" instead of asserting the emitted spans and metric points against mocked backends — the telemetry contract itself goes unverified.

## Definition of done


- [ ] Logs are structured JSON with `trace_id`, `span_id`, `service.name`, `service.version`, and `deployment.environment`; no secrets or PII; ERROR is never sampled.
- [ ] Metrics follow RED/USE/golden-signal coverage, use OTel semantic names and base units, and stay within a stated cardinality budget; latency is a histogram with exemplars.
- [ ] Every entry point and significant nested operation has a span; W3C context propagates across all outbound calls; exceptions call `record_exception` and set ERROR status.
- [ ] Tail sampling keeps 100% of error and slow traces; the Collector config (with `memory_limiter`, `batch`, redaction) is versioned and tested.
- [ ] At least one service overview dashboard exists with golden signals, SLO state, error budget, and deploy annotations.
- [ ] SLIs are defined as good/valid ratios with explicit targets and error budgets; alerts are multi-window multi-burn-rate, symptom-based, each with severity, owner, and runbook.
- [ ] Tests written first (TDD), all external backends mocked, derived-metric math guarded for divide-by-zero/overflow/shape, and the telemetry pipeline reviewed against STRIDE.
