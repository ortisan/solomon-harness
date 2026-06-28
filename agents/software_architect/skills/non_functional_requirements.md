# Non-Functional Requirements

Treat non-functional requirements as part of the architecture and write each one as a testable fit-criteria scenario with a number and a verification mechanism, never as an adjective like "fast" or "scalable" that cannot be reviewed or proven.

## Use ISO/IEC 25010 as the coverage checklist

Run the in-scope work against the ISO/IEC 25010:2023 product-quality model so no attribute is forgotten. The 2023 revision defines nine characteristics:

- Functional suitability — completeness, correctness, appropriateness.
- Performance efficiency — time behavior, resource use, capacity.
- Compatibility — co-existence, interoperability.
- Interaction capability (formerly usability) — learnability, operability, accessibility.
- Reliability — maturity, availability, fault tolerance, recoverability.
- Security — confidentiality, integrity, non-repudiation, accountability, authenticity.
- Maintainability — modularity, reusability, analysability, modifiability, testability.
- Flexibility (formerly portability) — adaptability, scalability, installability, replaceability.
- Safety (added in 2023) — operational constraint, risk identification, fail-safe, hazard warning, safe integration.

The model is a checklist, not a specification. For each characteristic that constrains this system, write a concrete scenario; for the rest, record "not architecturally significant" so the omission is a decision, not an oversight.

## Write each NFR as a quality-attribute scenario

State every significant NFR with the six parts of a SEI quality-attribute scenario: source, stimulus, artifact, environment, response, response measure. The response measure is the number that makes it testable.

- Performance — p50/p95/p99 latency and sustained/peak throughput per critical path. "Checkout API p99 < 300 ms at 500 rps on the production cluster."
- Availability — target SLO (for example 99.9% monthly), the error budget it implies (about 43 minutes/month), and the failure modes it tolerates.
- Scalability — the dimension and ceiling (data volume, concurrent users, tenants) and whether scaling is horizontal or vertical.
- Security — authn/authz model, data classification, encryption in transit and at rest; the deep threat work lives in `architecture_review_gate` and the `security` agent.
- Reliability/resilience — timeouts, retries with backoff and jitter, circuit breakers, and idempotency for retried operations (see `resilience_patterns`).
- Observability — the SLIs that back each SLO; RED for request-driven services, USE for resources. An NFR with no SLI is unverifiable.

## Worked NFR table

State the architecturally significant NFRs in a table that names the verification for each, so review can check whether each is actually proven:

| Attribute | Metric | Target | Verification |
|---|---|---|---|
| Performance | Checkout p99 latency | < 200 ms at 1,000 rps | k6 load stage, threshold `p(99)<200`, fails CI on breach |
| Availability | Monthly uptime SLO | 99.95% (about 21 min budget) | SLO burn-rate alert on the request-success SLI |
| Scalability | Sustained write throughput | 5,000 orders/s at < 70% CPU | Soak test in staging at 2x peak |
| Security | Data at rest | AES-256, KMS-managed keys | Infra policy scan (Trivy/tfsec) blocks unencrypted volumes |
| Maintainability | Module cycles | 0 cyclic dependencies | import-linter / ArchUnit fitness function, blocking |

Each row ties the requirement to the architectural mechanism that satisfies it and the test or monitor that proves it; a row with an empty Verification column is not a requirement, it is a wish. The Verification column is where NFRs connect to `evolutionary_architecture_fitness_functions`.

## Trade-off analysis with ATAM

NFRs conflict: latency budgets fight cost, availability fights consistency, security fights interaction speed. Use the SEI ATAM method to make the conflict explicit rather than discovering it after build.

1. Build a utility tree: quality attributes -> refinements -> concrete scenarios, each ranked by (business importance, technical difficulty) as high/medium/low.
2. Map each architectural decision to the scenarios it affects.
3. Identify sensitivity points (a decision a single attribute is highly sensitive to), trade-off points (a decision that helps one attribute and hurts another), risks, and non-risks.
4. Record each trade-off point as an ADR consequence (`architectural_decision_records`) so the cost is on the record.

Worked trade-off point: introducing a read-through cache improves the performance scenario (p99) but creates a staleness window that degrades a consistency scenario. That tension, with the chosen tolerance stated as a number, belongs in the ADR consequences.

## Common pitfalls

- An NFR stated as an adjective ("fast", "highly available", "secure") with no number, which a reviewer rejects because there is nothing to test or sign off against.
- A number with no verification mechanism, so the target is aspirational and silently regresses; every NFR needs a test, monitor, or fitness function.
- Latency stated only as an average, hiding the tail; specify p95/p99, because the average passes while users at the tail suffer.
- Setting NFR numbers by guesswork instead of deriving them from business scenarios and budgets, producing thresholds teams rerun until green.
- Treating NFRs as a one-time document instead of fitness functions on the critical path, so they decay after launch.
- Listing every attribute at "high", which is not a prioritization; ATAM forces the ranking that makes design choices possible.

## Definition of done

- [ ] In-scope quality attributes are checked against ISO/IEC 25010; out-of-scope ones are explicitly recorded as not significant.
- [ ] Every significant NFR is a six-part quality-attribute scenario with a numeric response measure.
- [ ] Each NFR names the architectural mechanism that satisfies it and the test/monitor/fitness function that proves it.
- [ ] Latency NFRs specify percentiles (p95/p99), not averages, with the load they hold at.
- [ ] Conflicting attributes are reconciled via an ATAM utility tree, and each trade-off point is recorded as an ADR consequence.
- [ ] No NFR ships without a verification entry; unverifiable NFRs are removed or made measurable.
