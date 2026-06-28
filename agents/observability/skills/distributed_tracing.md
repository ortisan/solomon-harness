## Distributed tracing


- Propagate context with W3C Trace Context (`traceparent`, `tracestate`) on every outbound HTTP call and IPC hop. Use baggage for cross-cutting business context, but keep baggage small (it travels on every hop).
- Span naming is low cardinality (`GET /users/{id}`, `db.query.select_user`, `http.out.fetch_rates`). Put the high-cardinality detail in span attributes, never in the span name.
- Create a root or child span at every entry point (HTTP handler, queue consumer, cron job) and child spans for significant nested work: database queries, outbound calls, file system access, heavy computation. Follow `db.*`, `http.*`, `messaging.*` semantic conventions for attributes.
- On exception: call `record_exception`, set span status to ERROR, attach the stack trace, then handle or re-raise. Do not leak secrets into span attributes or events.
- Link asynchronous and fan-out work with span links so a producer span connects to its consumer spans across a queue boundary.
- Sampling strategy: head sampling at a fixed ratio for baseline volume, plus tail-based sampling in the Collector to keep 100% of error and slow traces. Tail sampling is where you guarantee you never throw away the trace you actually need.
