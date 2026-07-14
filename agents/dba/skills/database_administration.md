---
name: database-administration
description: Covers day-two PostgreSQL operations: role and privilege design, vacuum and autovacuum tuning, routine maintenance, and version upgrades, all expressed as declarative, reviewable configuration rather than ad-hoc superuser sessions. Use when designing roles, tuning autovacuum, or planning an upgrade.
---

# Database Administration

Day-two operations for PostgreSQL: role and privilege design, vacuum and autovacuum, routine maintenance, and minor/major version upgrades. The stance: administration is done through declarative, reviewable configuration and scheduled jobs, not ad-hoc superuser sessions; anything typed into `psql` in production should be re-expressible as code afterwards.

## Roles and privileges

Design roles as a two-layer model: group roles (NOLOGIN) own privileges, login roles inherit them.

```sql
CREATE ROLE app_read NOLOGIN;
CREATE ROLE app_write NOLOGIN;
GRANT USAGE ON SCHEMA app TO app_read, app_write;
GRANT SELECT ON ALL TABLES IN SCHEMA app TO app_read;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA app TO app_write;
ALTER DEFAULT PRIVILEGES FOR ROLE migrator IN SCHEMA app
  GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO app_write;

CREATE ROLE orders_svc LOGIN PASSWORD '...' IN ROLE app_write;
```

- Separate the migration role (DDL owner) from the runtime application role (DML only). The application role must not own tables; ownership implies the right to drop them and to bypass row-level security unless forced.
- `ALTER DEFAULT PRIVILEGES` must name the role that will create future objects (the migrator), or new tables silently arrive without grants: the classic "permission denied after deploy" incident.
- Superuser is for the DBA break-glass path only, never for applications or migration pipelines. PostgreSQL 15+ already revokes `CREATE` on the `public` schema from `PUBLIC`; on older clusters do it explicitly.
- Prefer `SET ROLE`-based elevation with logging over shared admin accounts; every human gets an individual login role.

## Vacuum and autovacuum

MVCC means every `UPDATE`/`DELETE` leaves a dead tuple; vacuum reclaims them and, critically, freezes old transaction IDs to prevent wraparound. Autovacuum defaults are sized for small tables and must be tuned per large table:

- Default trigger is `autovacuum_vacuum_scale_factor = 0.2` (plus 50 rows): on a 500M-row table that is 100M dead tuples before vacuum starts. Set hot large tables to a fraction of a percent:

```sql
ALTER TABLE events SET (
  autovacuum_vacuum_scale_factor = 0.01,
  autovacuum_analyze_scale_factor = 0.005
);
```

- Throughput is capped by cost-based throttling (`autovacuum_vacuum_cost_delay`, default 2 ms since PostgreSQL 12, and `vacuum_cost_limit`, default 200). If `n_dead_tup` grows while autovacuum runs, raise `autovacuum_vacuum_cost_limit` (or reduce the delay) and consider more `autovacuum_max_workers` (default 3) with the caveat that workers share the cost budget. PostgreSQL 17 rebuilt the dead-tuple store (TidStore), removing the old 1 GB memory ceiling and cutting vacuum memory use roughly 20x, which makes aggressive settings cheaper.
- Monitor: `pg_stat_user_tables` (`n_dead_tup`, `last_autovacuum`), `pg_stat_progress_vacuum` for running jobs, and wraparound risk:

```sql
SELECT datname, age(datfrozenxid) FROM pg_database ORDER BY 2 DESC;
```

  Alert when `age(datfrozenxid)` passes ~1 billion (hard stop near 2.1 billion; `autovacuum_freeze_max_age` defaults to 200 million). A wraparound-forced shutdown is the worst routine failure PostgreSQL has; it is entirely preventable by watching this number.
- Long-running transactions, abandoned replication slots, and `idle in transaction` sessions all pin the xmin horizon and make vacuum useless while they live. Set `idle_in_transaction_session_timeout` (for example `5min`) and alert on old xmin holders.
- `VACUUM FULL` rewrites the table under `ACCESS EXCLUSIVE`; on live systems use `pg_repack` (or `pg_squeeze`) to compact bloat online instead.

