---
name: database-migrations
description: Standardizes evolving schemas on live systems without downtime: expand-contract as the default pattern, lock-aware DDL, batched backfills, and disciplined use of migration tools such as Alembic. Use when writing, reviewing, or planning a schema migration on a production or live database.
---

# Database Migrations

A standard for evolving schemas on live systems without downtime: expand-contract as the default pattern, lock-aware DDL, batched backfills, and disciplined use of migration tools such as Alembic. The stance: a migration is production code executed exactly once under the worst possible conditions, so it is reviewed for locking behavior, rollback, and data volume, not just for correctness of the end state.

## Expand-contract (parallel change)

Never make a change that requires the application and schema to switch simultaneously. Split every breaking change into phases, each independently deployable and reversible:

1. Expand: add the new column/table/index alongside the old, nullable or with a safe default. Old code keeps working.
2. Migrate writes: deploy application code that writes both old and new (or a trigger that mirrors writes).
3. Backfill: copy historical data in batches (below).
4. Migrate reads: deploy code that reads the new location; verify with metrics or a comparison job.
5. Contract: drop the old column/table in a later release, after a soak period and after confirming nothing reads it (`pg_stat_user_tables`, log scans, code search).

Renames are expand-contract too: add the new name, dual-write, backfill, cut reads over, drop the old. An in-place `ALTER TABLE ... RENAME COLUMN` is instant in PostgreSQL but breaks every deployed reader at once.

## Locks: know what each DDL takes

Almost all `ALTER TABLE` forms take `ACCESS EXCLUSIVE`, which blocks reads and writes. What matters is how long they hold it:

- Metadata-only (fast even on huge tables): `ADD COLUMN` with a constant default (PostgreSQL 11+ stores the default in the catalog, no rewrite), `DROP COLUMN`, `SET DEFAULT`, widening `varchar(n)`.
- Full-table scan under lock (dangerous): `ADD COLUMN ... DEFAULT (volatile_fn())`, `SET NOT NULL` (pre-12 always; from 12 it can be skipped by an existing validated `CHECK (col IS NOT NULL)`; PostgreSQL 18 allows `NOT NULL ... NOT VALID` then `VALIDATE`), adding a `CHECK` or FK without `NOT VALID`.
- Full-table rewrite (worst): `ALTER COLUMN ... TYPE` for non-binary-coercible changes (e.g. `int` to `bigint`), `SET TABLESPACE`, `VACUUM FULL`.

The safe patterns:

```sql
-- Constraint without a long lock: add unvalidated, then validate.
ALTER TABLE orders ADD CONSTRAINT orders_amount_ck
  CHECK (amount_cents >= 0) NOT VALID;             -- brief lock only
ALTER TABLE orders VALIDATE CONSTRAINT orders_amount_ck;  -- SHARE UPDATE EXCLUSIVE; writes continue

-- Indexes: never plain CREATE INDEX on a live table.
CREATE INDEX CONCURRENTLY idx_orders_customer ON orders (customer_id);
```

`CREATE INDEX CONCURRENTLY` cannot run inside a transaction, scans the table twice, and on failure leaves an `INVALID` index that must be dropped and retried (check `pg_index.indisvalid`).

Even a fast `ACCESS EXCLUSIVE` request queues behind long-running transactions and then blocks everyone behind it. Always set a lock timeout and retry:

```sql
SET lock_timeout = '3s';
-- retry the DDL with backoff on failure, off-peak
```

MySQL differences that change the plan: DDL is not transactional (a multi-statement migration that fails midway leaves a half-applied state, so each step must be independently re-runnable), and large ALTERs use `ALGORITHM=INSTANT/INPLACE` where possible or an external tool (`gh-ost`, `pt-online-schema-change`) where not.

## Backfills: batch, throttle, observe

Never `UPDATE big_table SET new_col = ...` in one statement: it locks rows for the duration, generates one giant transaction of WAL, bloats the table, and can stall replicas.

```sql
-- Loop from the application or a DO block until 0 rows affected:
WITH batch AS (
  SELECT id FROM orders
  WHERE new_status IS NULL
  ORDER BY id
  LIMIT 10000
  FOR UPDATE SKIP LOCKED
)
UPDATE orders o SET new_status = o.status
FROM batch WHERE o.id = batch.id;
```

- Batch size 1,000 to 50,000 rows; commit each batch; sleep 10 to 100 ms between batches.
- Watch replication lag (`pg_stat_replication`) and dead tuples (`pg_stat_user_tables.n_dead_tup`) while it runs; pause when lag grows.
- Make the backfill idempotent and resumable (the `WHERE new_col IS NULL` predicate does this) so a crash mid-run costs nothing.
- Run backfills as data migrations separate from schema migrations, so a slow backfill never holds a deploy hostage.

## Tooling: Alembic and friends

Alembic (with SQLAlchemy 2.x) is the house default for Python services. Rules:

- One revision per PR; linear history (`alembic merge` only to resolve genuine parallel branches); never edit a migration that has run anywhere beyond a developer machine.
- Configure a `naming_convention` on `MetaData` so constraints get deterministic names; unnamed constraints make later drops guesswork.
- `alembic revision --autogenerate` is a draft generator, not an authority. It does not detect: renames of tables or columns (it emits drop-and-add, which destroys data), changes to `server_default` or column type unless `compare_server_default=True` / `compare_type=True` are enabled, `CHECK` constraints in most dialects, row data, views, triggers, functions, or sequences. Read and correct every autogenerated file.
- Provide a real `downgrade()` for schema steps; where a step is genuinely irreversible (dropped data), make `downgrade()` raise with an explanation rather than pretending.
- Use `op.execute()` with explicit SQL for the lock-safe patterns above (`NOT VALID`, `CREATE INDEX CONCURRENTLY` with `autocommit_block()`), because the high-level ops default to the naive forms.
- Test every migration against a production-shaped dataset (size and skew), not an empty database: run upgrade, downgrade, upgrade in CI.

## Common pitfalls

- A "quick" `ALTER TABLE` queued behind a long transaction, silently blocking all traffic to the table; no `lock_timeout` set.
- Autogenerated Alembic revision applied unread, converting a rename into a drop-and-add that deletes a column of data.
- `CREATE INDEX` (non-concurrent) on a large live table; writes blocked for the whole build.
- A failed `CREATE INDEX CONCURRENTLY` leaving an invalid index that still taxes every write.
- Single-statement backfill of millions of rows: replica lag, WAL burst, table bloat, lock pileups.
- Schema and application deployed as a lockstep switch instead of expand-contract; rollback of one side breaks the other.
- Down migrations that were never tested, discovered broken during an incident.
- On MySQL, assuming a failed multi-step migration rolled back; DDL there auto-commits per statement.

## Definition of done

- [ ] The change is decomposed into expand-contract phases, each deployable and reversible on its own.
- [ ] For every DDL statement, the lock taken and its expected hold time on production-sized data are stated in the PR.
- [ ] `lock_timeout` and a retry strategy wrap any `ACCESS EXCLUSIVE` DDL; indexes use `CONCURRENTLY`; constraints use `NOT VALID` + `VALIDATE`.
- [ ] Backfills are batched, throttled, idempotent, resumable, and monitored for replica lag; they live in separate data migrations.
- [ ] Autogenerated migrations were reviewed line by line; renames and type changes were hand-written.
- [ ] Upgrade-downgrade-upgrade passes in CI against a production-shaped dataset.
- [ ] The contract (drop) phase is scheduled with evidence that nothing reads the old structure.
