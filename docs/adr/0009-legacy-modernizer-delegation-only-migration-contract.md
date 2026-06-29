# ADR-0009: legacy_modernizer — a delegation-only, one-step-per-run migration-planning contract

- Status: Accepted
- Date: 2026-06-28
- Deciders: software_architect, product_owner, scrum_master (NFR-bar owners security, observability, qa as content confirmers)
- Issue: #70 (first slice of modernization epic #72; constrains follow-ups #74, #75)

## Context and problem statement

When solomon-harness is installed onto an existing legacy codebase, no fleet member
owns the cross-cutting question a maintainer faces: "given everything non-conformant
here, what is the safe, ordered sequence of small changes to reach the house standards
(hexagonal, OpenTelemetry, secure-by-default, TDD), and who executes each one?" Without
an owner of that sequence, adopters either attempt a big-bang rewrite (high blast radius,
long-lived branch, stalled delivery) or modernize ad hoc, leaving structural debt
untracked. This recurs on every legacy adoption.

#70 introduces the `legacy_modernizer` specialist. The architecturally significant part
is not the agent's files but the cross-cutting **design contract** its planning skill
establishes: a boundary between a roadmap-owner that plans and sequences, and the
specialists that execute. That boundary is a constraint future work must honor — the
deferred standing scan-legacy cadence (#74) and install-time auto-enrolment (#75) build
runtime behavior on top of it. This slice ships only the definition, the contract text,
and registration (no new runtime Python; the cadence and auto-enrolment are deferred), so
the decision is about whether to record the boundary now, at the point it is established,
or later, at the point it is first executed.

## Decision drivers

- Bounded blast radius: a modernization of a real legacy codebase must never become a
  long-lived big-bang branch.
- Reviewability and human control: every change must terminate at the unchanged
  `/solomon-review` human gate; the agent must propose no merge and no release.
- Separation of concerns: planning/sequencing (one owner) must be cleanly separated from
  execution (the specialist who owns each standard), so each step is verifiable by its
  owner against a known NFR bar.
- Conformance of downstream slices: #74 (cadence) and #75 (auto-enrolment) must inherit a
  single recorded set of invariants rather than re-deriving them independently.
- Consistency with the existing loop contract: termination and the human gate must mirror
  `/solomon-scan-arch` and `/solomon-scan-dedup`, not introduce a new autonomy model.
- Testability now: this slice can assert only statically checkable facts (files,
  registration, compile output, grep-able contract text), so the contract must be
  expressible as such, with no assertion depending on host-LLM runtime output.

## Considered options

- Agent role: A1 an "executor" legacy_modernizer that both plans and writes refactor diffs;
  A2 a roadmap-OWNER that authors no source-refactor diff and DELEGATES all execution.
- Step granularity / PR shape: B1 a multi-step migration PR (several steps in one branch);
  B2 one bounded step per run, terminating at a single draft PR, never big-bang.
- Delegate set: C1 an open/dynamic set (any agent the planner deems fit); C2 a closed,
  fixed set of exactly eight specialists, with out-of-set owners held or flagged.
- When to record the ADR: D1 defer it to the runtime slice (#74/#75); D2 record the
  contract now, in the slice that establishes it.

## Decision outcome

Chosen A2 + B2 + C2 + D2, expressed as the migration-planning contract below.

- **A2 over A1.** An executor that writes diffs collapses the planning/execution boundary,
  removes the per-standard owner's accountability, and re-creates the big-bang and
  auto-merge risk the harness explicitly forbids. A delegation-only owner keeps each step
  verifiable by the specialist who owns the standard and keeps merge/release permanently
  human-gated; execution belongs to the delegates behind `/solomon-review`.
- **B2 over B1.** One bounded step per run caps blast radius and keeps each draft PR
  independently reviewable; a multi-step PR reintroduces the long-lived branch and a review
  surface no single owner can verify.
- **C2 over C1.** A closed eight-specialist set makes "who executes each step" deterministic
  and grep-able, and makes an out-of-set requirement an explicit held/flagged signal rather
  than a silent mis-assignment to an unknown or empty delegate.
- **D2 over D1.** The architectural artifact is the contract text itself, authored in THIS
  slice. Recording the boundary now (Status: Proposed, a human accepts at review) gives the
  downstream runtime slices a reviewed constraint to be checked against, consistent with
  ADR-0001 recording the `/solomon-start` contract at the point it was established, not the
  point it was first executed. Deferring would freeze the contract text in this slice's
  skill while leaving its rationale and boundary unrecorded until #74.

The contract, stated as the invariants this decision fixes:

1. **Delegation-only boundary.** legacy_modernizer owns assessment, sequencing, and
   delegation; it authors no source-refactor diff. Each delegated step is recorded as a
   handoff via `log_handoff`, naming the executing delegate.
2. **Closed delegate set.** Exactly `{software_architect, software_engineer, security,
   observability, qa, dba, sre, documenter}`. A candidate step whose required owner falls
   outside the set is held or flagged, never assigned.
3. **Parsimony invariant.** A single run advances at most one bounded step (a named module
   or path, never the whole codebase), ordered dependency-/risk-first: secret removal
   (owner security) and a covering-test safety net (owner software_engineer/qa) precede any
   architecture refactor (owner software_architect) that depends on them.
4. **Human-gated termination.** The run terminates at a single `/solomon-review`-gated draft
   PR; it proposes no merge and no release at any autonomy level, and produces no
   multi-step or whole-repo big-bang PR, mirroring `/solomon-scan-arch` and
   `/solomon-scan-dedup`.
5. **Four owner-attributed per-step NFR exit criteria.** TDD red/green/refactor covering
   test (owner software_engineer/qa); secure-by-default from a STRIDE pass — no secrets in
   code, parameterized queries, input validation (owner security); OpenTelemetry on touched
   paths (owner observability); a hexagonal port/adapter boundary on the touched module
   (owner software_architect).

Scope of this decision: it governs the contract text and the registration of
legacy_modernizer as a first-class fleet member. It does NOT decide the cadence mechanics
(#74) or the selection-routing of auto-enrolment (#75); it constrains them.

### Consequences

- Positive: the boundary between planning and execution is explicit and recorded before any
  runtime slice builds on it; blast radius is bounded to one step; merge and release stay
  permanently human-gated; #74 and #75 inherit one reviewed set of invariants; the contract
  is grep-able and statically testable within this definition-only slice.
- Negative: a real modernization advances slowly, one step per run — a deliberate trade of
  throughput for safety; the closed delegate set excludes UI, auth, and loop-mechanics
  concerns, so multi-language and framework-specific execution is a deferred follow-up, not
  available now; the "always used" intent is only partly met here (registration and
  discoverability), with automatic invocation deferred to #75 — a known
  stakeholder-expectation gap (issue risk R-03).
- Follow-ups and constraints this places on downstream work:
  - #74 (standing scan-legacy dev stage and cadence) must wire the stage to honor invariants
    3 and 4: L2/L3 autonomy allowed, L1 denied, single-driver lock, terminating at
    `/solomon-review`, mirroring scan-arch/scan-dedup; it must introduce no path that
    advances more than one step or proposes a merge.
  - #75 (install-time auto-enrolment into `select_agents`) must preserve invariant 1: it may
    add legacy_modernizer to the core/selected set but must grant it no execution capability.
  - End-to-end auto-execution of refactor diffs is permanently excluded (violates invariant
    1); modernizing solomon-harness's own repository is excluded (that benchmarking belongs
    to `practice_curator`, #16/#43).

## More information

Driven by #70, the first vertical slice of modernization epic #72. The contract text lives
in the planning skill under `agents/legacy_modernizer/skills/` and the role boundary in
`agents/legacy_modernizer/agents/legacy_modernizer.md`; registration is the
`REQUIRED_KEYWORDS` key in `scripts/validate-agents.py`, the `agents/AGENTS.md` specialist
index line, and the compiled `.claude/agents/legacy_modernizer.md`. The termination and
human-gate behavior mirror the loop contract of `/solomon-scan-arch` and
`/solomon-scan-dedup`. Status is proposed; a human accepts it at `/solomon-review`, at which
point the orchestrator records it in project memory via `save_decision` and backfills
`commit_sha`.
