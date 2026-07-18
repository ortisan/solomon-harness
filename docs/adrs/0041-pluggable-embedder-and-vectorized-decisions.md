# ADR-0041: Selectable embedder and a vector index over decisions

- Status: accepted
- Date: 2026-07-18
- Deciders: software_architect, software_engineer, dba, security
- Issue: #303
- Amends: ADR-0016 (typed states, gated embeddings, closed durability funnel)

## Context and problem statement

A live audit of the SurrealDB memory store found two gaps in the vector layer that ADR-0016 established.

First, the `models.embedding` config key (shipped as `text-embedding-004`) is declared but read nowhere: the client always uses the built-in lexical `HashingEmbedder`, and there is no supported way to select a different embedder. The `Embedder` protocol anticipates a real model, but nothing wires one.

Second, only the `memory` table carries an embedding and an HNSW index. Decisions, which hold the free-text rationale and outcome behind every architectural choice, have no embedding and no index, so they can only be fetched by id or "latest N", never searched by content.

## Decision drivers

- The store is deliberately dependency-light and offline-capable, with a safe lexical default (ADR-0016). Any change must preserve that default and add no forced runtime dependency.
- `.agent/config.json` is git-tracked and already treated as sensitive: `loop_policy` denylists it from autonomous writes because it can widen a run's autonomy or defeat the cost ceiling. Selecting an embedder from it must not turn it into a code-execution vector.
- Changing the embedding dimension forces an HNSW `REMOVE`/re-`DEFINE` and a re-embed of every row, a live-tenant migration. The default path must not trigger one.
- Decisions should be first-class in semantic recall, on the same mechanism as memory.

## Considered options

- Bundle a local model (sentence-transformers) as a runtime or optional dependency. Rejected here: it adds a heavy dependency and a dimension migration, beyond the dependency-free scope chosen with the maintainer.
- Call an embedding API (e.g. Gemini `text-embedding-004`). Rejected here: it needs an API key and network, breaking the offline/degraded contract.
- Import a config-named `module:Class` embedder. Rejected on security review: `importlib.import_module` of a git-tracked-config-controlled path runs arbitrary code the moment any `DatabaseClient` is constructed, which is strictly worse than what the `loop_policy` denylist on that file was written to prevent.
- A name-selected registry of vetted embedders plus a decisions vector index, default unchanged (chosen).

## Decision outcome

`models.embedding` is a key into a hardcoded registry of reviewed embedder factories (`_EMBEDDER_REGISTRY`), currently `{"hashing": HashingEmbedder}`. The config selects among vetted code; it never names an importable path, so the git-tracked config cannot execute arbitrary code. A name absent from the registry (including the shipped `text-embedding-004`) resolves to the lexical default, so the store never fails to open. A caller that needs an arbitrary embedder injects the object directly through `DatabaseClient(embedder=...)`; exposing a new model to config means adding a reviewed factory to the registry and shipping its integration. Precedence: injected embedder, then the registry selection, then the default.

The HNSW dimension follows the active embedder. Both vector indexes (`memory_embedding` and the new `decisions_embedding`) are built at connect time from the embedder's dimension, taken from an integer `dim` attribute when present and otherwise from the actual length of a probe vector, so an embedder that emits 768-long vectors can never be indexed at 256 and then fail on the first write. With the default `HashingEmbedder` the dimension is 256 and the DDL is byte-identical to the pre-change schema, so it applies to an existing tenant with no migration. Swapping to an embedder of a different dimension still requires a one-time manual index rebuild, which the harness does not perform automatically.

Decisions are embedded on write in `_db_log_decision` from their title, rationale, and outcome; there is no category gate, since a decision is always semantic. `search_decisions` is the decisions-table analogue of `semantic_search`, exposed through `MemoryService` and the `solomon-memory` MCP server. The vector is stored only for the index: `get_decision` and `list_decisions` read with `OMIT embedding` so a caller (and the MCP tool result it feeds) never receives the array.

The embedding is computed in the DB writer, not stored in the durability mirror. `_replay` re-UPSERTs the mirrored fields verbatim, so a decision written during a primary outage lands without an embedding on reconcile and is searchable only after a `reindex-embeddings` pass, the same property memory embeddings have had since ADR-0016. `reindex-embeddings` (CLI and `DatabaseClient.reindex_embeddings`) backfills any decision or memory row whose `embedding` is `NONE`, reading only the id and the fields it needs and pre-filtering the non-semantic memory categories so it never re-fetches indexed file content. It is additive and idempotent, so it needs no single-driver lock, and it is the path that indexes the decisions written before this change.

### Consequences

- Positive: decisions become searchable, lexically today and semantically once a reviewed model embedder is registered; the config selects among vetted embedders with no code-execution surface; the dependency-free offline default and the existing memory behavior are unchanged.
- Negative: a real semantic embedder still requires an out-of-tree model, a registry entry, and a manual index rebuild plus reindex when its dimension differs from 256; the lexical default only matches on shared tokens; an outage-written decision needs a manual reindex to enter the vector index.
- Neutral: `models.embedding` gains meaning as a registry selector without changing the default; the two vector indexes now derive their dimension from the embedder rather than a module constant.
