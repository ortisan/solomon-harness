# ADR-0041: Pluggable embedder and a vector index over decisions

- Status: accepted
- Date: 2026-07-17
- Deciders: software_architect, software_engineer, dba
- Amends: ADR-0016 (typed states, gated embeddings, closed durability funnel)

## Context and problem statement

A live audit of the SurrealDB memory store found two gaps in the vector layer that ADR-0016 established.

First, the `models.embedding` config key (shipped as `text-embedding-004`) is declared but read nowhere: the client always uses the built-in lexical `HashingEmbedder`, and there is no supported way to plug a real model-backed embedder without editing the client. The `Embedder` protocol anticipates a real model, but nothing wires one.

Second, only the `memory` table carries an embedding and an HNSW index. Decisions — the richest knowledge in the store — have no embedding and no index, so they can only be fetched by id or "latest N", never searched by content.

## Decision drivers

- The store is deliberately dependency-light and offline-capable, with a safe lexical default (ADR-0016). Any change must preserve that default and add no forced runtime dependency.
- Changing the embedding dimension forces an HNSW `REMOVE`/re-`DEFINE` and a re-embed of every row — a live-tenant migration. The default path must not trigger one.
- Decisions should be first-class in semantic recall, on the same mechanism as memory.

## Considered options

- Bundle a local model (sentence-transformers) as a runtime or optional dependency — rejected here: it adds a heavy dependency and a dimension migration, beyond the dependency-free scope chosen with the maintainer.
- Call an embedding API (e.g. Gemini `text-embedding-004`) — rejected here: it needs an API key and network, breaking the offline/degraded contract.
- A config-driven plug seam plus a decisions vector index, default unchanged (chosen).

## Decision outcome

The embedder becomes pluggable from `.agent/config.json`. `models.embedding` is interpreted as a `module:Class` import path when it names a real embedder object; the class is imported defensively (the same optional-import pattern the SurrealDB backend uses), instantiated, and validated by a probe embed. Any other value (including the shipped `text-embedding-004`, an unimportable path, or a failing probe) falls back to `HashingEmbedder`, so the store never fails to open. Precedence is: an explicitly injected embedder, then the config plug, then the lexical default.

The HNSW dimension follows the active embedder. Both vector indexes (`memory_embedding` and the new `decisions_embedding`) are built at connect time from the embedder's `dim` attribute (default 256), moved out of the static schema list into `_vector_index_statements`. With the default embedder the DDL is byte-identical to before, so it applies to an existing tenant with no migration. A plugged embedder of a different dimension requires a one-time index rebuild, which the harness does not perform automatically.

Decisions are embedded on write in `_db_log_decision` from their title, rationale, and outcome — no category gate, since a decision is always semantic. `search_decisions` is the decisions-table analogue of `semantic_search`, exposed through `MemoryService` and the `solomon-memory` MCP server. Embeddings are computed in the DB writer, not stored in the durability mirror, so a decision replayed after an outage is re-embedded on reconcile.

A `reindex-embeddings` CLI command (and `DatabaseClient.reindex_embeddings`) backfills any decision or memory row whose `embedding IS NONE`, using the active embedder and honoring the memory semantic-category gate. It is additive and idempotent, so it needs no single-driver lock; it is the path that indexes the decisions written before this change and re-embeds every row after an embedder swap.

### Consequences

- Positive: decisions become searchable (lexically today, semantically the moment a model is plugged); the embedder is swappable with no code change; the dependency-free, offline default and the existing memory behavior are unchanged.
- Negative: a real semantic embedder still requires an out-of-tree model and a manual index rebuild + reindex when its dimension differs from 256; the lexical default only matches on shared tokens.
- Neutral: `models.embedding` gains meaning (a plug path) without changing the default; the two vector indexes now derive from the embedder rather than a module constant.
