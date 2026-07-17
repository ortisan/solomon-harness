# ADR-0016: Typed states, gated embeddings, and a closed durability funnel for the project memory

- Status: accepted
- Date: 2026-07-04
- Deciders: software_architect, software_engineer, dba
- Issue: #165, #166

## Context and problem statement

The 2026-07-04 memory-architecture review found the project memory looser than
its consumers assume. Status tokens are free-form outside the issue vocabulary
(ADR-0006): the loop-run writer stores `failed` while the aggregator counts
`failure`, so the failure rate reads 0.0 forever (F1); handoffs, sessions, and
milestones each carry ad-hoc tokens (`pending`, `active`, `approved`) that no
reader can rely on (F2). Board transitions live as `board_history:*` JSON blobs
stamped with the naive local clock, so cycle time needs a JSON parse per issue
and the timestamps skew with the host timezone (F4). Every memory row is
embedded into the HNSW vector index, including the code index and board
history, which pollutes semantic search (F6). And the ADR-0007 durability
funnel does not cover graph edges or metrics, while the SQLite fallback returns
`lastrowid` instead of the minted record id, so ids are not backend-invariant
(F5, F7, F8).

## Decision drivers

- One canonical token per logical state, established below every consumer, as
  ADR-0006 did for issues; reads stay tolerant, writes normalize
  (expand/contract, no destructive rewrite).
- Garbage from foreign writers (anything bypassing `DatabaseClient`) must be
  rejected at the store, without turning the schemaless tables rigid.
- Durability must hold for every write kind: a record written during an outage
  must survive to reconcile.
- Backend-invariant ids: a caller must get the same id whether the write landed
  on SurrealDB or the SQLite fallback.

## Considered options

- Full schemafull tables (DEFINE TABLE SCHEMAFULL with typed fields everywhere).
- Targeted DEFINE FIELD ASSERT constraints on the status/state fields only,
  with normalize-on-write in the client (chosen).
- Application-only normalization with no store-side constraint.
- For embeddings: an allowlist of semantic categories vs a denylist of the
  known non-semantic ones.
- For old timestamps: a big-bang migration of ISO-string time fields to native
  datetime vs native datetime for new tables only.

## Decision outcome

Chosen: targeted constraints plus normalization at the write seam, a
first-class transitions table, a denylisted embedding gate, and funnel coverage
for edges and metrics.

### Canonical vocabularies per stateful kind

Normalization happens in `solomon_harness/tools/database_client.py` at each
public write method, below every consumer (the MCP server, the workflows, the
GitHub board adapter), exactly like `normalize_status` (ADR-0006):

| Kind      | Field  | Canonical set                                              | Aliases mapped on write                              |
| --------- | ------ | ---------------------------------------------------------- | ---------------------------------------------------- |
| issue     | status | Ideas, Backlog, Ready, in_progress, code_review, qa, closed (+ legacy open, done, Done) | ADR-0006 aliases, plus casing aliases for the display columns |
| loop_run  | status | ok, failed, skipped (ADR-0039)                              | success, passed -> ok; failure, error -> failed       |
| handoff   | status | open, accepted, done                                        | ready, pending -> open; approved -> accepted; completed, closed -> done |
| session   | status | active, done                                                | completed, closed, finished -> done                   |
| milestone | state  | open, closed                                                | active, pending -> open; complete, completed, done -> closed |

Unknown tokens pass through lowercased: normalization never invents a state,
and the store-side assert (below) is what rejects genuine garbage. The mirror
replay path (`_replay`) routes each kind's status field through the same
normalizer, so a legacy pending mirror can never trip an assert.

