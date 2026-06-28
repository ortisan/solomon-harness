## Logging


- Structured JSON only, one event per line. No multi-line human prose in production logs except attached stack traces.
- Mandatory fields on every record: `timestamp` (RFC 3339 / ISO 8601, UTC), `level`, `message`, `service.name`, `service.version`, `deployment.environment`, plus `trace_id` and `span_id` when a span is active. Use OTel log correlation so these are injected automatically rather than passed by hand.
- Level semantics, applied consistently: ERROR = actionable, something failed and someone must look; WARN = degraded but self-recovering; INFO = state transitions and business events (order placed, job completed); DEBUG = developer detail, disabled in production by default.
- Never log secrets or PII: tokens, passwords, API keys, full PANs, auth headers, raw request bodies with personal data. Enforce a redaction processor in the Collector as a backstop, but redact at the source first. Maintain an explicit deny-list of field names.
- Keep log I/O off the hot path. Use a non-blocking/async appender or write to stdout and let the Collector ship it. A synchronous logger call inside a request handler that blocks on disk or network is a latency bug.
- Sample high-volume INFO/DEBUG if needed, but never sample ERROR. Errors are rare and always wanted.
- Do not put unbounded values (user IDs, request IDs, full URLs) into indexed log fields; keep them in the message payload or as span attributes instead.
- Retention tiers: hot 7-30 days searchable, warm 30-90 days, cold/archive beyond. Set this explicitly; do not let everything sit in the expensive hot tier.
