# Spec 233: generate a house spec doc per issue via /solomon-issue

- Issue: #233 · Status: ready
- Date: 2026-07-14 · Author: product_owner

## Context

S1 of umbrella #221 (spec-driven issue docs and automatic ADR capture).
Created by the #221 slicing gate from the refined umbrella and its
refine-to-start handoff contract — not through the interactive elicitation
flow, so no elicitation trace exists for this issue.

## Problem

An issue's intent lives only in its GitHub description; nothing generates a
durable, structured specification for the issue itself, so agents and humans
reconstruct intent from scattered issue text.

## Requirements

1. A house template at `docs/specs/0000-spec-template.md` with the seven
   mandated sections, plus a convention README with the filename rule.
2. `scripts/spec-lint.py` enforces the convention (exit 0/1, defects named)
   and runs in the CI validators job.
3. `/solomon-issue` generates `docs/specs/<N>-<slug>.md` at creation time in
   both host mirrors, via the Write tool, linted before done.
4. No runtime package code: docs, a standalone validator, and prompt wiring
   only.

## Acceptance Criteria

```gherkin
Scenario: A new issue generates a spec-driven document
  Given the house spec template at docs/specs/0000-spec-template.md
  When an author runs /solomon-issue and issue #N is created
  Then a file exists at docs/specs/<N>-<slug>.md
  And it contains the sections Context, Problem, Requirements, Acceptance Criteria,
      Design Constraints, Out of Scope, and Traceability
  And the Traceability section links issue #N and any related ADR
  And scripts/spec-lint.py exits 0 for that file

Scenario: Boundary — a minimal issue still yields a valid spec
  Given an issue created with only a title and a one-line body
  When the spec document is generated
  Then all required sections are present as headings
  And any empty section carries an explicit "TBD (refine)" placeholder
  And scripts/spec-lint.py exits 0

Scenario: Failure path — spec-lint rejects a malformed spec
  Given a spec file missing the Traceability section or misnamed <N>-<slug>.md
  When scripts/spec-lint.py runs
  Then it exits 1 and names the missing section or the filename defect
```

## Design Constraints

No runtime package code: the convention is docs + a standalone validator +
prompt wiring, pinned by content gates (the ADR-0025/#222 enforcement
pattern). Issue-derived text reaches the spec only through the Write tool —
never a shell string (the elicitation gate's discipline). The convention's
decision record lands with S2a (#234), which owns the docs/adrs → docs/adrs
rename; S3 (#236) is gated on that record landing first.

## Out of Scope

ADR migration and automatic capture (S2a #234, S2b #235); install-time wiring
(S3 #236); specs for bugs, chores, or ideas; backfilling historical issues.

## Traceability

- Issue: #233 (parent #221)
- ADR: none in this slice — recorded with S2a's (#234) migration ADR by design
- PR: #237
