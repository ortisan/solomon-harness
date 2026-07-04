# Metrics

This skill sets the standard for metric design: the right instrument for the question being asked, RED/USE coverage per surface, a hard cardinality budget with numbers, histograms that can answer percentile and SLO questions, and a clear position on Prometheus versus OTLP collection.

## Instrument types

Choose the instrument by the query you will run against it, not by what is easiest to emit:

- Counter: monotonic totals — requests served, errors, retries, bytes sent. The only instrument where `rate()` is meaningful.
- UpDownCounter: additive values that can decrease — active connections, items in a queue you increment and decrement.
- Gauge (observable): sampled point-in-time state you cannot add across instances meaningfully — memory percent, pool utilization, config values.
- Histogram: distributions — latency, payload size, query time. Anything you will ask a percentile of must be a histogram from the start; you cannot recover a distribution from a counter later.

Naming and units follow OTel semantic conventions: base units (seconds, bytes), the UCUM `unit` field set on the instrument, names like `http.server.request.duration`. Do not hand-encode units into metric names; the Prometheus exporter appends `_seconds`-style suffixes itself, and doing both yields `duration_seconds_seconds`.

## RED, USE, and golden signals

Apply RED (Rate, Errors, Duration) to every request-driven service and USE (Utilization, Saturation, Errors) to every resource: CPU, memory, disk, connection pools, queues. The four golden signals (latency, traffic, errors, saturation) are the cross-check on every service overview. A service missing any RED metric, or a bounded resource missing saturation, is incompletely instrumented.

## Cardinality budgets

Active series count is the product of label value counts, multiplied by instance count. Do the math before adding a label: `http.server.request.duration` with `http.route` (30 values) times `http.request.method` (5) times `http.response.status_code` (10) is 1,500 combinations per instance; across 20 instances that is 30,000 series for one metric. Budgets this agent enforces:

- Per metric per instance: at most 1,000 label combinations.
- Per metric fleet-wide: at most 10,000 series.
- Per service, all metrics: at most 100,000 active series; alert at 80 percent.

Each active series costs a few kilobytes of TSDB head memory plus index churn, so a million-series accident is a multi-gigabyte backend outage. Never label by `user_id`, `request_id`, `session_id`, `trace_id`, raw URL path, error message text, or any unbounded enum; templatize paths (`/users/{id}`). A label must have enumerable values and a stated budget: in this repo, a `backend` label on a `solomon.memory.write.duration` histogram with exactly two values, `surrealdb` and `sqlite`, is the model — bounded, meaningful, and it directly answers "is the fallback active".

## Histograms: buckets and exponential histograms

Explicit-bucket histograms only answer questions their bucket edges allow. Tune edges per metric and include the SLO threshold as an exact edge (a 300 ms latency SLO needs a 0.3 s boundary), otherwise the SLI good/total ratio cannot be computed from the histogram. The SDK default edges are generic and top out poorly for sub-100 ms services; replace them via a View.

Prefer exponential histograms for latency where the backend supports them: base-2 buckets with an auto-adjusting scale, 160 buckets by default, holding relative error to a few percent across the whole range with no hand-tuning. OTLP carries them natively; Prometheus supports them as native histograms (feature-flagged since 2.40, first-class in the 3.x line).

Percentiles, done correctly: aggregate histograms server-side, then take the quantile — `histogram_quantile(0.99, sum by (le, route) (rate(http_server_request_duration_seconds_bucket[5m])))`. Never average a percentile across instances (the result is meaningless) and never alert on the mean. Track p50, p90, p95, p99, and p99.9 for latency. Emit exemplars on histograms so a bucket links to a representative trace; that is the metric-to-trace pivot.

## Prometheus versus OTLP

Know the collection model you are on. Prometheus pulls (scrapes) cumulative-temporality series; OTLP pushes and supports both delta and cumulative temporality — set cumulative when exporting toward Prometheus-compatible backends or counters will not join correctly. Prometheus 3.x ingests OTLP directly (`/api/v1/otlp/v1/metrics`), but keep the Collector in the path anyway for redaction, batching, and backend portability. Query hygiene: compute `rate()`/`increase()` over a window at least 4x the scrape interval (15 s scrape means a 1 m minimum window) so a missed scrape does not punch holes in the series; `rate()` handles counter resets itself.

## Common pitfalls

- A counter or gauge where a percentile question will be asked; the distribution is unrecoverable after the fact.
- Unbounded label values (`user_id`, raw paths, error strings) detonating the TSDB.
- Averaging percentiles across instances, or alerting on mean latency.
- Bucket edges that do not include the SLO threshold, making the latency SLI uncomputable.
- Units baked into names by hand alongside exporter suffixing, or non-base units mixing ms and s across services.
- Delta temporality pushed at a cumulative-only backend, silently corrupting rates.
- `rate()` windows shorter than 4x the scrape interval, producing gappy, flappy panels and alerts.

## Definition of done

- [ ] Every metric uses the correct instrument type, semconv-aligned name, base unit, and the `unit` field.
- [ ] RED coverage on every request-driven surface, USE on every bounded resource, golden signals on the service overview.
- [ ] Cardinality math is written down for every new label; budgets (1,000 per metric per instance, 10,000 fleet-wide, 100,000 per service) hold, with an alert at 80 percent.
- [ ] Latency uses exponential histograms where supported, or explicit buckets that include the SLO threshold as an edge.
- [ ] Percentiles computed via server-side histogram aggregation; no averaged percentiles, no mean-based alerts.
- [ ] Exemplars enabled on histograms and the metric-to-trace pivot verified.
- [ ] Temporality and scrape/rate-window settings match the backend and are documented with the metric.