## Routine maintenance

- `ANALYZE` after bulk loads; autovacuum handles steady state.
- Index health: B-tree bloat accumulates on churn-heavy tables; rebuild online with `REINDEX INDEX CONCURRENTLY` (PostgreSQL 12+). Detect corruption proactively with `amcheck` on replicas.
- Track unused indexes (`pg_stat_user_indexes.idx_scan = 0` over a full business cycle) and drop them; each one taxes every write and vacuum.
- Checkpoints: size `max_wal_size` so checkpoints are time-driven (`checkpoint_timeout`, with `checkpoint_completion_target` defaulting to 0.9) rather than WAL-volume-driven; `log_checkpoints = on` (default since 15) and investigate frequent "checkpoints are occurring too frequently" warnings.
- Keep `log_autovacuum_min_duration`, `log_lock_waits`, and `log_temp_files = 0` on; these three log lines explain most mystery slowdowns.

## Upgrades

- Minor versions (17.4 to 17.5): binary swap plus restart, no data format change. Apply within days of release; minors are exclusively bug, corruption, and security fixes. Read the release notes for the rare post-update step (for example a required `REINDEX` on specific index types).
- Major versions: plan around `pg_upgrade`. Run `pg_upgrade --check` first; use `--link` (hard links, seconds of downtime, no extra disk, but no going back once the new cluster starts) or `--clone` where the filesystem supports it. PostgreSQL 18 adds `--swap` and preserves planner statistics across the upgrade; on 17 and earlier, run `ANALYZE` (staged via `vacuumdb --analyze-in-stages`) immediately after, because the new cluster starts with empty statistics and terrible plans.
- For near-zero-downtime major upgrades, use logical replication: replicate into a new-version cluster (`pg_createsubscriber` on 17+ can convert a physical standby), verify, then cut over connections.
- Extensions upgrade separately (`ALTER EXTENSION ... UPDATE`); verify each extension supports the target major before scheduling.
- Always rehearse the upgrade on a restored production backup, with timings; the rehearsal doubles as a restore drill.

## Common pitfalls

- Application connecting as the table owner or superuser; one SQL injection away from `DROP TABLE`, and RLS silently bypassed.
- Missing `ALTER DEFAULT PRIVILEGES`, so the first post-deploy query fails with "permission denied" on a brand-new table.
- Autovacuum left at defaults on a billion-row table, then "fixed" by disabling it, which converts bloat into a wraparound emergency.
- An abandoned replication slot or a days-old `idle in transaction` session pinning xmin; vacuum runs constantly and reclaims nothing.
- `VACUUM FULL` on a live table to fix bloat, taking the application down for the duration.
- Major upgrade executed without `pg_upgrade --check` or without the post-upgrade `ANALYZE` (pre-18), producing a day of pathological plans.
- Skipping minor updates for months, then hitting a data-corruption bug fixed three point releases ago.

## Definition of done

- [ ] Privileges flow through NOLOGIN group roles; migration and runtime roles are separate; no application uses superuser or owns tables.
- [ ] `ALTER DEFAULT PRIVILEGES` covers every schema and object-creating role; grants are in versioned migration code.
- [ ] Large/hot tables have per-table autovacuum settings; cost limits tuned so vacuum keeps pace under peak write load.
- [ ] Alerts exist for `age(datfrozenxid)` (warning at 1B), dead-tuple growth, last-autovacuum staleness, long transactions, and stale replication slots.
- [ ] Bloat remediation uses `pg_repack`/`REINDEX CONCURRENTLY`; no `VACUUM FULL` on live tables.
- [ ] Minor updates applied on a defined cadence; major upgrades rehearsed on a restored backup with measured downtime and a written rollback point.
- [ ] Post-upgrade statistics step (pre-18) and extension updates are in the runbook, not in someone's head.
