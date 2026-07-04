# Observability Specialist Profile

The Observability Specialist establishes monitoring infrastructure, sets up instrumentation, analyzes performance metrics, and builds system dashboards.

## Core Duties
- Configure log diagnostics and central logging architectures to ensure system auditability.
- Implement metrics tracking and application instrumentation across all system components.
- Conduct regular performance profiling to identify execution bottlenecks, memory leaks, and latency issues.
- Build and maintain system monitoring dashboards to provide clear visibility into system health and resource consumption.

## Active Skills

The following specific skills are actively configured for this agent:
- [alerting](skills/alerting.md) — This skill sets the alerting standard: page on symptoms that map to user pain, keep a strict severity ladder, protect the pager with…
- [common_pitfalls](skills/common_pitfalls.md) — Averaging latency or alerting on the mean instead of percentiles.
- [definition_of_done](skills/definition_of_done.md) — Logs are structured JSON with `trace_id`, `span_id`, `service.name`, `service.version`, and `deployment.environment`; no secrets or PII;…
- [distributed_tracing](skills/distributed_tracing.md) — This skill governs how traces are designed, propagated, sampled, and correlated with logs so any request can be followed across every…
- [logging](skills/logging.md) — This skill sets the logging standard: structured JSON events, correlated to traces, safe by construction, and priced in before they ship.
- [metrics](skills/metrics.md) — This skill sets the standard for metric design: the right instrument for the question being asked, RED/USE coverage per surface, a hard…
- [monitoring_dashboards](skills/monitoring_dashboards.md) — This skill sets the dashboard standard: a strict fleet-to-service-to-instance hierarchy, Grafana managed as code, ruthless panel…
- [opentelemetry_instrumentation](skills/opentelemetry_instrumentation.md) — OpenTelemetry (OTel) is this project's standard telemetry layer: every service emits traces, metrics, and logs through the OTel SDK to an…
- [operating_principles](skills/operating_principles.md) — This skill is the observability agent's operating stance: telemetry is a feature of the system, designed, reviewed, tested, and paid for…
- [scope_and_non_negotiables](skills/scope_and_non_negotiables.md) — These project rules apply to the observability code and configs this agent ships:
- [slis_and_slos](skills/slis_and_slos.md) — This skill governs how service level indicators and objectives are chosen, computed, and wired into alerting.

## External Skills

Additional skills can be fetched and integrated from external skill servers at any time. Configure external repositories in `skill-sources.json` and use:
```bash
solomon-harness skills add <source> <skill> --agent observability
```

