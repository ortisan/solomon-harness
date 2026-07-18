# ADR-0042: The open-issue read stays a scan; drop the dead issues_status index

- Status: accepted
- Date: 2026-07-18
- Deciders: software_architect, dba, software_engineer
- Amends: ADR-0016 (typed states, gated embeddings, closed durability funnel)

## Context and problem statement

A live audit of the SurrealDB memory store found two related facts about the `issues` table's status indexing.

`get_open_issues` runs `SELECT * FROM issues WHERE status IS NONE OR status IS NULL OR status NOT IN $terminal` on every session start. The predicate is a negation, so the planner cannot use an index: `EXPLAIN` resolves it to a `TableScan`.

Separately, the `issues_status` index (`ON issues FIELDS status`) is dead. Its only conceivable consumer is the open-issue read, which is a negation it cannot serve; the cockpit buckets issues by status in Python after a full `list_issues` read, and no code path issues a positive `status = $x` query. The index is maintained on every issue write and read by nothing.

## Decision drivers

- Correctness and simplicity over speculative performance. A derived index that can silently return the wrong open set is worse than a cheap scan.
- The read is not hot in cost terms: 360 issues today, a trivial predicate, sub-millisecond. The cockpit already full-scans every issue via `list_issues` on the same board render, so the open-issue read is not the bottleneck.
- Every maintained-but-unread index is pure write-time cost and a false signal to a future reader that a query is served.

## Considered options

- Add a derived `open` (or `terminal`) boolean, index it, and rewrite the read to `WHERE open = true`. Rejected: the boolean must be recomputed on every status write, and there is more than one (the `log_issue` UPSERT and the board-transition `UPDATE ... SET status`), on both the SurrealDB and SQLite backends, plus a live-tenant backfill. A single missed path silently drops issues from `get_open_issues` with no error. The maintenance surface and consistency risk outweigh the bounded-growth benefit at this scale.
- A functional/expression index on `NOT is_terminal(status)`. Rejected: SurrealDB has no expression-index support; the negation cannot be indexed directly either way.
- Keep the read as a scan and remove the dead index (chosen).

## Decision outcome

`get_open_issues` stays a scan. The predicate is correct (a NULL/NONE status is open, matching `digest.build_digest`) and cheap at the current and foreseeable issue count. This is documented at the read so a future maintainer does not mistake the scan for an oversight.

The `issues_status` index is removed. The schema bootstrap replaces its `DEFINE INDEX IF NOT EXISTS` with `REMOVE INDEX IF EXISTS issues_status ON issues`, which drops it from existing tenants on the next connect and is an idempotent no-op on a fresh tenant (verified on SurrealDB v3.1.5). Removing it costs one read path nothing and saves the write-time maintenance.

Revisit the derived-boolean index only when the issue count makes the scan measurable — on the order of 10^4 rows, or a profiled `get_open_issues` above a few milliseconds. At that point the backfill-and-maintain cost is justified; below it, it is not.

### Consequences

- Positive: one dead index gone (less write amplification, no false "this query is indexed" signal); no derived-field consistency risk introduced; the read stays correct and simple.
- Negative: `get_open_issues` remains a `TableScan`, so its cost grows linearly with issue count; the revisit trigger above is the mitigation.
- Neutral: the indexing policy for the `issues` table is now `issues_github_id` (unique, the record key) only, which the hot per-issue lookup already uses.
