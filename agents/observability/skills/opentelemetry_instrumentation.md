---
name: opentelemetry-instrumentation
description: Covers OpenTelemetry SDK setup in Python, semantic-convention and resource-attribute usage, auto- versus manual instrumentation, OTLP export, Collector pipeline ordering, and sampler configuration as the project's mandatory telemetry layer. Use when wiring OTel into a service, configuring the Collector, or choosing between auto-instrumentation and a manual span.
---

# OpenTelemetry Instrumentation

OpenTelemetry (OTel) is this project's standard telemetry layer: every service emits traces, metrics, and logs through the OTel SDK to an OpenTelemetry Collector over OTLP, and never talks to a vendor backend directly. This skill covers SDK setup in Python, semantic conventions and resource attributes, auto- versus manual instrumentation, OTLP export, Collector pipelines, and sampling configuration.

## SDK setup (Python)

Pin `opentelemetry-api`, `opentelemetry-sdk`, and `opentelemetry-exporter-otlp` to one coherent 1.x version set (1.30 or later) and upgrade them together with the `opentelemetry-instrumentation-*` packages; version skew between API and SDK is the most common cause of silently no-op tracers. Configure the provider once, at process start, before any instrumented import:

```python
import os
from importlib.metadata import version
from opentelemetry import trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter

resource = Resource.create({
    "service.name": "solomon-harness",
    "service.version": version("solomon-harness"),
    "deployment.environment.name": os.environ.get("DEPLOY_ENV", "dev"),
})
provider = TracerProvider(resource=resource)
provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter()))
trace.set_tracer_provider(provider)
tracer = trace.get_tracer("solomon_harness.tools.database_client")
```

Use `BatchSpanProcessor` in production, never `SimpleSpanProcessor`: the simple processor exports synchronously on span end, which puts network I/O on the request hot path. In tests, swap in `InMemorySpanExporter` and assert on the finished spans; instrumentation is code and follows the same TDD cycle as everything else in this repo — write the failing span assertion first.

## Semantic conventions and resource attributes

Attribute names come from the OTel semantic conventions, not invention, and you must know a convention's stability status before building dashboards on it. HTTP conventions have been stable since semconv 1.23 (2023): `http.request.method`, `http.response.status_code`, `http.route`. Database conventions were declared stable in semconv 1.34 (2025): `db.system.name`, `db.operation.name`, and opt-in `db.query.text`. Messaging and GenAI conventions are still evolving, so pin the semconv version you emit against. During a convention migration, use `OTEL_SEMCONV_STABILITY_OPT_IN` to dual-emit old and new names rather than a big-bang rename that breaks every saved query.

Resource attributes are the join keys across all three signals. Set them once on the `Resource`, never per span: `service.name` is required (an unset value exports as `unknown_service`, a review reject), plus `service.version`, `service.namespace`, and `deployment.environment.name` (renamed from `deployment.environment` in semconv 1.27). Let resource detectors fill host, process, and `k8s.*` attributes instead of hardcoding them.

## Auto- versus manual instrumentation

Prefer auto-instrumentation for anything that has a library: `opentelemetry-bootstrap -a install` detects installed packages and installs the matching instrumentation distributions, and `opentelemetry-instrument python -m app` activates them with no code changes. This gets HTTP servers and clients, database drivers, and messaging clients right, with correct span kinds and semconv attributes. Add manual spans only for business logic the libraries cannot see. In this repo, a span around `DatabaseClient.save_decision` recording which backend served the write (`surrealdb` or the SQLite fallback) is manual instrumentation; the underlying HTTP call to SurrealDB is the auto-instrumented child. Never wrap an auto-instrumented call in a manual span that duplicates it — one operation, one span.

## OTLP export and sampling configuration

OTLP has two transports: gRPC on port 4317 and HTTP/protobuf on 4318. Configure export and sampling by environment, not code, so the same build runs everywhere:

```
OTEL_EXPORTER_OTLP_ENDPOINT=http://otel-collector:4317
OTEL_EXPORTER_OTLP_PROTOCOL=grpc
OTEL_TRACES_SAMPLER=parentbased_traceidratio
OTEL_TRACES_SAMPLER_ARG=0.10
```

`parentbased_traceidratio` keeps decisions consistent across a trace: the root service samples (10 percent here) and children honor the parent's decision, so traces are never half-kept. Head sampling in the SDK is only the coarse volume control; guaranteeing that error and slow traces survive belongs to tail sampling in the Collector (see the distributed_tracing skill).

## Collector pipelines

The Collector is the single egress point, and the place where sampling, redaction, enrichment, and batching are centralized. A pipeline is receivers, then processors, then exporters, and processor order matters: `memory_limiter` first so a traffic spike degrades by refusing data instead of OOM-killing the Collector, enrichment and redaction in the middle, `batch` last for export efficiency.

```yaml
receivers:
  otlp:
    protocols:
      grpc: {endpoint: 0.0.0.0:4317}
processors:
  memory_limiter: {check_interval: 1s, limit_mib: 512, spike_limit_mib: 128}
  attributes/redact:
    actions:
      - {key: http.request.header.authorization, action: delete}
  batch: {send_batch_size: 8192, timeout: 5s}
exporters:
  otlphttp: {endpoint: https://tempo.internal:4318}
service:
  pipelines:
    traces:
      receivers: [otlp]
      processors: [memory_limiter, attributes/redact, batch]
      exporters: [otlphttp]
```

Use the contrib distribution (`otelcol-contrib`) when you need `tail_sampling`, `transform`, or vendor exporters. The config lives in the repository, is reviewed like code, is validated in CI with `otelcol validate --config`, and has a test that feeds a sample payload through and asserts the redaction actually happened.

## Common pitfalls

- `SimpleSpanProcessor` or any synchronous exporter in production: telemetry latency becomes request latency.
- `service.name` unset or set per-span; `unknown_service` in the backend makes cross-signal joins impossible.
- Double instrumentation: a manual span wrapping an auto-instrumented client call, producing two spans for one operation.
- Invented attribute names (`env`, `svc`, `status`) that collide with or shadow semconv names.
- Missing `memory_limiter`, or `batch` placed before redaction so unredacted data sits in export queues.
- API/SDK version skew across OTel packages, silently yielding no-op tracers with no error raised.

## Definition of done

- [ ] OTel packages pinned to one coherent 1.x version set; provider configured once at process start.
- [ ] Resource carries `service.name`, `service.version`, and `deployment.environment.name`; nothing exports as `unknown_service`.
- [ ] Attribute names checked against semconv with stability status noted; migrations use `OTEL_SEMCONV_STABILITY_OPT_IN` dual emission.
- [ ] Auto-instrumentation covers frameworks and clients; manual spans exist only for business logic, with no duplicated operations.
- [ ] Export is OTLP to a Collector; endpoint, protocol, and sampler come from `OTEL_*` environment variables, not code.
- [ ] Collector pipeline order is `memory_limiter`, enrichment/redaction, `batch`; config is versioned, validated in CI, and covered by a redaction test.
- [ ] Span, attribute, and status assertions written first (TDD) against in-memory exporters; no test reaches a live Collector or backend.
