---
name: scope-and-non-negotiables
description: States the binding project rules for observability deliverables covering TDD against in-memory exporters, hermetic mocked test suites, guarded derived-metric math, quant trading latency and slippage budgets, and STRIDE controls on the telemetry pipeline itself. Use when scoping or reviewing observability work for compliance with the project's non-negotiable engineering and security rules.
---

# Observability Scope and Non-Negotiables

The binding project rules for every observability deliverable, with OpenTelemetry as the house telemetry standard. They cover TDD against in-memory exporters, hermetic test suites, guarded derived-metric math, quant latency budgets, and STRIDE applied to the telemetry pipeline itself.

## Scope and non-negotiables


These project rules apply to the observability code and configs this agent ships:

- TDD is mandatory. Write the failing test first, then the instrumentation. Use OTel in-memory exporters (`InMemorySpanExporter`, in-memory metric reader) to assert that spans, attributes, status codes, and metric points are emitted as specified. Test Collector configs against sample payloads. Follow SOLID and keep exporters, processors, and instrumentation behind clear contracts.
- QA: mock all external services and telemetry backends (Prometheus, Tempo/Jaeger, Loki, vendor APIs) in tests so suites are hermetic and deterministic. No test reaches a live collector or backend.
- ML/analytics guards: when computing derived telemetry (rates, ratios, burn rates, anomaly scores), validate array/tensor shapes before the operation, guard every division for divide-by-zero (zero valid events), and guard against float overflow and NaN propagation. If anomaly detection uses a model, prevent overfitting with cross-validation and out-of-sample tests, and ensure zero data leakage between training and evaluation windows.
- Quant systems: when instrumenting a trading service, the model hypothesis being observed must state target Sharpe ratio (for example >= 1.5), maximum drawdown limit (for example <= 15%), profit factor (for example >= 1.3), latency and slippage constraints (for example p99 order round-trip < 50 ms, assumed slippage in basis points), the dataset and features used, and the network/model architecture. Instrument and alert against these exact budgets, especially order-to-fill latency and realized vs assumed slippage.
- Security (STRIDE) for the telemetry pipeline: Spoofing (authenticate Collector receivers and scrape endpoints, mutual TLS); Tampering (sign or restrict write access to metrics and logs); Repudiation (preserve immutable audit logs with actor and trace context); Information disclosure (redact PII and secrets in logs, spans, and baggage); Denial of service (cap cardinality and set `memory_limiter` and queue bounds so a cardinality bomb cannot take down the backend); Elevation of privilege (least-privilege credentials for exporters and the Collector, no shared god-tokens).

## Common pitfalls

- Instrumentation written before its failing test — the span or metric-point assertion against `InMemorySpanExporter` comes first, and code-first work breaks the TDD mandate.
- A test suite that reaches a live Collector, Prometheus, Tempo, or Loki — the run becomes nondeterministic and violates the hermetic-QA rule.
- A burn rate or error ratio dividing by the valid-event count with no zero guard — zero traffic produces NaN or inf that propagates straight into alert expressions.
- An anomaly-detection model scored on the window it trained on — leakage between training and evaluation windows makes the detector's precision fictitious.
- A trading service instrumented without the hypothesis card's budgets — with no target for order-to-fill p99 or assumed slippage, there is nothing to alert realized values against.
- Unauthenticated Collector receivers, or PII left unredacted in logs, spans, or baggage — fails the spoofing and information-disclosure controls in the STRIDE list above.
- Direct vendor-SDK export that bypasses OpenTelemetry and the Collector — a deviation from the house default that requires an ADR, not a quiet dependency.

## Definition of done

- [ ] Every span, attribute, status code, and metric point asserted first via in-memory exporters and readers; Collector configs exercised against sample payloads.
- [ ] The suite is hermetic: Prometheus, Tempo/Jaeger, Loki, and vendor APIs all mocked, no live backend reached.
- [ ] Every derived-telemetry division carries a zero-denominator guard, with shapes checked ahead of each array or tensor operation; NaN and overflow cannot reach an alert expression.
- [ ] Any anomaly model is validated with cross-validation plus an out-of-sample window and zero leakage between training and evaluation.
- [ ] Trading instrumentation alerts against the stated budgets, including order-to-fill latency (for example p99 < 50 ms) and realized-versus-assumed slippage.
- [ ] All six STRIDE controls verified on the pipeline: mTLS-authenticated receivers, restricted writes, immutable audit logs, PII redaction, cardinality caps with `memory_limiter` and queue bounds, least-privilege exporter credentials.
- [ ] Telemetry flows through the OTel SDK and Collector; any deviation from the house default is recorded in an ADR.