`loop_run_failure_rate` counts canonical `failed` plus legacy `failure` rows,
so pre-fix data does not vanish from the metric (#165).

### Targeted DEFINE FIELD ASSERT policy

Tables stay SCHEMALESS. One `DEFINE FIELD IF NOT EXISTS ... ASSERT $value =
NONE OR $value IN [...]` per stateful field (issues.status, handoffs.status,
sessions.status, loop_runs.status, milestones.state), each executed as its own
`query()` call in `_bootstrap_surreal_schema` (the SDK only surfaces the first
statement's result per call — the one-statement-per-call invariant is load-
bearing and preserved). `NONE` stays allowed so rows that never carried the
field remain writable. Harness code cannot trip the asserts because it
normalizes first; the asserts exist to reject garbage from foreign writers.

### Transitions table

`DEFINE TABLE transitions SCHEMALESS` with `issue` typed `record<issues>`,
`entered_at` typed `datetime` (server-side `time::now()`), and a composite
index on `(issue, entered_at)`. A row is `{issue, from_status, to_status,
entered_at, actor}`, written by `record_status_transition` from the
`github.record_transition` seam. Expand/contract: the legacy `board_history:*`
JSON write is kept alongside for one release and removed in the next; its
timestamp moves from the naive local clock to UTC now. The SQLite fallback has
a parity table (issue stored as the github_id string, entered_at as UTC ISO),
so transitions are recorded even degraded. `cockpit_read` prefers transitions
rows per issue and falls back to the legacy keys. Transitions are not mirrored
this release: durability is covered by the parallel legacy write, which goes
through the funnel; the mirror extension can follow when the legacy write is
removed.

### Embedding category gate

A denylist, not an allowlist: the known non-semantic categories
(`codebase_index`, `index`, `board_history`) are excluded from embedding at
`save_memory` time, and `semantic_search` excludes them by default while still
honoring an explicit `category` argument. A denylist preserves behavior for
every unknown category (new categories stay searchable without a code change),
whereas an allowlist would silently drop them from the index — the failure
mode we are fixing, inverted. Existing rows that already carry a stale
embedding are out of scope; they fall out on their next save (UPSERT CONTENT
replaces the record) and can be swept later if needed.

### Closed durability funnel

- `relate()` routes through `_write_through` with a minted edge id (kind
  `edge`); replay executes an idempotent RELATE, check-before-create on a
  `record_id` field stamped on the edge. On the degraded fallback the DB write
  is a no-op and the pending mirror carries the edge to reconcile. A
  pure-SQLite configuration (no SurrealDB primary at all) still raises the
  graph guard, since there is nothing to replay into.
- `record_metric()` is mirrored (kind `metric`) and replayed as an idempotent
  UPSERT carrying its original time coerced to a native datetime.
- SQLite tables gain `record_id TEXT` with a unique index (ALTER cannot add a
  UNIQUE column, so it is a plain column plus `CREATE UNIQUE INDEX`), migrated
  expand/contract like `_ensure_issue_assignee_column`. Every minted-id write
  returns the minted id on both backends — never `lastrowid` — and the SQLite
  get-by-id paths match `id` or `record_id`, accepting the SurrealDB
  `table:key` spelling.
- Consequence of backend-invariant ids: the SQLite
  `issues.milestone_id -> milestones(id)` FOREIGN KEY is dropped (a rebuild
  migration, `_ensure_issue_milestone_fk_dropped`). It targeted the integer
  rowid and rejected the minted milestone record ids; the SurrealDB primary
  never enforced it, and the authoritative milestone link is the graph
  `contains` edge, so the linkage is soft by design.

### Explicitly deferred and rejected

- Deferred to wave 2 (#167): the `worked_on` episodic edge and the
  digest/resume rewrite.
- Rejected: a big-bang migration of the existing ISO-string timestamp fields
  to native datetime storage. The new transitions table uses native datetime;
  existing fields keep their format, noted as future expand/contract work.

### Consequences

- Positive: state tokens become a contract, the failure rate reads true,
  cycle time is one indexed query, semantic search stops returning file blobs,
  and an edge or metric written during an outage survives to reconcile.
- Negative: the asserts make foreign writes fail loudly on SurrealDB (by
  design), and one release carries the dual board-history write; readers of
  raw SQLite rows see a new nullable column per table.
- Follow-ups: remove the legacy `board_history:*` write next release; wave 2
  (#167) for `worked_on` and the digest rewrite; optional sweep of stale
  embeddings.

## More information

Review findings F1, F2, F4, F5 (partial), F6, F7, F8 (2026-07-04). Builds on
ADR-0006 (issue-status vocabulary), ADR-0007 (memory resilience model),
ADR-0011 (multimodel memory layer). Recorded in the project memory via
`save_decision`.
