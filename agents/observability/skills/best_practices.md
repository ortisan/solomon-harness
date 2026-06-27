# Observability Best Practices

Concrete standards for logging, metrics, tracing, OpenTelemetry instrumentation, dashboards, SLIs, and alerting that this agent must apply to every change.

## Operating principles

- Treat the three signals as one correlated system. A log, a metric, and a trace describing the same event must share `trace_id` and `service.name`. If you cannot pivot from a metric spike to the exact traces behind it, the instrumentation is incomplete.
- Instrument for questions you will ask at 3 a.m. during an incident, not for vanity counters. Every metric and span must answer "is a user hurting, and where".
- Default to OpenTelemetry SDK + OTLP exporter + OpenTelemetry Collector. The Collector is the single egress point; applications never talk to vendor backends directly. This keeps backends swappable and centralizes sampling, redaction, and batching.
- Bound cardinality on purpose. Cardinality is the number one cause of cost blowups and time-series database (TSDB) outages.

## Logging

- Structured JSON only, one event per line. No multi-line human prose in production logs except attached stack traces.
- Mandatory fields on every record: `timestamp` (RFC 3339 / ISO 8601, UTC), `level`, `message`, `service.name`, `service.version`, `deployment.environment`, plus `trace_id` and `span_id` when a span is active. Use OTel log correlation so these are injected automatically rather than passed by hand.
- Level semantics, applied consistently: ERROR = actionable, something failed and someone must look; WARN = degraded but self-recovering; INFO = state transitions and business events (order placed, job completed); DEBUG = developer detail, disabled in production by default.
- Never log secrets or PII: tokens, passwords, API keys, full PANs, auth headers, raw request bodies with personal data. Enforce a redaction processor in the Collector as a backstop, but redact at the source first. Maintain an explicit deny-list of field names.
- Keep log I/O off the hot path. Use a non-blocking/async appender or write to stdout and let the Collector ship it. A synchronous logger call inside a request handler that blocks on disk or network is a latency bug.
- Sample high-volume INFO/DEBUG if needed, but never sample ERROR. Errors are rare and always wanted.
- Do not put unbounded values (user IDs, request IDs, full URLs) into indexed log fields; keep them in the message payload or as span attributes instead.
- Retention tiers: hot 7-30 days searchable, warm 30-90 days, cold/archive beyond. Set this explicitly; do not let everything sit in the expensive hot tier.

## Metrics

- Pick the right method per surface: RED (Rate, Errors, Duration) for request-driven services; USE (Utilization, Saturation, Errors) for resources (CPU, memory, disk, queues, connection pools); the four golden signals (latency, traffic, errors, saturation) as the cross-check on every service overview.
- Use the correct instrument type. Counter for monotonic totals (requests, errors, retries). Gauge for point-in-time state (pool size, queue depth, memory percent). Histogram for distributions (latency, payload size, query time). Prefer OTel exponential histograms for latency so percentiles stay accurate without hand-tuned buckets.
- Naming and units follow OTel semantic conventions. Record latency in seconds and sizes in bytes (base units), e.g. `http.server.request.duration`. Do not bake units into label values.
- Cardinality budget is hard. Never use `user_id`, `request_id`, `session_id`, raw URL path, or unbounded enums as metric labels. Templatize paths (`/users/{id}`). Keep per-metric label combinations in the low thousands of series, not millions. Define the series budget before adding a label.
- Percentiles, done correctly: aggregate histograms server-side with `histogram_quantile`; never average a percentile across instances and never alert on the mean. Track p50, p90, p95, p99, and p99.9 for latency.
- Emit exemplars on histograms so a latency bucket links directly to a representative trace. This is the metric-to-trace pivot.
- Know your collection model: Prometheus pull/scrape vs OTLP push. Use `rate()`/`increase()` over a window at least 4x the scrape interval so missed scrapes do not punch holes in the series; `rate()` already corrects for counter resets on its own.

## Distributed tracing

