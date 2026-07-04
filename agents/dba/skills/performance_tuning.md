# Performance Tuning

A working method for diagnosing and fixing slow queries: find the offenders with `pg_stat_statements`, read the plan with `EXPLAIN (ANALYZE, BUFFERS)`, fix the estimate before fixing the query, and only then reach for indexes or configuration. The stance: tuning without a measurement is guessing, and a fix that is not verified against the same measurement is not a fix. PostgreSQL is the reference engine.

## Find the right query first

Enable `pg_stat_statements` (in `shared_preload_libraries`; it normalizes queries and aggregates statistics). The queries worth tuning are ranked by total cost to the system, not by worst single execution:

```sql
SELECT queryid, calls, round(total_exec_time::numeric, 0) AS total_ms,
       round(mean_exec_time::numeric, 1) AS mean_ms,
       rows, shared_blks_read, shared_blks_hit
FROM pg_stat_statements
ORDER BY total_exec_time DESC
LIMIT 20;
```

- High `total_exec_time` with low `mean_exec_time` means a cheap query called too often: fix the caller (caching, batching, N+1 elimination), not the plan.
- High `shared_blks_read` relative to `shared_blks_hit` means the working set misses cache: look at index-only scans, table bloat, or memory before rewriting SQL.
- Set `track_io_timing = on` and use `pg_stat_io` (PostgreSQL 16+) to attribute read time to backends, autovacuum, and checkpoints separately.
- Reset counters (`pg_stat_statements_reset()`) after a deploy so before/after comparisons are clean.

For queries that are slow only sometimes, load `auto_explain` with `auto_explain.log_min_duration = '500ms'` and `auto_explain.log_analyze = on` to capture the actual bad plan from production rather than reproducing an approximation.

## Reading EXPLAIN ANALYZE

Always run `EXPLAIN (ANALYZE, BUFFERS)` (PostgreSQL 18 includes `BUFFERS` by default with `ANALYZE`; on 17 and earlier request it explicitly). Read the plan bottom-up and look for these specific signals:

- Estimated versus actual rows. `rows=100` estimated against `rows=1,200,000` actual is the root cause of most bad plans: the join strategy and node order were chosen for a dataset that does not exist. Fix the statistics (next section) before anything else.
- `loops=N` multiplies everything. A nested loop whose inner index scan shows `actual time=0.05 loops=800000` costs 40 seconds, not 0.05 ms.
- `Rows Removed by Filter` large on a scan node means the index (or the scan) is not selective for this predicate; a partial or multicolumn index usually applies.
- `Sort Method: external merge Disk: 210400kB` means the sort spilled; either raise `work_mem` for that query (`SET LOCAL work_mem = '256MB'` inside the transaction) or eliminate the sort with an index matching the `ORDER BY`.
- `Hash Batches: 16` (greater than 1) is the hash-join equivalent of a spill.
- `Heap Fetches` on an Index Only Scan far above zero means the visibility map is stale: vacuum the table.
- Seq Scan is not inherently wrong. On a small table, or when the predicate selects more than a few percent of rows, it is the correct plan; do not index your way out of a query that reads most of the table.

## Statistics: fix the estimate

The planner is only as good as its statistics.

- `ANALYZE` runs via autovacuum, but after a bulk load or mass update run it explicitly.
- `default_statistics_target` is 100 (a 100-bucket histogram per column). For large tables with skewed columns raise it per column: `ALTER TABLE orders ALTER COLUMN status SET STATISTICS 1000; ANALYZE orders;`.
- Correlated columns break the planner's independence assumption (`WHERE city = 'Lisbon' AND country = 'PT'` is estimated as the product of two selectivities). Create extended statistics: `CREATE STATISTICS s_geo (dependencies, ndistinct, mcv) ON city, country FROM addresses; ANALYZE addresses;`.
- Expressions (`lower(email)`, `date_trunc('day', created_at)`) have no column statistics unless an expression index or extended statistics on the expression exists.
- Misestimates that survive good statistics usually mean the predicate is unplannable (function over a parameter, OR across tables); rewrite the query rather than fighting the planner with configuration.

## Fix in the right order

1. Rewrite the query: remove `SELECT *`, replace `OFFSET`-based pagination with keyset pagination (`WHERE (created_at, id) < ($1, $2) ORDER BY created_at DESC, id DESC LIMIT 50`), decompose OR-across-columns into `UNION ALL`, push `LIMIT` below joins where semantics allow.
2. Fix statistics as above.
3. Index precisely (see the indexing skill): match the predicate, the join key, and the sort in one index where possible.
4. Schema changes: partitioning for pruning, denormalization as a last resort.
5. Configuration: `random_page_cost = 1.1` on SSD/NVMe (the default 4.0 assumes spinning disks and biases against index scans), `effective_cache_size` at 50 to 75 percent of RAM, `work_mem` sized so that `max_connections x expected concurrent sort/hash nodes x work_mem` cannot exhaust memory.

Verify every fix against the same `pg_stat_statements` window and the same `EXPLAIN (ANALYZE, BUFFERS)`; record the before/after numbers in the PR.

MySQL notes: `EXPLAIN ANALYZE` exists from 8.0.18 and reads similarly; histograms are not maintained automatically (`ANALYZE TABLE ... UPDATE HISTOGRAM`), and the clustered-index storage model makes secondary-index lookups inherently a double lookup, which shifts more decisions toward covering indexes.

## Common pitfalls

- Tuning the query with the worst mean time while a 2 ms query called 50,000 times per minute dominates total load.
- Reading only the top line of `EXPLAIN ANALYZE` and missing `loops`, spills, or a 10,000x row misestimate deep in the plan.
- Adding an index for every slow query; each one taxes every write and may not even be chosen (check with `EXPLAIN` after creation, drop it if unused).
- Raising `work_mem` globally to silence one spilling query; it applies per sort/hash node per backend and is a common cause of OOM kills. Use `SET LOCAL` scoped to the offending transaction.
- Benchmarking against a hot cache or an empty staging dataset and shipping a plan that collapses on cold production data.
- `OFFSET 100000` pagination: the server still reads and discards every skipped row.
- Forgetting `ANALYZE` after bulk loads, then debugging the resulting nested-loop disaster as if it were an indexing problem.

## Definition of done

- [ ] The offending query was identified from `pg_stat_statements` by total cost, not anecdote.
- [ ] `EXPLAIN (ANALYZE, BUFFERS)` output is attached to the issue/PR, with the diagnosis naming the specific node and signal (misestimate, spill, loops, heap fetches).
- [ ] Row estimates are within roughly an order of magnitude of actuals after the fix, or the residual misestimate is explained.
- [ ] The fix followed the order query rewrite, statistics, index, schema, configuration, and the cheaper rungs were ruled out explicitly.
- [ ] Before/after numbers from the same measurement window are recorded; the regression test or benchmark is repeatable.
- [ ] No global memory or planner setting was changed to fix a single query without an ADR.
