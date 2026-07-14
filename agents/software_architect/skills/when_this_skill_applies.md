---
name: when-this-skill-applies
description: Governs triaging which architecture artifact a change deserves — a commit note, a C4 view update, a design contract, or an ADR — by scoring its blast radius against its cost of reversal using Bezos's one-way and two-way door framing. Use when deciding whether a change needs a design contract, a diagram update, a full ADR, or no architecture artifact at all.
---

# Architecture Engagement Model

Decide which architecture artifact a change deserves from its blast radius and its cost of reversal, not from its line count or who requested it: most changes need only a commit note, a few earn a design contract or a C4 view, and only the expensive-to-reverse decisions justify an ADR.

## The triage test: blast radius times cost of reversal

Before producing any artifact, score the change on two axes.

- Blast radius: how many components, teams, or consumers feel the change. Local (one module, one repo) versus system-wide (a shared contract, a data store, an integration, a cross-cutting concern like auth, caching, or messaging).
- Cost of reversal: the effort to undo it once shipped. Reversible in an afternoon (a config flag, an internal helper, a private function signature) versus a one-way door (a published API, a persistence engine, a service split, a wire format, a security model).

Map the score to the lightest artifact that still makes the decision auditable:

| Blast radius \ Reversal | Reversible in an afternoon | Costly / one-way door |
|---|---|---|
| Local to one module | Commit message + code comment | Design contract on the boundary (+ tests) |
| System-wide | C4 view update + design contract | ADR (+ C4 update + design contract) |

The rule of thumb: a change reversible in an afternoon never needs an ADR, because the cost of writing and maintaining the record exceeds the cost of just redoing the work. Reserve ADRs for decisions a future maintainer will ask "why on earth did they do this".

This is Bezos's Type 1 / Type 2 framing. Type 1 ("one-way door") decisions are slow, deliberate, and recorded; Type 2 ("two-way door") decisions are fast and delegated. Misclassifying a Type 2 as Type 1 drowns the team in analysis; misclassifying a Type 1 as Type 2 ships a mistake that is expensive to walk back.

## Which artifact answers which question

- C4 view (`c4_model_diagrams`) — answers "what are the moving parts and how do they talk". Produce or update one when you add or remove a Container (a service, store, broker, SPA) or change a link's protocol or synchronicity. Structure changed means the diagram changes in the same PR.
- ADR (`architectural_decision_records`) — answers "why is it this way and what did we reject". Produce one for an architecturally significant, costly-to-reverse choice that had at least two real options.
- Design contract (`design_contracts_as_component_boundaries`) — answers "what is the agreement at this boundary". Produce one whenever a new boundary appears or an existing one's observable behavior changes, regardless of blast radius, because an unspecified boundary is the most common source of silent breakage.
- Nothing but a commit note — the default. Most changes are local and reversible; over-documenting them is its own erosion, because nobody trusts a log full of noise.

The last-responsible-moment principle governs timing: make the decision when you have the most information but before the cost of deferring it exceeds the cost of deciding. Recording it in an ADR is what lets you defer safely, since the context is captured even if the choice is later revisited.

## Worked triage example

Decision: "Put a Redis cache in front of the product-catalog read path to cut p99 latency."

Walk the test:

1. Blast radius — system-wide. Catalog reads are consumed by web, mobile, and the search indexer; a cache changes the consistency story for all of them.
2. Cost of reversal — moderate-to-high. Removing the cache later is mechanically easy, but consumers will have come to rely on the new latency profile, and the cache introduces a staleness window and an invalidation contract that, once published, others build on.
3. Verdict — system-wide and not a clean two-way door, so it earns the full set: an ADR (options: Redis vs read-replica vs materialized view; consequences: staleness window, new failure mode, ops cost), a Container-level C4 update adding the cache and labeling the new links, and a design contract on the cache boundary stating the invalidation guarantee, TTL, and staleness tolerance as a concrete NFR.

Contrast: "Rename an internal helper and inline a private method." Local, reversible in an afternoon, so a commit message is the whole record. Writing an ADR for it would be decision theater.

When the decision is significant, the verdict feeds the `architecture_review_gate` as an input, and the accepted ADR is mirrored to project memory per `architecture_decisions_in_project_memory`.

## Common pitfalls

- Writing an ADR for a two-way-door change, which buries the genuinely significant decisions in noise so nobody re-reads the log; a reviewer rejects it because the artifact costs more to maintain than the decision costs to redo.
- Shipping a one-way-door change (a published API, a wire format, a persistence engine) with only a commit note, leaving no recorded rationale; a reviewer rejects it because the next maintainer cannot tell what was rejected or why.
- Updating code structure without updating the C4 view in the same PR, so the diagram lies within a sprint.
- Adding or changing a boundary without a design contract, the single most common cause of silent consumer breakage.
- Deciding too early, before the information exists, instead of at the last responsible moment, locking in a choice the team later cannot justify.
- Treating "who asked" as the trigger (a senior asked, so it must be an ADR) instead of blast radius and reversibility.

## Definition of done

- [ ] The change is scored on both axes, blast radius and cost of reversal, before any artifact is produced.
- [ ] The lightest sufficient artifact is chosen per the matrix; reversible local changes get a commit note, not an ADR.
- [ ] Any new or changed boundary has a design contract regardless of blast radius.
- [ ] Any Container added or removed, or any link protocol changed, is reflected in a C4 view in the same PR.
- [ ] Costly-to-reverse, system-wide decisions have an ADR with at least two options and a stated cost.
- [ ] Significant verdicts are routed to the `architecture_review_gate`, and accepted ADRs are mirrored to project memory.
