## Definition of done


- [ ] Logs are structured JSON with `trace_id`, `span_id`, `service.name`, `service.version`, and `deployment.environment`; no secrets or PII; ERROR is never sampled.
- [ ] Metrics follow RED/USE/golden-signal coverage, use OTel semantic names and base units, and stay within a stated cardinality budget; latency is a histogram with exemplars.
- [ ] Every entry point and significant nested operation has a span; W3C context propagates across all outbound calls; exceptions call `record_exception` and set ERROR status.
- [ ] Tail sampling keeps 100% of error and slow traces; the Collector config (with `memory_limiter`, `batch`, redaction) is versioned and tested.
- [ ] At least one service overview dashboard exists with golden signals, SLO state, error budget, and deploy annotations.
- [ ] SLIs are defined as good/valid ratios with explicit targets and error budgets; alerts are multi-window multi-burn-rate, symptom-based, each with severity, owner, and runbook.
- [ ] Tests written first (TDD), all external backends mocked, derived-metric math guarded for divide-by-zero/overflow/shape, and the telemetry pipeline reviewed against STRIDE.
