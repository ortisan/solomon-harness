## Metrics


- Pick the right method per surface: RED (Rate, Errors, Duration) for request-driven services; USE (Utilization, Saturation, Errors) for resources (CPU, memory, disk, queues, connection pools); the four golden signals (latency, traffic, errors, saturation) as the cross-check on every service overview.
- Use the correct instrument type. Counter for monotonic totals (requests, errors, retries). Gauge for point-in-time state (pool size, queue depth, memory percent). Histogram for distributions (latency, payload size, query time). Prefer OTel exponential histograms for latency so percentiles stay accurate without hand-tuned buckets.
- Naming and units follow OTel semantic conventions. Record latency in seconds and sizes in bytes (base units), e.g. `http.server.request.duration`. Do not bake units into label values.
- Cardinality budget is hard. Never use `user_id`, `request_id`, `session_id`, raw URL path, or unbounded enums as metric labels. Templatize paths (`/users/{id}`). Keep per-metric label combinations in the low thousands of series, not millions. Define the series budget before adding a label.
- Percentiles, done correctly: aggregate histograms server-side with `histogram_quantile`; never average a percentile across instances and never alert on the mean. Track p50, p90, p95, p99, and p99.9 for latency.
- Emit exemplars on histograms so a latency bucket links directly to a representative trace. This is the metric-to-trace pivot.
- Know your collection model: Prometheus pull/scrape vs OTLP push. Use `rate()`/`increase()` over a window at least 4x the scrape interval so missed scrapes do not punch holes in the series; `rate()` already corrects for counter resets on its own.
