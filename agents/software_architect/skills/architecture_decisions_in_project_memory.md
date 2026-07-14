---
name: architecture-decisions-in-project-memory
description: Governs mirroring an ADR into project memory through save_decision, encoding MADR sections into the title, rationale, and outcome fields, maintaining the adr:NNNN:status index for lookup, and superseding a prior decision without editing it. Use when recording, retrieving, or superseding an architecture decision in the SurrealDB-backed memory store rather than only in the docs/adr file.
---

# Architecture Decisions in Project Memory

Persist every architecture decision as an MADR-shaped record in the project memory through `save_decision`, retrieve it with `get_decision`, and link it to the issues that drove it and the commit that implements it, so the decision log is queryable state rather than a folder of files nobody re-reads. The canonical ADR text and its MADR sections live in the file the sibling `architectural_decision_records` skill defines; this skill governs how that decision is mirrored into memory, kept findable, superseded, and cross-linked.

## What memory stores and why both layers exist

Keep two representations of the same decision, deliberately:

- The version-controlled file `docs/adr/NNNN-kebab-title.md` is the canonical, reviewable, diffable ADR. It carries the full MADR prose and its status field is mutable (you edit it when the decision is deprecated or superseded).
- The `decisions` table in project memory is an append-only event log reachable by any agent over the `solomon-memory` MCP server, without a git checkout. It is what `get_latest_activity` surfaces and what a downstream agent (the `software_engineer` implementing the change, the `qa` agent verifying it) reads to learn why the structure is the way it is.

The file is the source of truth for the text; memory is the source of truth for "what was decided, by whom, on which branch, against which commit". Never let one exist without the other: a memory record with no file has no reviewable rationale, and a file never written to memory is invisible to agents that do not open the repo.

## Mapping MADR onto the save_decision schema

The schema is flat: `save_decision(title, rationale, outcome, author, branch="main", commit_sha="")`. MADR has more sections than the schema has fields, so use a fixed encoding so every record is parseable the same way:

- `title` — prefix with the ADR number: `"ADR-0007: Adopt SurrealDB as the primary memory store"`. The number is the stable handle that correlates the memory record with `docs/adr/0007-*.md`; without it you cannot join the two layers.
- `rationale` — the MADR **Context** plus **Options considered**: the forces, NFR targets, constraints, and at least two rejected alternatives with the reason each lost. This is the "why", stated as facts, not the position.
- `outcome` — a structured block carrying the remaining MADR sections so status is machine-findable:

  ```
  Status: Accepted
  Decision: We will use SurrealDB as primary with a SQLite fallback.
  Consequences: + single store for graph+document; - operational dependency on a young engine.
  Supersedes: ADR-0003
  ```

  Every record must carry a `Status:` line (Proposed | Accepted | Deprecated | Superseded) and the **Consequences** must name at least one cost. An outcome with only upsides is rejected in review, same rule as the file.
- `author` — the deciding agent id (`software_architect`), not a human name, so provenance is consistent across the harness.
- `branch` and `commit_sha` — the branch and commit that introduce the change the ADR governs. Leave `commit_sha` empty while the ADR is `Proposed`, and backfill it when the implementing change merges. This pair is the link from decision to code.

Capture the returned `decision_id` immediately; it is the only handle `get_decision` accepts and there is no list-all query.

```python
res = save_decision(
    title="ADR-0007: Adopt SurrealDB as the primary memory store",
    rationale="Context: need graph + document in one store, <50ms reads... "
              "Options: Postgres+JSONB (rejected: weak graph traversal); "
              "Neo4j (rejected: no document model, license).",
    outcome="Status: Accepted\nDecision: We will use SurrealDB primary, SQLite fallback.\n"
            "Consequences: + one store; - young engine, ops risk.",
    author="software_architect",
    branch="feat/memory-backend",
    commit_sha="",   # backfilled on merge
)
adr_no = "0007"
save_memory(key=f"adr:{adr_no}:status", value=f"accepted:{res['decision_id']}", category="adr-index")
```

## Keeping the log findable

`get_decision` needs an id, and the `decisions` table has no "find by ADR number" query. Maintain a mutable index in the key/value memory: write `save_memory(key="adr:NNNN:status", value="accepted:<decision_id>", category="adr-index")` on every status change. This gives you the one thing the append-only `decisions` table cannot: an O(1) lookup from ADR number to current status and current record id. `get_memory("adr:0007:status")` tells you a decision is live without scanning history.

