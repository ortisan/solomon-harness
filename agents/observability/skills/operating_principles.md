# Observability Best Practices

Concrete standards for logging, metrics, tracing, OpenTelemetry instrumentation, dashboards, SLIs, and alerting that this agent must apply to every change.

## Operating principles


- Treat the three signals as one correlated system. A log, a metric, and a trace describing the same event must share `trace_id` and `service.name`. If you cannot pivot from a metric spike to the exact traces behind it, the instrumentation is incomplete.
- Instrument for questions you will ask at 3 a.m. during an incident, not for vanity counters. Every metric and span must answer "is a user hurting, and where".
- Default to OpenTelemetry SDK + OTLP exporter + OpenTelemetry Collector. The Collector is the single egress point; applications never talk to vendor backends directly. This keeps backends swappable and centralizes sampling, redaction, and batching.
- Bound cardinality on purpose. Cardinality is the number one cause of cost blowups and time-series database (TSDB) outages.
