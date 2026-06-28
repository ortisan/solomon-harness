# Architecture Decision Records

This directory holds the project's Architecture Decision Records (ADRs): one file
per architecturally significant decision, in [MADR](https://adr.github.io/madr/)
style, numbered sequentially.

## When to write one

An ADR is warranted when a change is architecturally significant. The
`/solomon-dev-start` and `/solomon-dev-release` workflows evaluate this
automatically against the checklist in `agents/software_architect/skills/architecture_decisions_in_project_memory.md`.
Write an ADR when the change does any of the following:

- Introduces, removes, or swaps a framework, datastore, or major dependency.
- Changes a public contract (API, event schema, CLI) or a data model.
- Establishes a cross-cutting pattern (auth, error handling, caching, concurrency).
- Trades off a quality attribute (performance, security, cost, availability).
- Is hard or expensive to reverse later.

A bug fix, a refactor with no contract change, or a routine feature does not need one.

## How they are created

1. Copy `0000-adr-template.md` to `NNNN-<kebab-title>.md` with the next number.
2. Fill in context, options, the decision, and its consequences.
3. Record the same decision in the project memory with `save_decision` so it is
   queryable with `get_decision` and surfaces in `get_latest_activity`.
4. Link the ADR from the pull request that implements it.

Superseding a decision: create a new ADR, set the old one's status to
`superseded by ADR-XXXX`, and reference it from the new record.