Before opening a new decision, read the index and `get_latest_activity` to confirm you are not re-deciding something already `Accepted`. Re-litigating a settled ADR without citing and superseding it is decision drift.

## Superseding a prior decision

Decisions in memory are immutable, matching the ADR rule in `architectural_decision_records`. You never edit an accepted record's substance through `save_decision`; you write a new one and re-point the index:

1. Write the new decision (`ADR-0011`) with `Supersedes: ADR-0007` in its `outcome`.
2. Update the canonical file: set `docs/adr/0007-*.md` status to `Superseded by ADR-0011`, and `docs/adr/0011-*.md` to `Accepted`. The file is where the human-readable status lives.
3. Re-point the index entries: `save_memory("adr:0007:status", "superseded-by:0011", "adr-index")` and `save_memory("adr:0011:status", "accepted:<new_id>", "adr-index")`.

The old memory record stays untouched as a historical fact; the index, not the record, tells a reader it is dead. Querying `get_decision` on the superseded id must still return the original rationale, because the audit value of an ADR is that the wrong-in-hindsight decision and its reasoning remain visible.

## Linking each ADR to its issues and code

An ADR that governs nothing concrete is decision theater. Bind it in both directions:

- **To the issue that drove it.** When a decision answers a question raised in an issue, name the github id in the `rationale` (`"Driven by #142"`). Use `get_open_issues` before deciding to find the architecture-affecting work in flight, and `get_issue("142")` to pull the constraints into the Context. When the ADR creates follow-up work, `log_issue(github_id, title="Implement ADR-0007: ...", type_="task", status="open")` so the implementation is tracked and traceable back to the decision.
- **To the code that implements it.** Backfill `commit_sha` (and the right `branch`) when the change merges, so the decision points at the diff that realizes it. Reference `ADR-0007` in the commit message and the `design contract` the decision produces, closing the loop from code back to rationale.
- **To the next agent.** When you hand the accepted ADR to implementers, `log_handoff(sender="software_architect", recipient="software_engineer", contract_type="adr", contract_path="docs/adr/0007-*.md", status="ready")` so the decision is picked up as work, not lost in a folder.

## Common pitfalls

- Writing the file but never calling `save_decision`, so agents without a checkout cannot see the decision and `get_latest_activity` is blind to it.
- Calling `save_decision` and discarding the returned `decision_id`; there is no list query, so the record becomes unretrievable. Always persist it in the `adr:NNNN:status` index.
- Omitting the `ADR-NNNN` prefix from `title`, breaking the join between the memory record and the canonical file.
- No `Status:` line in `outcome`, so no agent can tell a live decision from a superseded one without reading every file.
- An `outcome` with only benefits and no cost in **Consequences**; the trade-off is mandatory, same as in the sibling ADR skill.
- "Editing" a superseded decision by writing a new record over the old id concept instead of writing a new ADR and re-pointing the index; this destroys the audit trail.
- ADR with empty `commit_sha` long after the change merged, leaving the decision unlinked from the code it governs.
- Re-deciding a settled question without reading the index or citing the prior ADR, producing two live records that contradict each other.
- Putting full MADR prose only in memory and treating the file as optional; memory text is not reviewable in a pull request, so the decision escapes code review.

## Definition of done

- [ ] Every architecture decision exists as both a `docs/adr/NNNN-*.md` file and a `save_decision` record, and the `decision_id` is stored in an `adr:NNNN:status` memory key.
- [ ] `title` carries the `ADR-NNNN:` prefix; `rationale` holds Context plus at least two rejected options; `outcome` carries `Status:`, `Decision:`, and a `Consequences:` line that names a cost.
- [ ] `author` is the deciding agent id; `branch` and `commit_sha` link the record to the implementing change, with `commit_sha` backfilled at merge.
- [ ] Superseding writes a new ADR with `Supersedes: ADR-NNNN`, flips both file statuses, and re-points the index; the old `get_decision` record is left intact and still retrievable.
- [ ] The driving issue is cited in the record, and any follow-up work is logged with `log_issue` referencing the ADR number.
- [ ] The accepted ADR is handed to implementers with `log_handoff` pointing at the canonical file path.
- [ ] Before any new decision, the `adr-index` and `get_latest_activity` were checked to avoid re-deciding a settled, unsuperseded ADR.
