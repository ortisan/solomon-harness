# Connection Pooling and Resource Management

How to keep PostgreSQL healthy under many clients: why connection count must stay low, PgBouncer pooling modes and their semantics, the pool sizing arithmetic, and the memory settings that decide whether the server is fast or getting OOM-killed. The stance: connections are a scarce server resource multiplexed by a pooler, and every memory setting is derived from a worst-case product, not copied from a blog.

## Why pooling is not optional

Each PostgreSQL connection is an operating-system process holding several MB of backend-local memory plus caches that grow with catalog size; hundreds of active backends also contend on locks and scheduler time. Throughput on a typical box peaks at a small multiple of the core count of active connections and degrades beyond it. Setting `max_connections = 5000` does not add capacity; it adds ways to collapse. Keep `max_connections` modest (100 to 300 on typical instances) and put a pooler in front.

Sizing heuristic for the server-side pool (from the PostgreSQL wiki, same reasoning HikariCP documents): active connections around `(cores x 2) + effective_spindles`. An 8-vCPU NVMe instance saturates around 20 to 30 active server connections; thousands of application clients then share those via the pooler. Validate with a load test: raise the pool until throughput stops improving, then stop, because past that point latency rises with no throughput gain.

## PgBouncer modes

PgBouncer (1.24+ current) is the house default: single lightweight process, tiny per-connection overhead.

| Mode | Server connection held | Multiplexing | Breaks |
| --- | --- | --- | --- |
| `session` | For the client's whole session | None (1:1 while connected) | Nothing; only useful to absorb connect storms |
| `transaction` | Per transaction | High | Session state across transactions |
| `statement` | Per statement | Highest | Multi-statement transactions; niche |

Transaction mode is the default choice. What it breaks, and the remedies:

- Session-level state does not survive: `SET` (use `SET LOCAL` inside the transaction), advisory locks held across transactions (use transaction-scoped `pg_advisory_xact_lock`), `LISTEN/NOTIFY` (needs a dedicated session-mode connection), temp tables and cursors `WITH HOLD` across transactions.
- Prepared statements historically broke transaction mode; PgBouncer 1.21+ tracks protocol-level prepared statements when `max_prepared_statements` is set (for example 200). Verify your driver uses protocol-level prepare (psycopg 3, JDBC do); SQL-level `PREPARE` still breaks.
- Do not use `server_reset_query` (`DISCARD ALL`) in transaction mode; it belongs to session mode.

Key parameters, with intent:

```ini
[databases]
app = host=127.0.0.1 port=5432 dbname=app

[pgbouncer]
pool_mode = transaction
default_pool_size = 20        ; server conns per user+database pair
min_pool_size = 5             ; keep warm
reserve_pool_size = 5         ; burst headroom after reserve_pool_timeout
max_client_conn = 2000        ; client side; cheap
max_db_connections = 40       ; hard cap per database across pools
server_idle_timeout = 600
query_wait_timeout = 30       ; fail fast instead of queueing forever
max_prepared_statements = 200
```

The invariant: the sum of every pool's possible server connections (all poolers, all `default_pool_size` + reserves, plus superuser/migration/cron connections) must stay below `max_connections` with headroom (`superuser_reserved_connections` defaults to 3). PgBouncer is single-threaded; one process saturates around one CPU core, so at very high throughput run multiple instances on the same port with `so_reuseport = 1`.

Application-side pools (HikariCP, SQLAlchemy `pool_size`) still exist under PgBouncer; keep them small and let PgBouncer do the multiplexing. Two fat layers of pooling multiply into the same oversubscription you were avoiding.

## Server memory: derive, do not guess

- `shared_buffers`: about 25 percent of RAM (default 128MB is a toy value). Beyond ~40 percent returns diminish because PostgreSQL also relies on the OS page cache. Requires restart.
- `effective_cache_size`: planner hint, not an allocation; set to 50 to 75 percent of RAM so index plans are costed realistically.
- `work_mem`: per sort/hash node, per backend, concurrently. A single query can use several multiples. Derive from the worst case: with 200 possible active backends and ~2 heavy nodes each, `work_mem = 64MB` exposes you to 25 GB. Safe pattern: a conservative global (4 to 16 MB) plus `SET LOCAL work_mem = '256MB'` for the known heavy queries, or a raised setting on the reporting role only (`ALTER ROLE reporting SET work_mem = '128MB'`).
- `maintenance_work_mem`: for `VACUUM`, `CREATE INDEX`, FK validation; 512MB to 2GB is reasonable on real hardware since few run concurrently (`autovacuum_work_mem` caps each autovacuum worker separately).
- `huge_pages = try` on Linux for large `shared_buffers`; measurable TLB savings.
- PostgreSQL 18 introduces asynchronous I/O (`io_method = worker` by default, `io_workers` to size it); it changes read-path behavior, so re-baseline I/O-bound benchmarks after upgrading rather than carrying old numbers forward.

Guard the server with timeouts: `idle_in_transaction_session_timeout = '5min'` (an idle-in-transaction session pins vacuum's xmin horizon and holds locks), `statement_timeout` set per application role (not globally, or migrations and backups die), `idle_session_timeout` (PG14+) for abandoned sessions, and `tcp_keepalives_idle` so dead clients get reaped.

MySQL note: connections are threads, not processes, so raw connection count hurts less; the pressing pooling reason there is failover behavior and per-thread buffers, and the decision framework (small active set, derive memory from products) still applies.

## Common pitfalls

- "Fixing" connection errors by raising `max_connections`, converting a queueing problem into a memory and contention problem.
- Transaction pooling deployed while the application relies on session `SET`, session advisory locks, or SQL-level `PREPARE`; symptoms are intermittent and maddening.
- `work_mem` raised globally to make one report fast; the next traffic spike OOM-kills the server.
- Sum of all pools and cron/migration connections exceeding `max_connections`; deploys fail at the worst moment.
- No `query_wait_timeout`/client timeout: during an incident every client queues forever and the outage propagates upstream.
- One PgBouncer process pinned at 100 percent CPU acting as the invisible bottleneck; nobody looks at the pooler's own saturation.
- Leaving `idle_in_transaction_session_timeout` unset; one stuck app thread quietly disables vacuum for the whole cluster.

## Definition of done

- [ ] `max_connections` is modest and justified; a pooler fronts every application path to the database.
- [ ] Pool mode is chosen against the application's session-state usage, with the incompatibility checklist (SET, advisory locks, LISTEN, PREPARE) explicitly cleared; `max_prepared_statements` set where drivers prepare.
- [ ] Pool sizes derive from the cores-based formula and a load test; the summed worst case of all pools stays under `max_connections` with reserved headroom.
- [ ] `shared_buffers`, `effective_cache_size`, `work_mem`, and `maintenance_work_mem` are derived from RAM and concurrency products, with the arithmetic recorded; heavy queries get scoped `work_mem`, not a global raise.
- [ ] Timeouts configured: `idle_in_transaction_session_timeout`, per-role `statement_timeout`, `query_wait_timeout` on the pooler.
- [ ] Pooler saturation (CPU, `cl_waiting`, pool usage) and backend memory are monitored and alerted.
- [ ] Any change was validated under production-shaped load, with before/after latency and throughput recorded.