- Propagate context with W3C Trace Context (`traceparent`, `tracestate`) on every outbound HTTP call and IPC hop. Use baggage for cross-cutting business context, but keep baggage small (it travels on every hop).
- Span naming is low cardinality (`GET /users/{id}`, `db.query.select_user`, `http.out.fetch_rates`). Put the high-cardinality detail in span attributes, never in the span name.
- Create a root or child span at every entry point (HTTP handler, queue consumer, cron job) and child spans for significant nested work: database queries, outbound calls, file system access, heavy computation. Follow `db.*`, `http.*`, `messaging.*` semantic conventions for attributes.
- On exception: call `record_exception`, set span status to ERROR, attach the stack trace, then handle or re-raise. Do not leak secrets into span attributes or events.
- Link asynchronous and fan-out work with span links so a producer span connects to its consumer spans across a queue boundary.
- Sampling strategy: head sampling at a fixed ratio for baseline volume, plus tail-based sampling in the Collector to keep 100% of error and slow traces. Tail sampling is where you guarantee you never throw away the trace you actually need.

## OpenTelemetry instrumentation

- Prefer auto-instrumentation for frameworks and clients; add manual spans only for business logic the libraries cannot see. Never double-instrument the same call.
- Set resource attributes once, correctly: `service.name` (required), `service.version`, `service.namespace`, `deployment.environment`, and host/`k8s.*` from resource detectors. These are the join keys across all three signals.
- Collector pipeline order matters: `memory_limiter` first (protects against OOM), then resource/attributes processors for enrichment and PII redaction, then `batch` last before the exporters (efficiency). Configure receivers, processors, and exporters explicitly; do not run an unbounded queue.
- Version the Collector config in the repo and treat it as code: reviewed, tested, rolled out like any deployment.

## Monitoring dashboards

- One overview dashboard per service, top to bottom by importance: golden signals / RED at the top, dependencies and saturation below, infra USE at the bottom. The on-call should diagnose from the first screen without scrolling.
- Show SLO state and error-budget remaining on the overview, not a separate hidden board. A dashboard without SLO context cannot tell you whether a spike matters.
- Use template variables (service, region, environment) instead of cloning dashboards. Dashboard sprawl is a maintenance failure mode.
- Annotate deploys, config changes, and feature-flag flips on the time axis so correlation with regressions is immediate.
- Render latency from histograms with `histogram_quantile`, render error rate as `errors/total`, and label panels with the unit and the percentile. No raw averages on a latency panel.

## SLIs and SLOs

- SLI = good events / valid events, expressed as a ratio. Define the SLI type explicitly: availability, latency, freshness, correctness, or throughput. Write the exact numerator and denominator (for example, latency SLI = requests served under 300 ms / all valid requests).
- Set SLO targets with their error budget stated. Monthly downtime budgets (calendar month, ~30.44 days): 99.9% ≈ 43m 49s; 99.95% ≈ 21m 54s; 99.99% ≈ 4m 23s. Pick the tier the product actually needs; over-tight SLOs waste budget and create false pages.
- Error budget = 1 - SLO. The budget governs release velocity: when it is exhausted, stop shipping risk and spend the budget on reliability work.
- Base SLIs on what the user experiences (server-side request success and latency, or client-side real-user monitoring), not on internal proxies like CPU.

## Alerting

- Alert on symptoms (SLO burn), not causes. A CPU-at-80% alert that does not map to user pain is noise; a "latency SLO burning fast" alert is signal.
- Use multi-window, multi-burn-rate alerting (Google SRE model). For a 99.9% monthly SLO:
  - Page (fast burn): 14.4x burn rate over a 1h window confirmed by a 5m window (consumes ~2% of the monthly budget in 1h).
  - Page (medium burn): 6x burn rate over 6h confirmed by 30m (~5% of budget).
  - Ticket (slow burn): 1x-3x burn rate over 1d-3d (~10% of budget), no page.
  The short confirmation window kills flapping; the long window catches steady erosion.
