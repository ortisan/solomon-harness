# Big Data Processing

Choosing and using the right engine for data that outgrows a single pandas process: DuckDB on one machine as the default, Spark 4.x when the data or the organization is genuinely distributed, ClickHouse MergeTree for interactive analytics on billions of rows. The stance: shuffles and small files are where distributed jobs die, so design partitioning first and treat every wide transformation as a cost to justify. Cluster provisioning and database server tuning are `sre`/`dba` handoffs; this skill covers how the analyst structures data and queries on these engines.

## When DuckDB is enough

If the working set fits on one modern machine's NVMe — in practice, up to a few hundred GB of Parquet — DuckDB 1.x beats a cluster on latency, cost, and debuggability. It is in-process, spills to disk for larger-than-RAM joins and sorts, reads Parquet/CSV/S3 directly, and speaks standard SQL with `QUALIFY` and window functions. Reach for Spark only when data volume, an existing lakehouse, or scheduled multi-tenant pipelines demand it. "We might need scale later" is not a reason to pay cluster overhead today.

```sql
-- DuckDB over a partitioned lake path, no cluster involved
SELECT sku, SUM(qty) FROM read_parquet('s3://lake/orders/dt=2026-06-*/*.parquet')
GROUP BY sku;
```

## Spark 4.x execution model

Spark 4 (ANSI SQL mode on by default — division by zero and overflow now raise instead of returning NULL, so legacy pipelines that relied on silent NULLs fail loudly; the `VARIANT` type handles semi-structured JSON) runs a driver that compiles your plan into jobs, stages, and tasks executed on executors. The unit of thinking is the **stage boundary**: narrow transformations (filter, map, column projection) pipeline within a stage; wide ones (join, groupBy, distinct, repartition) force a **shuffle** — every executor writes sorted blocks to disk and every other executor pulls them over the network. Most Spark performance work is removing or shrinking shuffles:

- Filter and project before joins and aggregations; let predicate pushdown reach the Parquet reader (check with `df.explain()` that `PushedFilters` is populated).
- Broadcast small dimension tables: below `spark.sql.autoBroadcastJoinThreshold` (default 10 MB) Spark does it automatically; hint larger ones explicitly with `broadcast(dim)` up to a few hundred MB if executors have the memory. A broadcast join removes the shuffle entirely.
- Adaptive Query Execution (AQE, on by default) re-plans at runtime: it coalesces the default 200 shuffle partitions to fit the actual data, splits skewed partitions in sort-merge joins, and converts to broadcast joins when a side turns out small. Leave it on; it makes hand-tuning `spark.sql.shuffle.partitions` mostly obsolete, but it cannot fix a join key where one value holds 40% of rows — pre-aggregate or salt that key yourself.
- `repartition(n)` shuffles; `coalesce(n)` only merges partitions and cannot increase parallelism. Writing output, aim for 128 MB-1 GB files: thousands of KB-sized files ("small files problem") slow every subsequent reader and the driver's file listing.

Partition the lake by low-cardinality query predicates — almost always a date column (`dt=2026-07-04`), sometimes plus region. Never partition by user_id or other high-cardinality keys: millions of directories destroy listing performance.

## ClickHouse MergeTree design

ClickHouse 25.x serves sub-second aggregations over billions of rows when the table is designed for the queries:

```sql
CREATE TABLE events (
    dt Date, ts DateTime('UTC'), tenant LowCardinality(String),
    user_id UInt64, event String, amount Decimal(18,2)
) ENGINE = MergeTree
PARTITION BY toYYYYMM(dt)
ORDER BY (tenant, event, ts);
```

- `ORDER BY` is the primary index: order columns from lowest to highest cardinality, matching the WHERE prefixes of the dominant queries. It is not a uniqueness constraint.
- `PARTITION BY` month, not day, unless volume forces it; keep total partitions in the low hundreds. Partitions exist for pruning and TTL drops, not for sorting.
- Precompute hot aggregations with materialized views into `SummingMergeTree`/`AggregatingMergeTree` targets; dashboards then scan thousands of pre-aggregated rows instead of billions.
- `ReplacingMergeTree` dedup is eventual (at merge time); read with `argMax`/`FINAL` as covered in `sql_analytics`.
- Inserts must be batched (tens of thousands of rows per insert, or `async_insert=1`); row-at-a-time inserts create part explosions that stall merges.

Schema migrations, replication, and cluster sizing go to the `dba` agent.

## Common pitfalls

- Standing up Spark for 50 GB of Parquet that DuckDB or Polars handles on one machine in minutes.
- Joining two large tables on a skewed key and reading "one task ran 2 hours, 199 ran seconds" in the Spark UI; needs salting or pre-aggregation, not more executors.
- Writing output with default parallelism and producing tens of thousands of tiny files; every downstream job then pays the listing and open-file tax.
- Partitioning the lake or a MergeTree table by a high-cardinality key.
- Relying on pre-4.0 Spark behavior where `1/0` returned NULL; under ANSI mode the job now fails — guard with `try_divide`.
- ClickHouse `ORDER BY` chosen alphabetically or by "primary key habit" instead of by query predicate prefix, forcing full-part scans.
- Single-row inserts into MergeTree tables causing "too many parts" errors.
- `collect()` on a large DataFrame to "check it in pandas", flooding the driver; use `limit()` or write to Parquet and sample.

## Definition of done

- [ ] Engine choice is justified by data size and access pattern in one sentence in the PR or script header; single-node options were considered first.
- [ ] For Spark jobs: `explain()` reviewed — predicate/projection pushdown confirmed, join strategies named, no unexpected shuffle stages; AQE left enabled.
- [ ] Skew checked on every large join key (top-k value frequencies) and mitigated where one key exceeds a few percent of rows.
- [ ] Output files land in the 128 MB-1 GB range; no small-files regression in the target path.
- [ ] Lake and MergeTree partitioning use low-cardinality time-based keys; ClickHouse `ORDER BY` matches dominant query predicates, lowest cardinality first.
- [ ] Hot dashboard aggregations are served by materialized views or pre-aggregated tables, not repeated full scans.
- [ ] Inserts to ClickHouse are batched; no per-row insert path exists.
- [ ] Results reconcile with a small-scale reference run (same query on a sampled extract in DuckDB) before the distributed number is published.
- [ ] Infrastructure changes (cluster size, replication, server settings) are handed to `sre`/`dba`, not embedded in job code.
