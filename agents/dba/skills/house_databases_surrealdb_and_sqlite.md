# House Databases: SurrealDB and SQLite

Operating this project's memory store: a SurrealDB primary with a SQLite fallback, implemented in `solomon_harness/tools/database_client.py`. The stance: the shared SurrealDB is the source of truth, the SQLite fallback exists so a backend outage never blocks or loses a write, and every divergence between them is reconciled deliberately, never left to drift. Everything below is grounded in the code; do not invent flags or paths that are not in it.

## Backend selection and tenancy

`DatabaseClient` reads the `database` block of `.agent/config.json` (harness-local first, project root as fallback): `provider`, `url` (default `ws://localhost:8000/rpc`), `namespace` (default `solomon`), `database`, plus `busy_timeout_seconds` and `connect_timeout_seconds` (both default 5.0). Environment overrides win: `SURREAL_URL`, `SURREAL_USER`, `SURREAL_PASS`.

- One shared SurrealDB serves every project on the machine; each project is a tenant. When the configured database is the `harness` sentinel (or empty), the client derives an `<owner>-<repo>` name from the git remote, so two projects never share a database inside the `solomon` namespace.
- Credentials fail closed: a local URL (`localhost`, `127.0.0.1`, `0.0.0.0`) defaults to `root`/`root`; a non-local URL with no credentials is refused and the client falls back to SQLite rather than guessing.
- An explicit `db_path` argument or `HARNESS_DB_PATH` forces the SQLite backend outright; that is the test/sandbox isolation convention, and the write-through mirror then lives beside that path instead of in the repo.

## Running the SurrealDB backend

The backend is defined once per machine in `~/.solomon-harness/docker-compose.yml`:

- Image pinned to `surrealdb/surrealdb:v3.1.5` (the Python SDK is `surrealdb>=2.0.0,<3.0.0`, which speaks the v2/v3 protocol); container `solomon_surrealdb`; storage `rocksdb:/data/solomon.db` on the `./memory/surrealdb` volume; 512 MB memory limit with a 256 MB RocksDB block cache; a `surreal isready` healthcheck. A Surrealist UI container listens on host port 3000.
- The container listens on 8000 internally; the host port is auto-assigned (8099 preferred, next free port otherwise) and recorded in `~/.solomon-harness/memory.json` under `host_port`. Never hardcode 8099 in tooling; read the record.
- Lifecycle: `solomon-harness memory-up` (idempotent; `--wait N`, default 25 s, for the port to serve) and `solomon-harness memory-down`. The Claude Code SessionStart hook runs `memory-up` automatically. `solomon-harness healthcheck` reports Docker, memory backend, and pending-initialization state; `db-init` initializes tables.

## Schema: one multi-model database

The bootstrap defines, all `IF NOT EXISTS` and `SCHEMALESS`: record tables (`decisions`, `memory`, `milestones`, `issues`, `backtest_runs`, `sessions`, `handoffs`, `releases`, `loop_runs`, `metrics`), graph `RELATION` tables (`blocks`, `supersedes`, `contains`, `produced`, `addresses`), indexes (`issues.github_id` UNIQUE, `issues.status`, `decisions.created_at`, composite `metrics (name, time)` for the timeseries), and an HNSW vector index on `memory.embedding` with `DIMENSION 256, DIST COSINE, TYPE F32`. The dimension must match `EMBEDDING_DIM` and the default `HashingEmbedder`, which is lexical (feature hashing), not semantic; a model-backed embedder can be swapped in via the `embedder` parameter but must emit 256-dim vectors or the index definition must change with it.

Operationally important quirk: the SDK's `query()` surfaces only the first statement's result, so the client executes one DDL statement per call; keep that pattern for any schema change, or a failing later statement is silently swallowed.

## Resilience and the SQLite fallback