- Every alert carries: a severity, an owner, a runbook link, and a clear "what the user is experiencing" statement. An alert with no runbook is an incomplete deliverable.
- Page only for user-facing, time-critical, SLO-threatening conditions. Everything else is a ticket. Track alert precision (fraction of pages that were actionable) and prune anything below ~90%.
- Configure deduplication, grouping, and inhibition so one root cause produces one page, not fifty.

## Common pitfalls to reject in review

- Averaging latency or alerting on the mean instead of percentiles.
- High-cardinality labels (`user_id`, `request_id`, raw paths) that detonate the TSDB.
- Synchronous logging or span export on the request hot path.
- Lost context across async/queue boundaries (no span links, no propagated `traceparent`).
- Cause-based alerts that generate fatigue while real SLO burns go unnoticed.
- Sampling that discards error or slow traces.
- Three disconnected signals with no shared `trace_id`/`service.name`, so no pivoting is possible.
- Dashboards with no SLO/error-budget context.

## Cross-cutting mandatory competencies

These project rules apply to the observability code and configs this agent ships:

- TDD is mandatory. Write the failing test first, then the instrumentation. Use OTel in-memory exporters (`InMemorySpanExporter`, in-memory metric reader) to assert that spans, attributes, status codes, and metric points are emitted as specified. Test Collector configs against sample payloads. Follow SOLID and keep exporters, processors, and instrumentation behind clear contracts.
- QA: mock all external services and telemetry backends (Prometheus, Tempo/Jaeger, Loki, vendor APIs) in tests so suites are hermetic and deterministic. No test reaches a live collector or backend.
- ML/analytics guards: when computing derived telemetry (rates, ratios, burn rates, anomaly scores), validate array/tensor shapes before the operation, guard every division for divide-by-zero (zero valid events), and guard against float overflow and NaN propagation. If anomaly detection uses a model, prevent overfitting with cross-validation and out-of-sample tests, and ensure zero data leakage between training and evaluation windows.
- Quant systems: when instrumenting a trading service, the model hypothesis being observed must state target Sharpe ratio (for example >= 1.5), maximum drawdown limit (for example <= 15%), profit factor (for example >= 1.3), latency and slippage constraints (for example p99 order round-trip < 50 ms, assumed slippage in basis points), the dataset and features used, and the network/model architecture. Instrument and alert against these exact budgets, especially order-to-fill latency and realized vs assumed slippage.
- Security (STRIDE) for the telemetry pipeline: Spoofing (authenticate Collector receivers and scrape endpoints, mutual TLS); Tampering (sign or restrict write access to metrics and logs); Repudiation (preserve immutable audit logs with actor and trace context); Information disclosure (redact PII and secrets in logs, spans, and baggage); Denial of service (cap cardinality and set `memory_limiter` and queue bounds so a cardinality bomb cannot take down the backend); Elevation of privilege (least-privilege credentials for exporters and the Collector, no shared god-tokens).

## Definition of done

- [ ] Logs are structured JSON with `trace_id`, `span_id`, `service.name`, `service.version`, and `deployment.environment`; no secrets or PII; ERROR is never sampled.
- [ ] Metrics follow RED/USE/golden-signal coverage, use OTel semantic names and base units, and stay within a stated cardinality budget; latency is a histogram with exemplars.
- [ ] Every entry point and significant nested operation has a span; W3C context propagates across all outbound calls; exceptions call `record_exception` and set ERROR status.
- [ ] Tail sampling keeps 100% of error and slow traces; the Collector config (with `memory_limiter`, `batch`, redaction) is versioned and tested.
- [ ] At least one service overview dashboard exists with golden signals, SLO state, error budget, and deploy annotations.
- [ ] SLIs are defined as good/valid ratios with explicit targets and error budgets; alerts are multi-window multi-burn-rate, symptom-based, each with severity, owner, and runbook.
- [ ] Tests written first (TDD), all external backends mocked, derived-metric math guarded for divide-by-zero/overflow/shape, and the telemetry pipeline reviewed against STRIDE.
