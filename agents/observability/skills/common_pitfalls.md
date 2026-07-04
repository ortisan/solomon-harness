## Common pitfalls


- Averaging latency or alerting on the mean instead of percentiles.
- High-cardinality labels (`user_id`, `request_id`, raw paths) that detonate the TSDB.
- Synchronous logging or span export on the request hot path.
- Lost context across async/queue boundaries (no span links, no propagated `traceparent`).
- Cause-based alerts that generate fatigue while real SLO burns go unnoticed.
- Sampling that discards error or slow traces.
- Three disconnected signals with no shared `trace_id`/`service.name`, so no pivoting is possible.
- Dashboards with no SLO/error-budget context.
