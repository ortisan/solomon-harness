# Spec: <issue title>

- Issue: #<issue number>
- Status: draft

_Status starts at `draft` when the spec is generated; update it by hand as
the spec progresses to `refined` (acceptance criteria locked in) or
`implemented` (the linked PR merged)._

## Context

The issue's user story, plus why this matters now: the surrounding system and
any prior decisions this builds on.

## Problem

The specific gap or pain point this issue closes, stated without a proposed
fix.

## Requirements

What the solution must do, in scope, one bullet per capability. This is the
"in scope" half of the issue's Scope section.

## Acceptance Criteria

Gherkin `Scenario / Given / When / Then`, covering the happy path, boundary
values, and at least one failure path. Every `Then` observable and specific.

## Design Constraints

Non-functional or structural limits the implementation must respect:
performance, security, compatibility, dependencies already decided (from the
issue's Definition of Ready).

## Out of Scope

What this issue deliberately does not cover, and why, so a later reader does
not re-litigate an already-made boundary decision.

## Traceability

`Issue: #<N>` plus either a related ADR (referenced by number and title, never
by a hardcoded path — ADR directories are project-specific and can move) or
the literal `No related ADR` when no architecturally significant decision
backs this change.
