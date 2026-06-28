# Architecture Review Gate

The architecture review gate is the explicit checkpoint where a design or a delivered change is judged against the architecture's binding constraints and either passes or is sent back, with the verdict recorded so the decision is auditable and not re-litigated. Treat it as a gate, not a conversation: a fixed checklist, a severity rubric, and a single go/no-go outcome persisted with `save_decision`. The same checklist runs at two points in the lifecycle — before Execution to admit a proposed design, and at Code Review (step 5) to admit a delivered change against that design.

## Entry criteria and inputs

Do not open the gate until the work is reviewable. Reject as not-ready (this is itself a no-go) when any input is missing:

- The artifact under review: the design (C4 Context + Container at minimum, see `c4_model_diagrams`) or the change (diff, PR) plus the design it claims to implement.
- The NFR scenarios the work must satisfy, each with a number and an SLI (see `non_functional_requirements`).
- The design contracts for every interface the work touches (see `design_contracts_as_component_boundaries`).
- The relevant ADRs and their status. If the change contradicts an Accepted ADR, the gate blocks until a superseding ADR exists (see `architectural_decision_records`).
- The fitness-function suite and its latest run (see `evolutionary_architecture_fitness_functions`). A gate with no automated fitness evidence is opinion, not a gate.

Pull prior context first: `get_open_issues` for known architectural debt against this component, `get_decision` for the last gate verdict on it, and `get_latest_activity` to see what changed since.

## The checklist

Run all five dimensions. Each finding gets a severity: **blocker** (gate cannot pass), **major** (pass only as conditional go with a logged, owned follow-up), **minor** (note, does not affect the verdict).

### 1. Non-functional requirements

- Every in-scope NFR is a measurable scenario (source, stimulus, response, response measure), not an adjective. A vague NFR is a blocker because it cannot be reviewed.
- Each NFR is tied to a concrete mechanism in the design and to the test or dashboard that proves it. An NFR with no backing SLI is a major finding.
- The change does not silently regress an existing NFR (latency, error budget, cost-per-request). If a fitness function for that NFR exists, confirm it still passes; if none exists, that gap is a major finding.

### 2. Design contracts and boundaries

- Every interface the work crosses has an explicit contract: inputs, outputs, error semantics, idempotency, and invariants. New public surface with no contract is a blocker.
- No change to an existing contract's observable behavior without a versioning or deprecation path. Silent breaking changes are a blocker.
- Dependencies point inward toward stable abstractions; no new dependency from a stable module onto a volatile one. Circular dependencies between components are a blocker.

### 3. SOLID and structural discipline

- Name the principle when you cite it (see `solid_and_structural_discipline`). "This feels wrong" is not a review finding.
- Single responsibility at the boundary: a component has one reason to change. A module that owns persistence, transport, and policy at once is a major finding.
- Check the Dependency Inversion at integration points and Interface Segregation on fat interfaces. New god-objects or leaky abstractions are major.

### 4. Security — STRIDE

Walk the data-flow diagram and check each threat category against every trust boundary crossing:

- **Spoofing** — authn at every boundary; no implicit trust between services. Delegate the deep authn/authz review to the `auth_engineer` and `security` agents; the gate confirms the boundary exists and is specified.
- **Tampering** — integrity of data in transit (TLS) and at rest; input validation at the boundary.
- **Repudiation** — security-relevant actions are logged with actor and time.
- **Information disclosure** — data classification honored; no secrets in logs, config, or error responses; least-privilege data access.
- **Denial of service** — rate limits, timeouts, and the resilience patterns (`resilience_patterns`) guard each integration point.
- **Elevation of privilege** — authz checked server-side at every boundary, not just in the client.

Any unmitigated threat at a boundary handling regulated or high-value data is a blocker. Missing mitigation on a low-value path is a major finding with a logged issue.

### 5. Fitness functions

