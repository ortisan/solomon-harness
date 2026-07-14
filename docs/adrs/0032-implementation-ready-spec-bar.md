# ADR-0032: Implementation-ready spec bar and the discovered-problem protocol

- Status: accepted
- Date: 2026-07-14
- Deciders: software_architect, product_owner (maintainer directive 2026-07-14)
- Issue: #280 (maintainer directive 2026-07-14)

## Context and problem statement

Two recurring failures degraded the delivery loop. First, issue specs were too
thin for an implementing model to act on: an issue stated the product intent
but not where the change lands, the current versus expected behavior, the
approach, or how to prove it works, so the model guessed. Second, a model that
discovered a side-problem while implementing an issue appended it as a comment
on the issue being worked, polluting that thread and losing the discovery as
trackable work. Both are amendments to the spec convention recorded in
ADR-0028, which established `docs/specs/` with seven mandated sections.

## Decision drivers

- A refined (Ready) issue must be implementable without asking anything.
- Enforcement must be mechanical, not prose the model can skip (the standing
  "enforcement is prose, not mechanism" weakness).
- Reuse the existing spec machinery; ADR-0028 restricts this convention to
  docs, a standalone validator, and prompt wiring — no runtime package code.
- Discovered work must stay independently trackable, refinable, and claimable.

## Considered options

- A new package-level issue-body validator (`check_issue_ready`) called by the
  prompts.
- Extend the existing `docs/specs` convention: two new spec sections plus a
  status-gated `spec-lint` rule.
- Prose-only guidance in the command prompts.

## Decision outcome

Chosen option "extend the existing spec convention", because it meets the
mechanical-enforcement driver while honoring ADR-0028's no-runtime-code
constraint. The spec template gains two sections — **Implementation Pointers**
(exact `file:line` targets, current versus expected behavior, the concrete
approach) and **Verification** (the exact command that proves the change) —
raising the mandated set from seven to nine. `scripts/spec-lint.py` requires
both and, once a spec is `Status: ready` or `implemented`, rejects any section
still holding a `TBD (refine)` line: refinement resolves every placeholder, so
Ready means implementable. `/solomon-issue` pre-fills the sections (placeholders
allowed at `draft`); `/solomon-refine` resolves them and flips the spec to
`ready` behind the lint gate. Bugs, which have no spec, carry the same detail
in the issue body (suspected `file:line`, verification command).

The discovered-problem protocol is recorded for `/solomon-start` and
`/solomon-loop`: a problem or better solution found mid-implementation becomes a
NEW issue linked `Refs #<parent>`, never a comment on the in-flight issue and
never a silent widening past the PLAN.md target-files fence; a blocking
discovery is surfaced to the human as enumerated options.

### Consequences

- Positive: an implementing model reads a spec that names where, what, how, and
  how to verify; discovered work is tracked as first-class issues; the Ready
  gate is machine-checked in CI.
- Negative: refinement does more work (resolve real `file:line` pointers before
  Ready); a spec marked `ready` with a lingering placeholder now fails CI.
- Follow-ups: amends ADR-0028 (seven sections to nine); bugs enforce the bar by
  prose only; backfilling historical specs and issues is out of scope.

## More information

Amends ADR-0028. Realizes the maintainer directive of 2026-07-14. Enforced by
`scripts/spec-lint.py` (tests in `tests/test_spec_lint.py`) and wired into
`/solomon-issue`, `/solomon-refine`, `/solomon-start`, `/solomon-loop`,
`/solomon-bug`, and both `.github/ISSUE_TEMPLATE` forms. Recorded in project
memory via `save_decision`.
