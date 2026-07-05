# Operating Principles

This skill is the observability agent's operating stance: telemetry is a feature of the system, designed, reviewed, tested, and paid for like one. It defines the instrument-first culture, the correlated-signals requirement, observability as code, the telemetry review that happens in every PR, and cost ownership. The detailed per-signal rules live in the sibling skills; this file governs how the agent works.

## Instrument-first culture

Instrumentation ships in the same change as the behavior it observes, not as a follow-up ticket that never gets scheduled. "It works but we cannot see it" means the work is not done: the definition of done for any feature includes the question "can on-call diagnose this at 3 a.m. from the telemetry alone". Instrument for the questions an incident will ask — is a user hurting, where, since when, and what changed — not for vanity counters. A metric or span that cannot plausibly appear in an incident query or a capacity decision is cost without value and should not ship.

The practical test applies to this repository too: when a change lands in `solomon_harness` that adds a new failure path — say, the SurrealDB client falling back to SQLite — the same PR carries the WARN log with structured fields, the metric that makes the fallback rate visible, and the span attribute that marks affected traces. The reviewer can then see the feature and its observability as one unit.

## One correlated system

The three signals are one system, not three products. A log, a metric exemplar, and a trace describing the same event must share `trace_id` and the same `service.name` resource identity, so a responder can pivot from a metric spike to the exact traces behind it to the logs of the failing span without copying ids between tools. If that pivot breaks anywhere, the instrumentation is incomplete no matter how much is being emitted. OpenTelemetry is the default for all of it: OTel SDK in the application, OTLP out, and the OpenTelemetry Collector as the single egress point. Applications never talk to vendor backends directly; the Collector centralizes sampling, redaction, and batching, and keeps backends swappable without touching application code.

## Observability as code

Every observability artifact is versioned, reviewed, tested, and deployed through the same pipeline as application code:

- Collector configs live in the repo and are validated in CI (`otelcol validate --config`) plus a payload test asserting redaction and routing.
- Alert rules are files, checked with `promtool check rules` (or the backend's equivalent), with required annotations (severity, owner, runbook_url) enforced by a CI validator.
- Dashboards are provisioned from git with stable uids; SLO definitions are declarative files, not clicks in a UI.
- Instrumentation follows the house TDD cycle: write the failing assertion first against in-memory exporters (`InMemorySpanExporter`, the in-memory metric reader), then write the instrumentation that makes it pass. Tests are hermetic — external backends (Prometheus, Tempo, Loki, vendor APIs) are mocked, and no test reaches a live Collector.

Nothing about the telemetry pipeline is changed by hand in production. A config that only exists in a backend UI is drift waiting to erase itself.

## Telemetry review in PRs

Observability review is part of code review, not a separate audit. On every behavior-changing PR the reviewer checks:

- New entry point or outbound call: does it have a span with semconv attributes, and does context propagate across it?
- New failure mode: is it distinguishable in an ERROR or WARN log with structured fields, does a metric expose its rate, and does an existing SLO or alert cover it — or is the gap stated deliberately?
- New metric or label: is the cardinality delta computed and inside the budgets from the metrics skill?
- New log line: is the level justified, the message a stable signature, secrets and PII excluded, and hot-path volume sampled?
- Removed or renamed telemetry: are the dashboards, alerts, and SLOs that referenced it updated in the same change, not discovered broken during the next incident?

A PR that fails these checks gets the same treatment as one that fails tests.

## Cost and cardinality ownership

Telemetry cost is an engineering budget with numbers, owned by whoever adds the telemetry. Cardinality is the top cause of TSDB outages and observability cost blowups, so it is bounded on purpose: budgets are declared before a label ships, and ingest budgets exist per service for logs and traces with alerts at 80 percent. Spend is reviewed monthly, and deleting unused telemetry — the metric no dashboard reads, the DEBUG log nobody queried in a quarter — is real prioritized work, not housekeeping that never happens.

## Common pitfalls

- Telemetry deferred to a follow-up ticket, shipping features that are blind in production from day one.
- Signals emitted in isolation, with no shared `trace_id` or consistent `service.name`, so no pivot is possible.
- Applications exporting straight to a vendor backend, hard-wiring the vendor and bypassing central sampling and redaction.
- Dashboards, alerts, or Collector configs edited by hand in production with no git counterpart.
- Instrumentation written without tests, verified only by eyeballing a backend after deploy.
- PRs that rename or delete telemetry while leaving the dashboards and alerts that depend on it silently broken.
- Nobody owning telemetry spend, until the log bill or a cardinality explosion forces an emergency purge.

## Definition of done

- [ ] Every behavior change ships its instrumentation in the same PR, answering the 3 a.m. diagnostic question.
- [ ] Logs, metrics, and traces for one event share `trace_id` and resource identity; the cross-signal pivot is verified.
- [ ] All telemetry flows through the OTel SDK and Collector; no direct vendor export from application code.
- [ ] Collector configs, alert rules, dashboards, and SLO definitions are versioned, CI-validated, and provisioned — never hand-edited in production.
- [ ] Instrumentation was written test-first against in-memory exporters; suites are hermetic with all backends mocked.
- [ ] The PR telemetry checklist was applied: spans on new paths, coverage for new failure modes, cardinality deltas computed, log levels justified, dependent assets updated.
- [ ] Cardinality and ingest budgets are declared with 80 percent alerts, and a monthly spend review exists with deletion work actually scheduled.
