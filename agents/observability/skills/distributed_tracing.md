# Distributed Tracing

This skill governs how traces are designed, propagated, sampled, and correlated with logs so any request can be followed across every service, queue, and background job it touches. The stance: context propagation is non-negotiable on every hop, span names stay low-cardinality, and the sampling design must guarantee that the trace you need during an incident was actually kept.

## Context propagation

Use W3C Trace Context as the propagation standard. The `traceparent` header carries `version-traceid-parentid-flags`, for example `00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01`; `tracestate` carries vendor-specific data. OTel SDKs default to it. When interoperating with legacy Zipkin/B3 services, run a composite propagator that reads and writes both formats during the migration, then retire B3 — do not run split-brain propagation indefinitely.

Propagation must survive every boundary, not just HTTP: inject context into message headers on publish and extract on consume; for cron and batch work, start a new root and attach span links to the traces that enqueued the work. In this repo, an MCP tool call into `solomon_harness.mcp_server` is an entry point: it starts or continues a trace, and the SurrealDB write it triggers must appear as a child span, not a fresh disconnected trace.

Baggage (W3C Baggage) is for small cross-cutting business context such as `tenant.id` or an experiment flag. It travels as a header on every hop, so keep it to a handful of short keys and never put secrets or PII in it — every downstream service and access log can read it.

## Span design

- Names are low-cardinality templates: `GET /users/{id}`, `db.query.select_user`, `http.out.fetch_rates`. The concrete id, URL, or SQL text goes in attributes, never the name; a unique span name per request destroys grouping and aggregation.
- Set the span kind correctly (SERVER, CLIENT, PRODUCER, CONSUMER, INTERNAL). Backends derive service graphs and RED metrics from kinds; a CLIENT call recorded as INTERNAL disappears from the dependency map.
- Attributes follow the `http.*`, `db.*`, and `messaging.*` semantic conventions. Use span events for point-in-time facts (cache miss, retry attempt, lock acquired) instead of zero-duration child spans.
- Create a span at every entry point (HTTP handler, queue consumer, cron job) and for significant nested work: database queries, outbound calls, file I/O, heavy computation.
- On exception: `span.record_exception(exc)`, `span.set_status(StatusCode.ERROR)`, then handle or re-raise. A span that swallowed an exception while reporting OK status is a review reject. Do not leak secrets into attributes or events.
- Link asynchronous fan-out with span links so a producer span connects to its consumer spans across the queue boundary.

## Head versus tail sampling

Head sampling decides at the root, before anything is known about the outcome. It is cheap, stateless, and configured in the SDK (`parentbased_traceidratio`). Its blind spot is rare events: with 10 percent sampling, an error class that occurs 5 times a day has a 0.9^5, roughly 59 percent, chance of leaving no trace at all; at 1 percent it is 0.99^5, about 95 percent.

Tail sampling decides after the trace completes, in the Collector's `tail_sampling` processor. Standard policy set: keep 100 percent of traces with error status, keep 100 percent of traces slower than the latency SLO threshold, then a probabilistic 5 to 10 percent baseline. The costs are concrete. Buffering: with `decision_wait: 10s` at 2,000 spans/s and roughly 1 KB per span, the Collector holds about 20 MB; at 20,000 spans/s with a 30 s wait it is about 600 MB per instance — size `memory_limiter` accordingly. Topology: every span of a trace must reach the same Collector instance, which means a two-tier deployment with the `loadbalancing` exporter routing by trace ID in tier one and `tail_sampling` running in tier two.

The practical combination: head sampling in the SDK as coarse volume control (100 percent for low-traffic services, lower for high-traffic ones), tail sampling in the Collector to enforce "never discard an error or slow trace". Document the effective policy next to the Collector config so nobody assumes 100 percent retention that is not there.

## Trace-log correlation

Every log record written inside an active span must carry `trace_id` and `span_id`, injected automatically — in Python via `LoggingInstrumentor` from `opentelemetry-instrumentation-logging` — never copied by hand. Metrics link back to traces through exemplars on histograms. Verify the pivot end to end: from a latency spike on a dashboard, through an exemplar, to the trace, to the logs of the failing span. If that walk breaks at any step, correlation is incomplete regardless of what is being emitted.

## Common pitfalls

- Context lost at a queue, thread pool, or async boundary, producing orphan root spans that cannot be joined to the request.
- High-cardinality span names (raw paths, ids in the name) that defeat aggregation and blow up backend indexes.
- Head-only sampling at a low ratio, silently discarding the error traces incidents depend on.
- Tail sampling behind a trace-ID-unaware load balancer, so traces arrive split and policies misfire.
- Exceptions caught without `record_exception` and ERROR status; the trace looks healthy while the log shows a failure.
- Baggage used as a data bus: large values or PII broadcast in headers to every downstream service.

## Definition of done

- [ ] W3C `traceparent`/`tracestate` propagates across every outbound call, queue hop, and background job; legacy formats bridged by a composite propagator with a retirement date.
- [ ] Span names are low-cardinality templates; detail lives in semconv attributes; span kinds are correct.
- [ ] Every entry point and significant nested operation has a span; async fan-out uses span links.
- [ ] Exceptions call `record_exception` and set ERROR status; no secrets in attributes, events, or baggage.
- [ ] Sampling policy is written down: head ratio, tail policies keeping 100 percent of error and SLO-slow traces, and the buffering/memory numbers behind `decision_wait`.
- [ ] Tail sampling runs behind trace-ID-aware load balancing when there is more than one Collector instance.
- [ ] Logs inside spans carry injected `trace_id`/`span_id`; the metric-to-trace-to-log pivot is verified end to end.
