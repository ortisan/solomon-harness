## OpenTelemetry instrumentation


- Prefer auto-instrumentation for frameworks and clients; add manual spans only for business logic the libraries cannot see. Never double-instrument the same call.
- Set resource attributes once, correctly: `service.name` (required), `service.version`, `service.namespace`, `deployment.environment`, and host/`k8s.*` from resource detectors. These are the join keys across all three signals.
- Collector pipeline order matters: `memory_limiter` first (protects against OOM), then resource/attributes processors for enrichment and PII redaction, then `batch` last before the exporters (efficiency). Configure receivers, processors, and exporters explicitly; do not run an unbounded queue.
- Version the Collector config in the repo and treat it as code: reviewed, tested, rolled out like any deployment.
