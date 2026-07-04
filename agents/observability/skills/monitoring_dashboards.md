# Monitoring Dashboards

This skill sets the dashboard standard: a strict fleet-to-service-to-instance hierarchy, Grafana managed as code, ruthless panel discipline instead of walls of graphs, and working links between metrics, traces, and logs. A dashboard is an answer machine for a named question; if nobody can say what question a panel answers, the panel goes.

## Dashboard hierarchy: fleet, service, instance

Three levels, each linking down to the next:

- Fleet (or product) overview: one row per service showing SLO status and error-budget remaining, current burn rate, and a deploy marker. This is the on-call landing page; it answers "is anything hurting users right now" in under ten seconds.
- Service overview: one per service. Golden signals / RED at the top (rate, error ratio, latency percentiles from histograms), SLO state and budget next, dependencies and saturation below. The responder must be able to localize a problem from the first screen without scrolling.
- Instance / debug: USE per resource (CPU, memory, disk, pools, queues), runtime internals (GC, event loop, connection churn), and subsystem deep-cuts. Reached through drill-down links from the service overview, never by browsing a folder of forty boards.

Every level carries deploy, config-change, and feature-flag annotations on the time axis — pushed by CI — because "what changed" is the first incident question and eyeballing timestamps across tools wastes the minutes that matter.

## Grafana conventions

- Dashboards are code. Definitions live in git and are provisioned — via file provisioning, the Grafana Foundation SDK or grafonnet, or the Terraform provider. Hand-edited-only production dashboards are configuration drift; an edited board that was never exported is lost at the next provision cycle.
- Stable `uid`s on every dashboard so links from alerts, runbooks, and other boards never rot. Folders per team or domain, not per person.
- Template variables (`$environment`, `$service`, `$region`, `$instance`) instead of cloned per-service copies. Dashboard sprawl is a maintenance failure: ten near-identical boards means nine stale ones.
- Every panel sets its unit, and latency panels name the percentile in the title (`p99 latency`). Enable the shared crosshair so panels align under the cursor. Use consistent time ranges and refresh intervals per board.
- Render latency from histograms with `histogram_quantile`, error rate as a ratio (`errors / total`), never an absolute count that scales with traffic, and no raw averages on a latency panel.

## Avoiding the wall of graphs

The overview earns each panel: 10 to 12 panels maximum, one screen, no scrolling. Each panel answers a named question — "are users seeing errors", "are we inside the latency SLO", "is a dependency saturating" — and the question belongs in the panel title or description. If a panel cannot be captioned with its question, it is decoration and gets cut. Depth is not lost; it moves to linked debug boards. A 60-panel board is not thorough, it is unreadable at 3 a.m., and it hides the one panel that matters behind 59 that do not. Panels whose only purpose is to look busy (uptime counters, vanity totals) are review rejects.

## Linking traces, logs, and metrics

Dashboards are the pivot surface between the three signals, and the links are configuration that must be built and tested:

- Metrics to traces: enable exemplars on latency histograms so a dot on the panel opens the exact trace in Tempo or Jaeger.
- Logs to traces: configure the log datasource to extract `trace_id` (Loki derived fields) so a log line links to its trace; configure trace-to-logs the other way with matching `service.name` labels.
- Panel data links carry the current `$service`/`$instance` variables into the drill-down board, so context follows the click.

The acceptance test for dashboard work is the walk: from a latency spike on the service overview, click an exemplar to the trace, jump to the failing span's logs — with no manual copying of ids between tools. For a service like this repo's memory layer, that walk runs from a `solomon.memory.write.duration` p99 panel to the trace of one slow SurrealDB write to the WARN log showing the SQLite fallback engaging.

## Common pitfalls

- Wall-of-graphs overviews where the signal panel is buried among dozens of vanity panels.
- Cloned dashboards per service or environment instead of template variables; most clones are stale.
- Hand-edited production dashboards that exist nowhere in git and vanish on the next provisioning run.
- Latency panels showing averages, or counts instead of ratios for errors, hiding real regressions.
- No SLO or error-budget context on the overview, so nobody can tell whether a spike matters.
- Broken or untested cross-signal links, forcing responders to copy ids between tools mid-incident.
- Missing deploy annotations, leaving "what changed" to archaeology.

## Definition of done

- [ ] The three-level hierarchy exists: fleet overview, service overview per service, linked instance/debug boards.
- [ ] Every dashboard is provisioned from git with a stable `uid`; no hand-edited-only boards in production.
- [ ] The service overview fits one screen with at most 12 panels, each captioned with the question it answers, with SLO state and error budget visible.
- [ ] Latency rendered from histograms with named percentiles; error rate as a ratio; units set on every panel.
- [ ] Template variables replace cloned boards; deploy and flag annotations flow from CI.
- [ ] Exemplar, trace-to-logs, and log-to-trace links configured, and the spike-to-trace-to-log walk verified end to end.
- [ ] Alerts and runbooks link to the relevant dashboard by `uid`, not by URL guesswork.
