---
name: indexing-strategies
description: Guides choosing, shaping, and retiring PostgreSQL indexes: access method per workload, multicolumn ordering, partial, covering, and expression indexes, and the write amplification every index costs. Use when adding, reviewing, or removing an index, or when `EXPLAIN` skips the expected index.
---

# Indexing Strategies

How to choose, shape, and retire indexes in PostgreSQL: the right access method per workload, multicolumn ordering, partial/covering/expression indexes, the selectivity arithmetic that decides whether an index pays, and the write amplification every index costs. The stance: an index is a purchase, paid for on every write and every vacuum, so each one must be justified by a named query and re-verified with `EXPLAIN` after creation.

## Access methods: pick by operator, not habit

| Method | Serves | Typical use | Notes |
| --- | --- | --- | --- |
| B-tree | `=`, `<`, `>`, `BETWEEN`, `ORDER BY`, `LIKE 'abc%'` | Default for almost everything | Deduplication since PG13 shrinks low-cardinality indexes; PG18 adds skip scan for multicolumn prefixes |
| Hash | `=` only | Long keys where only equality matters | WAL-logged and crash-safe since PG10; rarely beats B-tree, but smaller/faster for wide text keys |
| GIN | Containment: `@>`, `?`, `&&`, full-text `@@` | `jsonb`, arrays, tsvector, trigram search | Slow to update; `fastupdate` pending list (default cap `gin_pending_list_limit` = 4 MB) defers cost to vacuum |
| GiST | Overlap/nearest: `&&`, `<->` | Ranges, geometry, exclusion constraints, KNN | The only method usable by `EXCLUDE` constraints on ranges |
| BRIN | Range predicates on physically correlated columns | Append-only time-series (`created_at`) | Stores min/max per block range (`pages_per_range` default 128); megabytes where a B-tree is tens of GB |
| SP-GiST | Non-balanced structures | Prefix/text routing, points | Niche; measure against GiST |

BRIN only works when physical row order correlates with the column (check `pg_stats.correlation` near 1.0); after heavy updates the correlation decays and BRIN degrades to near-useless.

## Shaping the index

- Multicolumn order: equality columns first, then the range/sort column. For `WHERE tenant_id = $1 AND created_at > $2 ORDER BY created_at DESC`, the index is `(tenant_id, created_at DESC)`. A B-tree serves leftmost prefixes; `(a, b)` supports `a` alone but historically not `b` alone. PostgreSQL 18's skip scan can use `(a, b)` for `b`-only predicates when `a` has few distinct values, but do not design for it: order deliberately.
- Partial indexes encode the hot predicate and shrink the index by excluding cold rows:

```sql
CREATE INDEX CONCURRENTLY idx_orders_pending
  ON orders (created_at)
  WHERE status = 'pending';
```

  The query must contain a predicate the planner can prove implies `status = 'pending'`, or the index is ignored. Partial unique indexes also express conditional uniqueness (`UNIQUE ... WHERE deleted_at IS NULL`).
- Covering indexes (`INCLUDE`, PG11+) add non-key payload columns so the query becomes an Index Only Scan: `CREATE INDEX ON orders (customer_id) INCLUDE (status, total_cents)`. Index-only scans still consult the visibility map; a poorly vacuumed table shows large `Heap Fetches` and loses the benefit.
- Expression indexes serve computed predicates and give the planner statistics on the expression: `CREATE INDEX ON users (lower(email))` matches only `WHERE lower(email) = $1` written exactly that way.
- Operator classes matter: `text_pattern_ops` for `LIKE 'prefix%'` under non-C collations; `gin_trgm_ops` (pg_trgm) for `%infix%` search.

## The selectivity arithmetic

An index scan does random heap I/O; a sequential scan does cheap streaming I/O. The planner's crossover point depends on `random_page_cost` (default 4.0; set 1.1 on SSD/NVMe). Working rules:

- An index earns a plain Index Scan when the predicate selects roughly under 1 to 5 percent of rows. At 20 percent selectivity, expect a bitmap scan or a seq scan, and that is correct.
- Compute expected rows honestly: a status column with 4 values at 25 percent each is not indexable on its own; the same column as a partial-index predicate over the 0.1 percent `pending` slice is excellent.
- `n_distinct` and MCV lists in `pg_stats` tell you what the planner believes; if its belief is wrong, fix statistics before adding indexes.
- Index-only scans change the arithmetic: if the index covers the whole query, even low selectivity can pay because no heap visits happen.

## Write amplification: what each index costs

Every `INSERT` writes one entry into every index on the table; a 10-index table does 11 structure writes per row plus WAL for each. Two second-order costs matter more:

- HOT updates. An `UPDATE` that modifies no indexed column and fits on the same page skips all index maintenance. Indexing a frequently updated column (for example `updated_at`) defeats HOT for every update of the table and can multiply write I/O. Check `pg_stat_user_tables.n_tup_hot_upd` versus `n_tup_upd`; lower `fillfactor` (e.g. 90) on update-heavy tables to preserve HOT headroom.
- Vacuum and bloat. Each index must be scanned by vacuum; churn-heavy B-trees bloat and need `REINDEX CONCURRENTLY`.

Retire what does not earn its keep: `SELECT indexrelid::regclass, idx_scan FROM pg_stat_user_indexes WHERE idx_scan = 0` observed across a full business cycle (statistics reset on major upgrade and `pg_stat_reset()`, so check the window). Drop duplicates and leftmost-prefix redundancies (`(a)` is redundant next to `(a, b)` unless it is much smaller and hot).

MySQL/InnoDB differences that change decisions: the table is a clustered index on the PK, so every secondary index stores the PK as its row pointer; a wide PK amplifies every index, which argues for compact PKs. Secondary lookups are a double B-tree descent, so covering indexes pay off even more than in PostgreSQL. Functional indexes exist only from 8.0.13, and there are no partial indexes; the workaround is generated columns.

## Common pitfalls

- Indexing low-cardinality columns whole (`status`, booleans) instead of using partial indexes on the hot slice.
- Wrong multicolumn order (range column first), forcing filters instead of index conditions; verify with `EXPLAIN` that the predicate appears as `Index Cond`, not `Filter`.
- Expression mismatch: index on `lower(email)`, query on `email = $1`; the index is never used.
- Adding an index and never confirming the planner chose it; dead weight on every write.
- Indexing the column that every update touches, silently killing HOT updates.
- BRIN on a table whose physical order no longer correlates with the column.
- GIN on a high-write table without accounting for the pending-list flush latency spikes.
- Counting on the 4096-row staging table to predict production plan choice; selectivity decisions need production-scale statistics.

## Definition of done

- [ ] Each new index names the exact production query (or constraint) it serves, with `EXPLAIN (ANALYZE, BUFFERS)` before and after showing it used as an `Index Cond`.
- [ ] Access method chosen by operator and data shape, with the reason stated (B-tree default; GIN/GiST/BRIN/hash justified).
- [ ] Multicolumn order is equality-first then range/sort; partial predicates match the query text provably.
- [ ] Selectivity estimated from `pg_stats` (not guessed); indexes on low-selectivity whole columns rejected or made partial.
- [ ] Write cost assessed: HOT-update impact checked on update-heavy tables; total index count on the table justified.
- [ ] Created with `CREATE INDEX CONCURRENTLY` on live tables; invalid leftovers checked and cleaned.
- [ ] Unused/duplicate indexes reviewed as part of the change; removals scheduled with the same rigor as additions.
