# Architecture Decision Records

This directory holds the project's Architecture Decision Records (ADRs): one file
per architecturally significant decision, in [MADR](https://adr.github.io/madr/)
style, numbered sequentially.

## When to write one

An ADR is warranted when a change is architecturally significant. The
`/solomon-start` and `/solomon-release` workflows evaluate this
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

Amending a decision: use a new ADR when the amendment needs its own context,
options, and consequences. Keep both records `accepted`, add `Amends: ADR-XXXX`
to the new record, and add a reciprocal dated `Amended:` pointer to the old one.

## Reconciliation section (optional, post-merge)

An ADR may carry an optional `## Reconciliation` section, appended once the
pull request implementing the decision merges. It is append-only: never
rewritten or edited in place, only ever added to, exactly like the record's
Status field is the one field a decision changes after acceptance. Status and
`## Reconciliation` answer different questions and neither substitutes for the
other: Status changes to `superseded by ADR-XXXX` when the decision itself is
reversed by a later choice; `## Reconciliation` records, merge by merge,
whether what actually shipped matched what the Decision Outcome claimed.

Write one entry per merge:

```
## Reconciliation

- 2026-07-17, merge `a1b2c3d` (PR #341): matches-as-designed. Reviewed by
  software_architect during /solomon-review; the Decision Outcome's claim
  that the cache invalidates on write is backed by
  `solomon_harness/cache.py:88-94`.
```

or, when the review found a mismatch:

```
## Reconciliation

- 2026-07-17, merge `a1b2c3d` (PR #341): [DEVIATION] the Decision Outcome
  states the retry budget is 3 attempts; the shipped code
  (`solomon_harness/retry.py:41`) hardcodes 5. Filed as issue #350; the ADR's
  prose was not corrected in place — a superseding or amending record carries
  the reconciled figure once filed.
```

Each entry cites the merge commit and the review verdict that produced it —
the ADR-reconciliation step in `agents/software_architect/skills/architecture_review_gate.md`,
run during `/solomon-review` — so a later reader can tell, without
re-deriving it, whether an Accepted ADR still describes the code or carries
known, tracked drift. A section with only "matches-as-designed" entries is
evidence the record stays trustworthy; one with an open `[DEVIATION]` and no
follow-up ADR or issue is itself a signal the decision needs re-litigating,
not more prose. The standing architecture-scan loop
(`architecture_scan_loop`) treats an Accepted ADR with no `## Reconciliation`
section after several merged PRs have touched its area as a drift finding in
its own right.

This convention extends the pull-request body contract in ADR-0031
(`docs/adrs/0031-pr-body-adr-contract.md`): that record established the
machine-checked `ADR:` line on every PR body; this section covers what
happens on the far side of that line once the PR actually merges. Recording
it here, rather than as a new numbered ADR with reciprocal `Amends:`/
`Amended:` pointers, lets the convention apply starting now; formalizing it
as a proper amending record is a follow-up, not a precondition for using it.
