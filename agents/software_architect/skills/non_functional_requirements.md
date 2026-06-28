## Non-functional requirements


NFRs are part of the architecture, not an afterthought. Every significant NFR must be a measurable scenario with a number and a source, not an adjective. "Fast" and "scalable" are not requirements.

State each as a quality-attribute scenario with all six parts: source, stimulus, artifact, environment, response, response measure. Cover at minimum:

- **Performance** — p50/p95/p99 latency targets and sustained/peak throughput, named per critical path. Example: "checkout API p99 under 300 ms at 500 req/s".
- **Availability** — target SLO (for example 99.9% monthly), allowable error budget, and the failure modes it tolerates.
- **Scalability** — the dimension and ceiling (data volume, concurrent users, tenants) and whether scaling is horizontal or vertical.
- **Security** — see STRIDE below; authn/authz model; data classification; encryption in transit and at rest.
- **Reliability/resilience** — timeouts, retries with backoff and jitter, circuit breakers, bulkheads, graceful degradation, idempotency for retried operations.
- **Observability** — required logs, metrics (RED for request-driven services, USE for resources), traces, and the SLIs that back each SLO. An NFR with no SLI is unverifiable.
- **Maintainability, portability, compliance, cost** — state them when they constrain the design.

Tie each NFR to the architectural mechanism that satisfies it and to the test or monitor that proves it. An NFR that no test or dashboard checks does not exist.