- The architecturally significant characteristics (cyclic-dependency = 0, layer-violation = 0, coupling thresholds, p99 budget, bundle/size ceilings) each have an automated fitness function that runs in CI. See `evolutionary_architecture_fitness_functions` for authoring them.
- The suite is green on the artifact under review. A red fitness function is a blocker; the gate does not override the machine check by hand.
- New architectural characteristics introduced by this change have new fitness functions, or a logged issue to add them before merge. Adding a characteristic with no guard is a major finding.

## Verdict and recording

The gate produces exactly one of three outcomes:

- **Go** — zero blockers and zero open majors. The work proceeds.
- **Conditional go** — zero blockers, but one or more majors. Proceed only after each major is filed with `log_issue` and assigned an owner and a milestone (`create_milestone` if none fits). The verdict records the issue IDs as conditions.
- **No-go** — one or more blockers. The work returns to its author. Each blocker is filed with `log_issue` referencing the exact artifact and checklist item.

Record the verdict with `save_decision` so it is durable and queryable, mirroring the ADR shape:

```python
save_decision(
    title="Gate: payments-service async refactor",
    status="conditional-go",            # go | conditional-go | no-go
    context="Reviewed Container diagram + PR #214 against NFR set v3 and fitness suite run 88.",
    decision="Proceed. Async write path admitted; SOLID and contract checks pass; fitness suite green.",
    consequences="Open majors: missing p99 fitness function (#231), no DoS guard on webhook ingress (#232).",
    rationale="Zero blockers; two majors filed with owners and milestone M-09.",
)
```

Then `log_handoff` to the next stage: to the `software_engineer` for a conditional go (carrying the issue IDs), or back to the design author for a no-go (carrying the blocker IDs). Close the gate with `save_session` capturing what was reviewed, the verdict, and the linked decision and issue IDs, so the next reviewer starts from `get_decision` and `get_session` instead of re-deriving context.

A gate verdict is immutable like an ADR. To reverse it, run the gate again and write a new decision that supersedes the old one; never edit a recorded verdict.

## Common pitfalls

- Running the gate as a discussion with no recorded verdict, so the same objection resurfaces every sprint. Persist with `save_decision` or it did not happen.
- Passing on green fitness functions alone while skipping the NFR, contract, and STRIDE dimensions. The automated suite covers structure, not intent.
- Overriding a red fitness function "just this once" by hand. That defeats the gate; fix the code or write a superseding ADR that changes the threshold.
- Conditional go with majors that have no issue ID, owner, or milestone. An unowned "we'll fix it later" is a silent no-go that ships debt.
- Reviewing a change with no link to the design it implements, so contract drift is invisible. Demand the design as an input.
- Treating "no blockers" as "good architecture". The gate is a floor, not a ceiling; minor findings still get logged.
- Letting the gate become a bottleneck on one person. Encode every objective check as a fitness function so the human gate only judges what machines cannot.
- Doing the security pass as a checkbox instead of walking each trust boundary against all six STRIDE categories.

## Definition of done

- [ ] Entry criteria met: artifact, NFR scenarios, design contracts, relevant ADRs, and a fresh fitness-suite run are all present, with prior context pulled via `get_open_issues` and `get_decision`.
- [ ] All five dimensions reviewed — NFRs, contracts, SOLID, STRIDE, fitness functions — with each finding tagged blocker, major, or minor.
- [ ] Every blocker and major filed with `log_issue`, each carrying an owner and a milestone; the fitness suite is green or its gaps are logged.
- [ ] Exactly one verdict (go, conditional-go, no-go) recorded with `save_decision` in ADR shape, listing the condition issue IDs for a conditional go.
- [ ] Handoff to the next stage logged with `log_handoff` and the gate session closed with `save_session`, both referencing the decision and issue IDs.
- [ ] No Accepted ADR is contradicted without a superseding ADR; the verdict is treated as immutable and re-run rather than edited to reverse.
