# ADR-0003: Capability-broker / self-extending-fleet model

- Status: accepted
- Date: 2026-06-29
- Deciders: software_architect, product_owner, practice_curator, software_engineer, security
- Issue: #46 (slice A of epic #43)

> Numbering note: 0003 is the next free ADR on `main` at authoring time (0001 worktree,
> 0002 memory-resilience). A concurrent cockpit (#44) branch is also producing an ADR; if a
> different 0003 lands on `main` first, this one is renumbered to the next free value at merge.

## Context and problem statement

The fleet is statically wired: `solomon_harness/agent_selection.py` enables a fixed catalog from
detected stack signals, and nothing takes a free-text *demand* and decides which existing agent
should serve it — or reports, in a structured way, that none can. Epic #43 wants
`practice_curator` to become a capability broker that routes a demand, adapts a missing skill
(#47), or creates a new agent (#48/#49), always as a human-reviewed change. Before any of that,
the fleet needs one deterministic, testable decision point and a contract for its verdict, plus a
committed stance on how the broker intercepts demands and how it treats external sources. This ADR
fixes that model; slice A (#46) implements only its read-only routing/gap core.

## Decision drivers

- Determinism and testability: routing must be unit-testable without a network or a model.
- A stable verdict contract the later slices (adapt/create) build on without rework.
- Safety: the self-extending behavior must never enter unreviewed code or run unbounded.
- Simplicity (Karpathy): no new ML dependency; reuse existing discovery.

## Considered options

- Match engine: host LLM via an injected port vs an embedded semantic/ML classifier.
- Interception point: orchestration-time (resolve before the loop runs) vs runtime hot-swap.
- Verdict shape: a bare agent name vs a typed route/gap verdict carrying next-action hints.
- Autonomy: propose-and-approve (reviewed PR) vs autonomous application.
- Trust: allowlisted, pinned, never-executed external sources vs open fetch.

## Decision outcome

1. **Verdict contract.** `route(demand, matcher)` returns either a **route** verdict
   (`agent`, `rationale`, `alternatives`) or a **gap** verdict (`missing_capability`,
   `nearest_agent`, `suggested_action` in {`adapt_skill`, `create_agent`}, `rationale`). The gap
   verdict pre-wires the adapt (#47) and create (#48/#49) slices.
2. **Match via an injected port.** The demand→agent match is supplied by a matcher port — the host
   LLM in production, a deterministic stub in tests. The core owns read-only catalog loading
   (the `agents/AGENTS.md` index + each role file, reusing `agent_selection._discover_agents`),
   verdict construction, and invariant enforcement only. No embedded ML model; an ML matcher would
   need its own ADR.
3. **Orchestration-time interception.** Capability is resolved before the delivery loop runs; a
   newly created or adapted agent is invocable only after `compile` + session restart. No runtime
   hot-swap.
4. **Human-reviewed autonomy.** The broker may at most open a draft PR (adapt/create) and never
   merges; every acquisition lands via #20's reviewed-PR path (one agent per PR), matching
   `practice_curator`'s "reviewed updates" identity. Slice A is read-only — it mutates nothing.
5. **External-source trust boundary (applies from slice B).** Sources are allowlisted in
   `skill-sources.json`, fetches are pinned, fetched content is untrusted data that is never
   executed; the `security` agent reviews every adapt/create PR.

Chosen because an injected matcher keeps the core deterministic and TDD-able with no new
dependency; a typed verdict gives the later slices a stable contract; orchestration-time
interception matches how the harness already binds capability (file discovery + compile); and the
reviewed-PR autonomy ceiling keeps a self-extending fleet safe.

### Consequences

- Positive: routing/gap detection becomes a deterministic, reviewable contract; the riskier
  acquisition slices build on a fixed shape; no ML/network enters the foundational slice.
- Negative: the host LLM is responsible for match quality (mitigated by advisory verdicts +
  enumerated alternatives for confirmation); a new agent needs a session restart to become active.
- Follow-ups: the external-source security surface (SSRF, prompt-injection-from-fetched-content)
  is enumerated and enforced when slices B–D land; the `agent_builder` meta-agent (#49) owns
  construction.

## More information

Implemented by `solomon_harness/capability_router.py` (slice A, #46) and the
`agents/practice_curator/skills/capability_broker.md` skill. Recorded via `save_decision`. The
acquisition slices (#47/#48/#49) and the lifecycle wiring (#50, reusing #20) extend this model.
