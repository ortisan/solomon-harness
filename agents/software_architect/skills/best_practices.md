# Software Architect Best Practices

Purpose: a concrete standard for producing C4 diagrams, Architectural Decision Records, design contracts, and non-functional requirements that hold up under review and survive contact with implementation.

## When this skill applies

Use it whenever you define or change system structure: introducing a service, a database, an integration, a cross-cutting concern (auth, caching, messaging), or any decision that is expensive to reverse. If a change is local to one module and reversible in an afternoon, document it in code and a commit message, not in an ADR. Reserve architecture artifacts for decisions with system-wide blast radius.

## C4 model diagrams

C4 names four levels after four C's: Context, Containers, Components, Code. Model at these four zoom levels and stop there. Do not invent extra levels.

1. **Level 1 - System Context** — the system as one box, surrounded by users (personas) and external systems. Audience: everyone, including non-technical stakeholders. One per system.
2. **Level 2 - Container** — deployable/runnable units inside the system boundary: services, SPAs, mobile apps, databases, message brokers, serverless functions. Each container shows technology choice and the protocol of every link (HTTPS/JSON, gRPC, AMQP, JDBC). This is the most useful level; spend the most effort here.
3. **Level 3 - Component** — the major structural building blocks inside one container and their responsibilities. Draw it only for containers with real internal complexity; skip it for thin or generated ones.
4. **Level 4 - Code** — class/ER detail. Generate it from code (IDE, tooling) rather than drawing by hand; hand-drawn code diagrams rot within a sprint.

Rules that keep diagrams honest:

- Every element has a name, a type, and a one-line responsibility. Every relationship has a verb-phrase label and a direction ("Sends order events to", not a bare arrow).
- Every dependency arrow names its protocol and synchronicity (sync request/response vs async event). An unlabeled arrow is a defect.
- One diagram answers one question. If a Container diagram needs a legend longer than five entries, split it.
- Keep diagrams as text-based, version-controlled artifacts: **Structurizr DSL**, **Mermaid C4**, or **PlantUML with C4-PlantUML**. Diagrams live in the repo next to the code and change in the same PR. Binary exports from drawing tools are not the source of truth.
- Include a legend, a "last updated" date, and the author. A diagram with no date is assumed stale.
- Notation discipline: solid line for synchronous calls, dashed for asynchronous/events; consistent shapes per element type across all diagrams.

Common pitfalls: mixing abstraction levels in one diagram (a class sitting next to a load balancer); drawing the org chart instead of the runtime; omitting the data stores; drawing the aspirational system without marking what does not exist yet. Mark planned elements explicitly (for example a "PLANNED" tag) so readers do not mistake intent for reality.

## Architectural Decision Records

One decision per ADR. Immutable once accepted. To change a decision, write a new ADR and set the old one's status to `Superseded by ADR-NNNN`; never edit an accepted record's substance.

Store ADRs as `docs/adr/NNNN-kebab-title.md`, numbered monotonically, starting at 0001. Use MADR or Nygard format. Minimum sections:

- **Status** — Proposed, Accepted, Deprecated, or Superseded (with the link).
- **Context** — the forces in play: requirements, constraints, NFR targets, deadlines, team skills. State facts, not the choice.
- **Decision** — the position taken, in active voice: "We will use ...".
- **Consequences** — what becomes easier and what becomes harder. The trade-off and the cost are mandatory; an ADR with only upsides is incomplete and signals you have not found the real cost yet.
- **Options considered** — at least two alternatives with the reason each was rejected. A single-option ADR is a rationalization, not a decision.

Write an ADR when the decision affects structure, is costly to reverse, or future maintainers will ask "why on earth did they do this". Examples: choosing a persistence engine, sync vs async integration, monolith vs service split, an auth scheme, a public API contract style. Skip ADRs for naming conventions, library micro-choices, and anything trivially reversible.

Pitfalls: writing the ADR after the code ships (decision theater); burying the real reason ("the vendor sponsored us") behind a technical rationalization; letting status fields go stale so nobody can tell which records are live.

## Design contracts as component boundaries

This is the role's primary output. A design contract is the enforceable agreement at a component boundary, independent of implementation.

For each boundary specify:

- **Interface signature** — operations, typed inputs and outputs, error/exception set. No leaking of internal types across the boundary.
- **Preconditions** — what the caller must guarantee (validated inputs, required state, auth context).
- **Postconditions** — what the component guarantees on success.
- **Invariants** — what stays true before and after every call.
- **Error contract** — the closed set of failure modes and how each is signaled. Callers must be able to enumerate what can go wrong.
- **Idempotency and side effects** — is the operation safe to retry; what state mutates.
- **Quality-of-service terms** — latency budget, throughput limit, payload size cap, rate limits, consistency guarantee (strong vs eventual), versioning/compatibility policy.

