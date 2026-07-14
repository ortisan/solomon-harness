# Spec 233: generate a house spec doc per issue via /solomon-issue

- Issue: #233 · Status: ready
- Date: 2026-07-14 · Author: product_owner

## Context

S1 of umbrella #221 (spec-driven issue docs and automatic ADR capture).
Elicitation: skipped — the demand arrived fully specified by the refined
umbrella and its refine-to-start handoff contract.

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
4. Spec generation adds less than 2 s to `/solomon-issue` (umbrella DoR).

## Acceptance Criteria

Scenario: a new issue generates a spec-driven document (sections present,
Traceability cites #N, spec-lint exits 0). Scenario: a minimal issue still
yields a valid spec (headings present, `TBD (refine)` placeholders, lint 0).
Scenario: spec-lint rejects a malformed spec (exit 1 naming the missing
section or the filename defect). Full Gherkin in issue #233.

## Design Constraints

No runtime package code: the convention is docs + a standalone validator +
prompt wiring, pinned by content gates (the ADR-0020/#223 enforcement
pattern). Issue-derived text reaches the spec only through the Write tool —
never a shell string (the elicitation gate's discipline). The convention's
decision record lands with S2a (#234), which owns the docs/adr → docs/adrs
rename.

## Out of Scope

ADR migration and automatic capture (S2a #234, S2b #235); install-time wiring
(S3 #236); specs for bugs, chores, or ideas; backfilling historical issues.

## Traceability

- Issue: #233 (parent #221)
- ADR: none in this slice — recorded with S2a's migration ADR by design
- PR: opened by this branch (feature/spec-per-issue-docs)
