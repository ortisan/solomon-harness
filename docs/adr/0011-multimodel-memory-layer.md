# ADR-0011: Multi-model memory layer in SurrealDB — graph, timeseries, relational, vector

- Status: accepted
- Date: 2026-06-29
- Deciders: software_architect, software_engineer, dba, product_owner
- Issue: PR #119 (delivered outside the board workflow; no tracking issue)

## Context and problem statement

The project memory (`solomon_harness/tools/database_client.py`) is SurrealDB-primary
with a SQLite fallback, but it used SurrealDB only as a relational/document store:
nine `SCHEMALESS` tables with no indexes, no graph edges, no timeseries modeling,
and no vector search. The product intent was a true multi-model store — record the
project memory as a graph where relationships matter, as timeseries for statistics,
relationally for lookups, and as vectors for semantic recall — so an agent can
navigate relationships and recall by meaning instead of rescanning the codebase. A
spec-verification audit found this the largest unmet requirement: the multi-model
claim was aspirational, not implemented.

## Decision drivers

- Fit the model to the access pattern (relationship traversal, time-bucketed stats,
  key lookup, similarity) rather than forcing everything through document scans.
- Additive and non-breaking on the existing schemaless tables and write paths.
- Dependency-light (Karpathy simplicity): no heavy ML or runtime dependency on the
  default path.
- Backend-honest: graph and vector are SurrealDB-only and must degrade clearly on the
  SQLite fallback; statistics must survive a fallback.
- Injection-safe, and testable in CI where no SurrealDB is running.

## Considered options

- Keep document/relational only (status quo) and rewrite the spec to match.
- Bolt on separate stores beside SurrealDB (a graph DB, a vector DB, a TSDB).
- Use SurrealDB's native multi-model features (RELATE edges, time bucketing, HNSW
  vector index) in place.
- Embedding source for the vector model: an external model/API vs a dependency-free
  local embedder.

## Decision outcome

Chosen option: use SurrealDB's native multi-model features in place, additively.

- Relational: `DEFINE INDEX IF NOT EXISTS` for hot lookups and integrity
  (`issues.github_id` UNIQUE, `issues.status`, `decisions.created_at`).
- Graph: `TYPE RELATION` edge tables (`blocks`, `supersedes`, `contains`, `produced`,
  `addresses`) with parameterized `RELATE` writes, arrow traversals, typed helpers,
  and a cycle-guarded transitive walk (`supersedes_chain`).
- Timeseries: a `metrics` table (`name, value, tags, time`) with a `(name, time)`
  index; `record_metric`/`query_metric` work on BOTH backends so statistics survive a
  SQLite fallback, while `aggregate_metric` (`time::group` buckets), `loop_run_throughput`
  and `loop_run_failure_rate` are SurrealDB-only.
- Vector: an `embedding` field on `memory` with an HNSW `DIMENSION 256 DIST COSINE`
  index and KNN `semantic_search` via the `<|k, EF|>` operator, over a pluggable
  `Embedder` Protocol whose default `HashingEmbedder` is a dependency-free, L2-normalized
  lexical embedding (swappable for a model-backed one).

All `DEFINE`s are `IF NOT EXISTS` and non-breaking; the graph and vector methods raise a
clear `RuntimeError` on the SQLite backend. The capabilities are exposed over
`MemoryService` and the MCP server.

Chosen because native multi-model keeps one store, one connection, and one
tenant-isolation model — no cross-store consistency problem and no extra
infrastructure — while satisfying each access pattern directly and staying additive
over the existing schemaless tables. A dependency-free default embedder keeps the
vector path usable and testable without committing the project to an ML runtime.

### Consequences

- Positive: relationship navigation (blocking graphs, supersession chains, milestone
  membership), time-bucketed statistics, fast indexed lookups, and semantic recall —
  without rescanning the project; a single store to operate; tenant isolation preserved.
- Negative: graph and vector are unavailable on the SQLite fallback (metrics still
  work); the default `HashingEmbedder` is lexical, not semantic, so `semantic_search`
  ranks by token overlap until a model-backed embedder is injected; historical `memory`
  rows carry no embedding until re-saved.
- Follow-ups: a pluggable model-backed embedder; a one-time re-embed/backfill of
  historical rows for retroactive semantic recall; consider `DEFINE FIELD` typing as the
  data model stabilizes.

## More information

Delivered in PR #119 (squash `b554875`): `solomon_harness/tools/database_client.py`
(schema, graph/timeseries/vector methods, `HashingEmbedder`), `memory_service.py` and
`mcp_server.py` (exposure), and `tests/test_database_client_multimodel.py`. This
decision is also recorded in the project memory via `save_decision`.