Align with the project's Hexagonal Architecture: the Core Domain depends only on Ports expressed in domain primitives and domain models. Driving (input) adapters call Incoming Ports; Driven (output) adapters implement Outgoing Ports. No transport-specific or database-specific types appear in a Port. Changing database, swapping REST for gRPC, or replacing a broker must require only a new adapter, with zero Core Domain edits. A contract that mentions `HttpRequest`, an ORM entity, or a JSON field is leaking and must be rewritten in domain terms.

Encode contracts in machine-checkable form wherever possible: OpenAPI/JSON Schema for HTTP, Protobuf/`.proto` for gRPC, AsyncAPI for events, plus consumer-driven contract tests (Pact-style) so producer and consumer cannot drift silently. A contract no test exercises is a comment.

Pitfalls: chatty interfaces that force N calls for one use case; boundaries that share mutable state instead of passing data; "just add a field" changes that break consumers because no compatibility policy was stated; treating a database table as an integration contract between services.

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

## SOLID and structural discipline

Apply SOLID at the boundaries you design, and name the principle when you cite it in review:

- **SRP** — one reason to change per module. If a class changes for both a pricing rule and a report format, split it.
- **OCP** — extend behavior through new implementations of an abstraction, not by editing stable code. Watch for `if type == ...` ladders; they signal a missing polymorphic seam.
- **LSP** — a subtype must honor the supertype's contract: no strengthened preconditions, no weakened postconditions, no surprise exceptions. A subclass that throws `NotSupported` violates it.
- **ISP** — many focused client-specific interfaces over one fat interface. No client should depend on methods it never calls.
- **DIP** — high-level policy depends on abstractions; details depend on those same abstractions. This is exactly the Ports and Adapters rule above: the Core Domain owns the Port interfaces and the adapters depend on them.

Guard structure with fitness functions in CI: dependency-direction checks (ArchUnit for the JVM, import-linter for Python) that fail the build when an adapter is imported by the Core Domain, when a layer is skipped, or when a cyclic dependency appears. Architecture you cannot enforce automatically erodes by the next release.

## Mandatory project competencies to honor in any design

These come from the project rules and bind every artifact you produce.

- **TDD is mandatory.** Design for testability: depend on interfaces, allow injection at every boundary, keep the Core Domain free of I/O so it is unit-testable without infrastructure.
- **QA.** Mock all external API calls and services in tests so suites are isolated and deterministic. Every contract you define ships with consumer-driven contract tests. Cover backtesting logic and parameters explicitly where the system has them.
- **ML / DRL designs.** Enforce zero data leakage by construction (strict train/validation/test and walk-forward splits, no future information in features). Require cross-validation and out-of-sample evaluation in the design. Mandate guards before critical tensor ops: validate tensor shapes, and protect against division-by-zero and float overflow/underflow.
- **Quant strategy designs.** Any model hypothesis the architecture supports must state target Sharpe ratio (for example >= 1.5 net of costs), maximum drawdown limit (for example <= 20%), minimum profit factor (for example >= 1.3), latency and slippage constraints (for example sub-50 ms decision-to-order, slippage modeled per instrument), the dataset and features used, and the network/model architecture. No backtest result is valid without realistic transaction costs and slippage.
- **Security - STRIDE.** Run a STRIDE pass on every Container and trust boundary: Spoofing (authentication), Tampering (integrity/signing), Repudiation (audit logging), Information disclosure (encryption, least privilege), Denial of service (rate limiting, quotas, timeouts), Elevation of privilege (authorization, isolation). Record the threats and mitigations; an unmitigated high-severity threat blocks acceptance.
- **Preserve existing docstrings and comments** unrelated to the change.
- **Humanizer tone** in every artifact: direct, concise, senior-engineer prose. No emojis or icons.

## Definition of done

- [ ] Context and Container diagrams exist as version-controlled text (Structurizr/Mermaid/PlantUML), dated, with every arrow labeled by protocol and synchronicity.
- [ ] Component diagrams exist for every container with real internal complexity; code-level diagrams are generated, not hand-drawn.
- [ ] Each non-reversible decision has an ADR with Status, Context, Decision, Consequences (including the cost), and at least two options considered.
- [ ] Superseded ADRs are linked, not edited; no accepted ADR was altered in substance.
- [ ] Every component boundary has a written contract: signature, pre/postconditions, invariants, closed error set, idempotency, and QoS terms, expressed in domain types with no transport or persistence leakage.
- [ ] Contracts are encoded in a checkable schema (OpenAPI/Protobuf/AsyncAPI) and backed by consumer-driven contract tests.
- [ ] Every significant NFR is a six-part measurable scenario with a number, mapped to the mechanism that satisfies it and the SLI/test/dashboard that proves it.
- [ ] SOLID reviewed at each boundary; CI fitness functions enforce dependency direction and forbid cycles and layer violations.
- [ ] STRIDE pass completed on each trust boundary with mitigations recorded; no open high-severity threat.
- [ ] Role-specific guards present where relevant: TDD-friendly seams, mocked externals, ML leakage/shape/overflow guards, quant Sharpe/drawdown/profit-factor/latency/slippage targets stated.
- [ ] All artifacts pass the humanizer check: no emojis, no banned cliches, senior-engineer tone.