Public write/read methods are wrapped by `@_resilient`. A failure is classified as a transport fault only by exception type (SDK/websocket connection classes, `ConnectionError`/`OSError`) or a narrow set of anchored message markers ("no close frame", "connection reset", and similar); query and data errors propagate unchanged and never trigger recovery. On a transport fault the client attempts exactly one reconnect, run in a worker thread joined at the connect deadline so a half-open socket cannot hang the session, then retries the call once; if that fails it activates the SQLite fallback loudly on stderr and serves the call from SQLite.

The SQLite store lives at `<repo>/memory/long_term/harness.db` (or `HARNESS_DB_PATH`). Connections use WAL journal mode with the configured busy timeout for multi-agent concurrency, and set `PRAGMA foreign_keys = ON` per connection because SQLite defaults it off. Schema changes there are in-place expand/contract migrations guarded by `PRAGMA table_info` checks and tolerant of concurrent first-opens.

## Durability: the write-through mirror and reconcile

Every write also lands as Markdown under `.solomon/memory-mirror/<kind>/<id>.md` (precedence: explicit `mirror_root`, `HARNESS_MIRROR_ROOT`, beside an explicit SQLite path, then the repo default). The file is stamped `synced: false` before the DB attempt and re-stamped `true` only if the write reached the SurrealDB primary. Ids are client-minted (`<kind>-<UTC stamp>-<short uuid>`) and double as the SurrealDB record id, so replay is a deterministic UPSERT that never duplicates; deletions replay as DELETE tombstones so removed records stay removed.

After any outage, replay with `solomon-harness memory sync` (calls `DatabaseClient.reconcile()`, prints synced/pending counts; idempotent, stops cleanly on a mid-run drop). The separate `solomon-harness reconcile [--dry-run]` command is a different repair: it closes memory issue rows whose GitHub issue or parent resolved, and must run from a fresh process against the shared SurrealDB, not from a session already degraded to SQLite. Issue statuses are normalized on write to the ADR-0006 vocabulary, and the terminal-status predicate binds its literals as query parameters, never string formatting; keep both properties intact in any change.

The same store is exposed as the `solomon-memory` MCP server (`python -m solomon_harness.mcp_server`), registered in `.mcp.json` and `.gemini/settings.json`.

## Common pitfalls

- Writing memory from a session that silently fell back to SQLite and never running `memory sync`; the shared primary now disagrees with local state.
- Assuming the backend is on port 8099 instead of reading `~/.solomon-harness/memory.json`; on machines where 8099 was taken, tooling points at the wrong port.
- Concatenating multiple SurrealQL statements into one `query()` call; only the first result is checked, so later failures pass silently.
- Treating a SurrealQL query/data error as a connection problem and adding it to the fallback path; the classification is deliberately narrow so real errors surface.
- Changing `EMBEDDING_DIM` or the embedder without redefining the HNSW index (or the reverse); vector search degrades or errors.
- Expecting semantic similarity from the default `HashingEmbedder`; it measures token overlap only.
- Bypassing the mirror by writing to SurrealDB directly (raw SDK calls); an outage then loses exactly those writes.
- Running `solomon-harness reconcile` from a degraded session or a dirty worktree with a modified client; repair must come from a clean checkout on the primary.

## Definition of done

- [ ] Backend and tenant confirmed before writes: the client reports `surrealdb` and the derived tenant database, or the SQLite degradation is acknowledged and a `memory sync` is planned.
- [ ] Any schema change follows the house pattern: `IF NOT EXISTS`, one statement per `query()` call, dimension constants kept in lockstep with index definitions.
- [ ] Writes go through `DatabaseClient` (or the MCP tools) so the write-through mirror and minted-id UPSERT semantics apply; no raw side-channel writes.
- [ ] After any outage or fallback, `solomon-harness memory sync` runs and reports zero pending; residuals are investigated, not ignored.
- [ ] Status writes use the canonical vocabulary and parameterized predicates; no string-formatted status literals.
- [ ] Port, credentials, and paths read from their sources of record (`memory.json`, config, env overrides), never hardcoded.
- [ ] Test and sandbox work uses `HARNESS_DB_PATH`/`HARNESS_MIRROR_ROOT` isolation so real project memory is never touched.
