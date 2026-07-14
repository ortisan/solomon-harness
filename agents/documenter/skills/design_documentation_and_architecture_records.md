---
name: design-documentation-and-architecture-records
description: Governs recording architectural decisions and system designs - MADR-style ADRs with named constraints and per-option rejection reasoning, C4 diagrams drawn only at the level that earns its keep, and design docs stating non-goals. Use when writing or reviewing an ADR, a C4 diagram, or a design doc.
---

# Design Documentation and Architecture Records

This skill governs how architectural decisions and system designs are recorded: Architecture Decision Records (ADRs) in MADR style, C4 diagrams drawn only at the levels that earn their keep, and design docs that state non-goals and rejected options. The stance: a decision that is not recorded with its context and consequences will be re-litigated, and a diagram that disagrees with the code is worse than no diagram.

## ADRs: one decision per record

Record every architecturally significant decision as one ADR in `docs/adr/`, numbered sequentially, using the MADR-style template at `docs/adr/0000-adr-template.md`. The required anatomy:

- **Header**: status (proposed / accepted / superseded by ADR-XXXX), date, deciders, and the tracking issue.
- **Context and problem statement**: the forces at play, named explicitly. Hard constraints get identifiers (ADR-0010 names C1 "the host tool is the model loop" and C5 "dual host") so the outcome section can prove it satisfies each one.
- **Decision drivers**: the quality attributes and constraints that discriminate between options.
- **Considered options**: every option genuinely on the table, including "do nothing".
- **Decision outcome**: the chosen option, why it wins against the drivers, and each rejected option with the specific reason it loses. "Rejected: no auditable holder, no portable staleness story" survives review; "rejected: worse" does not.
- **Consequences**: split into positive, negative, scope (what the decision deliberately does not change), and follow-ups with issue numbers. Negative consequences are mandatory; a decision with no cost was not a decision.

Use `docs/adr/0010-loop-single-driver-lock.md` as the house exemplar of all of the above. Write an ADR when a change swaps a framework, datastore, or major dependency; changes a public contract or data model; establishes a cross-cutting pattern; trades off a quality attribute; or is expensive to reverse (`docs/adr/README.md`). A bug fix or contract-preserving refactor does not need one.

Discipline around the records:

- Accepted ADRs are immutable. To change course, write a new ADR and set the old one's status to `superseded by ADR-XXXX`; the history is the value.
- Numbering is guarded by the `check-adr-unique` validator in CI. When two open PRs claim the same number, the second to merge renumbers before merging; this project once shipped two ADR-0012 files and broke trunk for every PR behind it.
- Mirror the decision into project memory with `save_decision` (and `supersede_decision` for replacements) so it surfaces in `get_decision` and `get_latest_activity`, and link the ADR from the implementing pull request.

## C4: draw the level that earns its keep

The C4 model (Simon Brown) defines four zoom levels; each has a different cost-to-value ratio, so decide per level:

- **Context** (level 1): the system, its users, and neighboring systems. Cheap, slow to stale, always worth drawing. Every project gets one.
- **Container** (level 2): the deployable units and datastores and the protocols between them. Worth drawing for any system with more than one deployable; this is the diagram on-call engineers and new joiners actually use.
- **Component** (level 3): the parts inside one container. Draw only for containers under active change or with contested boundaries; component diagrams go stale fastest, so each one needs an owner and a review date.
- **Code** (level 4): almost never hand-drawn. If it is needed, generate it from the source (IDE tooling, `pyreverse`); a hand-maintained class diagram is stale on merge.

One level per diagram, one diagram per page, and every diagram states its scope, level, and the commit or date it was validated against.

## Keeping diagrams honest

- Diagrams are code. Prefer Structurizr DSL when maintaining several C4 levels: one model generates all views, so a rename propagates everywhere. Mermaid (including its C4 syntax) is fine for lightweight cases; PlantUML is acceptable. Store the source next to the code and render in CI; never commit only an exported PNG.
- Generate what can be generated: derive container-level diagrams from infrastructure-as-code or module structure where tooling allows. Whatever must stay hand-maintained carries `last_reviewed` and an owner, and gets checked at each release.
- Every image, including rendered diagrams, has alt text describing what it shows.

## Design docs

A design doc precedes non-trivial implementation and states: the problem, the constraints, the non-goals (what this design will not solve — the highest-value section for scope control), the chosen approach, rejected options with reasons, open questions, and the design contracts — the interfaces and invariants that bound each component, consistent with the hexagonal architecture and modularity rules the engineering specialists follow. Link the design doc to the issues and PRs that implement it, and close the loop after delivery by noting what diverged.

## Common pitfalls

- ADRs written after the fact as justification, with the rejected options reverse-engineered; the record must capture the real decision point.
- "Rejected: inferior" with no reason; every rejected option states the specific driver it fails.
- Editing an accepted ADR instead of superseding it, which silently rewrites history.
- Consequences sections listing only positives; reviewers should reject an ADR that admits no cost.
- A wall-poster diagram mixing C4 levels — containers, classes, and users in one picture — that no audience can read.
- Committed PNG diagrams with no source, unedited for a year and now describing a system that no longer exists.
- Design docs without non-goals, which invite scope creep and make review unbounded.

## Definition of done

- [ ] The change was checked against the ADR-significance criteria in `docs/adr/README.md`, and an ADR exists if any criterion applies.
- [ ] The ADR follows the template: context with named constraints, decision drivers, all considered options, outcome with per-option rejection reasons, and consequences including negatives, scope, and follow-ups.
- [ ] The ADR number is unique (`check-adr-unique` passes), the status header is correct, and superseded records point to their successor.
- [ ] The decision is mirrored to project memory via `save_decision` and linked from the implementing PR.
- [ ] C4 diagrams exist at Context level, at Container level when there is more than one deployable, and at Component level only with an owner and review date; each diagram states scope, level, and validated commit.
- [ ] Diagram source (Structurizr DSL, Mermaid, or PlantUML) is committed and rendered in CI; no orphan PNGs; all images have alt text.
- [ ] Design docs state problem, constraints, non-goals, rejected options with reasons, open questions, and design contracts, and link the implementing issues and PRs.
