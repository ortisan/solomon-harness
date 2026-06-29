# Architectural Decision Records

Capture one architecturally significant decision per ADR as an immutable, numbered, version-controlled record, so the reasoning behind a structural choice — and the options it rejected — survives the people who made it.

## What makes a decision ADR-worthy

Write an ADR when a decision is architecturally significant: it affects structure, is costly to reverse, or a future maintainer will ask "why is it like this". The triage is the blast-radius and cost-of-reversal test in the engagement model (`when_this_skill_applies`). Typical ADR-worthy choices: a persistence engine, sync versus async integration, monolith versus service split, an auth scheme, a public API contract style, a build/deploy topology. Skip ADRs for naming conventions, library micro-choices, and anything reversible in an afternoon — recording those is noise that buries the decisions that matter.

A decision needs at least two genuine options to warrant an ADR. A record with one option is a rationalization dressed up as a choice.

## Formats: Nygard and MADR

Two formats dominate; both are short Markdown and both work.

- Nygard (the original) — Title, Status, Context, Decision, Consequences. Minimal and fast; good for small teams and a high decision cadence.
- MADR (Markdown Any Decision Records) 4.0 — adds Decision Drivers, Considered Options with per-option pros and cons, and a Decision Outcome with explicit consequences. Better when the trade-off is non-obvious or several people must be convinced.

This project standardizes on the MADR shape, because it forces the options and the cost onto the page and because the project-memory mirror (`architecture_decisions_in_project_memory`) maps onto its sections. Whichever you pick, four things are mandatory: a Status, the Context stated as forces (not the choice), at least two Considered Options with the reason each lost, and Consequences that name at least one cost. An ADR with only upsides is incomplete — you have not found the real cost yet.

## Status lifecycle

An ADR's status is the one mutable field in an otherwise immutable record.

```
Proposed ──accept──> Accepted ──deprecate──> Deprecated
                         │
                         └──supersede──> Superseded by ADR-NNNN
```

- Proposed — under review; the decision is not yet binding.
- Accepted — binding; the architecture review gate (`architecture_review_gate`) treats it as a constraint.
- Deprecated — no longer recommended, with no direct replacement.
- Superseded by ADR-NNNN — replaced by a newer decision; the link is mandatory.

To change an accepted decision you never edit its substance; you write a new ADR and set the old one's status to `Superseded by ADR-NNNN`. The wrong-in-hindsight decision and its reasoning stay visible, because that is the audit value of the log.

## Storage and numbering

Store ADRs as `docs/adr/NNNN-kebab-title.md`, numbered monotonically from 0001, one decision per file. They live in the repo and change in the same pull request as the code they govern, so the decision is reviewed alongside the diff. Keep an index (`docs/adr/README.md`, or the memory `adr-index` from the sibling skill) so a reader finds the live status without opening every file.

## Worked ADR skeleton (MADR)

```markdown
# ADR-0007: Adopt SurrealDB as the primary memory store

- Status: Accepted
- Date: 2026-06-28
- Deciders: software_architect

## Context and problem statement
The harness needs graph + document data in one store with sub-50 ms reads,
runnable as a single local container. Which engine?

## Decision drivers
- One store for graph traversal and document records
- p99 read < 50 ms on a developer laptop
- Single-container local operation; SQLite fallback when Docker is absent

## Considered options
1. SurrealDB primary, SQLite fallback
2. PostgreSQL + JSONB
3. Neo4j

## Decision outcome
Chosen: option 1, SurrealDB primary with SQLite fallback, because it covers
graph and document in one engine and meets the latency target.

### Consequences
- Good: one store, one query language, simple local setup.
- Bad: operational dependency on a young engine; the team must build expertise.
- Neutral: the SQLite fallback path must be maintained and tested.

### Pros and cons of the options
- PostgreSQL + JSONB — mature and known; rejected for weak native graph traversal.
- Neo4j — strong graph; rejected for no first-class document model and licensing.
```

The decision does not stop at the file. Mirror it into project memory and link it to the issue that drove it and the commit that implements it per `architecture_decisions_in_project_memory`; that sibling skill owns the `save_decision` encoding and the supersession bookkeeping, so it is not repeated here.

## Common pitfalls

- Writing the ADR after the code ships (decision theater); a reviewer rejects it because it documents an outcome rather than guiding a choice.
- A single-option ADR, which is a rationalization; at least two real options with the reason each lost are required.
- Consequences listing only benefits, which means the real cost was never found; the trade-off is mandatory.
- Stating the Decision inside the Context section, so the record reads as advocacy; Context is facts, Decision is the position.
- Editing an accepted ADR's substance instead of superseding it, which destroys the audit trail the log exists to provide.
- Stale Status fields, so nobody can tell a live decision from a dead one; keep the status and the supersession link current.
- ADRs stored outside the repo (wiki, doc tool) where they are not reviewed with the diff and drift from the code.

## Definition of done

- [ ] The decision is architecturally significant per the triage test; trivial or reversible choices are not given ADRs.
- [ ] The record uses the MADR shape with Status, Context-as-forces, at least two Considered Options with rejection reasons, and Consequences naming at least one cost.
- [ ] Stored as `docs/adr/NNNN-kebab-title.md`, numbered monotonically, one decision per file, in the same PR as the change.
- [ ] Status reflects the lifecycle; superseding writes a new ADR and links both directions, never editing accepted substance.
- [ ] An index lets a reader find current status without opening every file.
- [ ] The decision is mirrored to project memory and linked to its issue and commit per `architecture_decisions_in_project_memory`.
