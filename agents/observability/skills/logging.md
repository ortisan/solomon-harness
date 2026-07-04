# Logging

This skill sets the logging standard: structured JSON events, correlated to traces, safe by construction, and priced in before they ship. Logs are the highest-volume and most expensive signal per byte, so structure, level discipline, and cost control are engineering requirements, not style preferences.

## Structure and schema

Emit one JSON event per line to stdout and let the Collector or log agent ship it; the application never writes to a log backend directly. Multi-line prose is banned in production logs except stack traces attached as a field. Mandatory fields on every record: `timestamp` (RFC 3339, UTC), `level`, `message`, `service.name`, `service.version`, `deployment.environment.name`, and `trace_id`/`span_id` whenever a span is active.

Keep the message stable and put variable data in fields, because grouping, deduplication, and sampling all key on the message. `"memory write failed"` with `backend="surrealdb"` and `table="decision"` groups into one signature; an f-string that interpolates the URL into the message produces a unique message per request and defeats all three.

```python
import logging
from opentelemetry.instrumentation.logging import LoggingInstrumentor

LoggingInstrumentor().instrument()  # injects trace_id/span_id into records
logger = logging.getLogger("solomon_harness.tools.database_client")
logger.warning(
    "memory write fell back to sqlite",
    extra={"backend": "sqlite", "table": "decision", "reason": "surrealdb_unreachable"},
)
```

Pair this with a JSON formatter (`python-json-logger`, or structlog with a JSON renderer). The OTel logging instrumentation injects the trace context automatically; correlation ids are never passed by hand.

## Level policy

- ERROR: something failed and a human must look. Never sampled, never rate-limited away, and every ERROR should map to an alert, an SLO burn, or a conscious decision that it does not page.
- WARN: degraded but self-recovering — a retry that succeeded, a circuit half-open, a fallback engaging. In this repo, the SQLite fallback taking over from SurrealDB is exactly WARN: work continues, but the operator should know.
- INFO: state transitions and business events (session saved, release recorded, job completed). Not per-iteration chatter.
- DEBUG: developer detail, off in production by default, switchable per module through configuration without a redeploy.

The test for a level: if changing it would change neither who reads the log nor what happens next, the level is wrong or the log is noise.

## What never to log

Secrets and PII are banned from logs, span attributes, and baggage: passwords, tokens, API keys, `Authorization` and `Cookie` headers, full card numbers, raw request bodies containing personal data. In this repo the SurrealDB credentials arrive via `SURREAL_URL`/`SURREAL_USER`/`SURREAL_PASS`: log the host and database name, never a URL with userinfo and never the password, matching the userinfo redaction already applied in the wiki bootstrap code.

Enforcement is layered. Redact at the source with an explicit deny-list of field names (`password`, `token`, `secret`, `authorization`, `api_key`, `cookie`, `set-cookie`) applied by the logging layer, and run a Collector `transform`/redaction processor as the backstop. The backstop is not the mechanism: a value that was emitted and then redacted still crossed the wire and may sit in a local buffer.

## Performance, sampling, and cost control

Keep log I/O off the hot path: write to stdout or use a non-blocking handler; a synchronous logger call that blocks on disk or network inside a request handler is a latency bug.

Do the volume math before shipping a new log line. One 1 KB INFO line per request at 100 requests/s is roughly 259 GB per month; at typical managed-platform ingest pricing of 0.50 to 3.00 USD per GB, one chatty line costs hundreds of dollars monthly for data nobody reads. Rules:

- Sample repetitive high-volume INFO/DEBUG (for example 1-in-100 on hot paths) and rate-limit identical WARNs (first 5 per minute, then sampled). Never sample ERROR.
- Keep unbounded values (user ids, request ids, full URLs) out of indexed fields; they belong in the event body or as span attributes.
- Set retention tiers explicitly: hot and searchable 7 to 30 days, warm 30 to 90 days, archive to object storage (around 0.023 USD per GB-month) beyond. Nothing sits in the hot tier by default.
- Give each service an ingest budget (for example 5 GB/day) and alert at 80 percent of it; a log-volume regression is a defect on par with a memory leak.

## Common pitfalls

- Interpolating variable data into the message string, producing one unique message per request and breaking grouping and sampling.
- Hand-built "correlation ids" instead of the injected `trace_id`/`span_id`, so logs cannot be joined to traces.
- Secrets or PII in log fields with the Collector redaction treated as the primary control instead of the backstop.
- ERROR used for expected conditions (validation failures, 404s), training responders to ignore the level.
- Synchronous log writes to disk or network on the request path.
- No retention policy, leaving every byte in the hot tier and turning the log bill into the largest observability line item.

## Definition of done

- [ ] All production logs are single-line JSON with the mandatory fields, including `trace_id`/`span_id` injected by instrumentation.
- [ ] Messages are stable signatures; variable data lives in structured fields.
- [ ] Level semantics applied per the policy; DEBUG off in production and switchable without redeploy.
- [ ] Source-level deny-list redaction in place, Collector redaction as backstop, and a test proving a seeded secret never reaches the exporter.
- [ ] High-volume INFO/DEBUG sampled or rate-limited with the ratio documented; ERROR is never sampled.
- [ ] Retention tiers and a per-service ingest budget are set, with an alert at 80 percent of budget.
- [ ] Log emission is asynchronous or stdout-based; no blocking I/O on the request path.
