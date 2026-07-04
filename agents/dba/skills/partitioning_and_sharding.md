# Partitioning and Sharding

When and how to split large tables: PostgreSQL declarative partitioning, partition pruning, retention by partition dropping, and the far more consequential decision of sharding across nodes. The stance: partitioning is a maintenance and lifecycle tool first and a query optimization second; sharding is an architecture commitment taken only after vertical scaling, replicas, and partitioning are demonstrably exhausted, because its complexity is permanent.

## When partitioning pays

Reach for partitioning when one of these is true, not merely when a table feels big:

- The table is large enough that vacuum, `ANALYZE`, or index rebuilds take hours (roughly beyond 100 GB or a few hundred million rows, workload-dependent).
- Data has a lifecycle: retention deletes by time. `DROP`/`DETACH` of a partition is a metadata operation; the equivalent `DELETE` of 200M rows generates WAL for days and bloats the table.
- Queries are overwhelmingly bounded by one dimension (time window, tenant), so pruning lets each query touch a small fraction of storage.

If none apply, a well-indexed single table is simpler and usually faster: partitioning adds planning overhead, per-partition locks, and operational moving parts.

## Declarative partitioning mechanics

```sql
CREATE TABLE events (
  id bigint GENERATED ALWAYS AS IDENTITY,
  tenant_id bigint NOT NULL,
  created_at timestamptz NOT NULL,
  payload jsonb,
  PRIMARY KEY (id, created_at)
) PARTITION BY RANGE (created_at);

CREATE TABLE events_2026_07 PARTITION OF events
  FOR VALUES FROM ('2026-07-01') TO ('2026-08-01');
```

- Methods: RANGE (time-series, the common case), LIST (tenant/region), HASH (spreading write hot spots when no natural range exists).
- The partition key must be part of every `PRIMARY KEY`/`UNIQUE` constraint on the parent; global unique indexes across partitions do not exist. This constrains identity design: composite PKs as above, or uniqueness enforced per partition plus application discipline. (MySQL has the same rule for partitioned tables.)
- Indexes created on the parent propagate to all partitions, including future ones. Foreign keys from partitioned tables to others work (PG12+); FKs pointing at a partitioned table require the referenced key to include the partition key.
- Retention: prefer `ALTER TABLE events DETACH PARTITION events_2025_06 CONCURRENTLY` (PG14+) then drop or archive; plain `DETACH`/`DROP` takes stronger locks on the parent.
- A `DEFAULT` partition catches stray rows, but a bloated default partition blocks adding overlapping ranges and hides data-quality bugs; monitor it and keep it empty.
- Automate partition creation and retention with pg_partman (premake future partitions, retention drops) or an equivalent scheduled job; a missing next-month partition is a write outage at midnight on the first.
- Keep partition counts sane: hundreds to low thousands. Planning time, locking, and cache pressure grow with partition count (much better since PG12, still not free). Daily partitions on a 10-year retention table is 3,650 partitions of trouble; monthly is 120.

## Partition pruning: make queries eligible

Pruning removes partitions from the plan at plan time (constant predicates) or execution time (parameters, nested-loop join values, PG11+). `enable_partition_pruning` is on by default. To actually get it:

- The query must filter on the partition key with an operator the partitioning strategy understands: `WHERE created_at >= $1 AND created_at < $2` prunes; `WHERE date_trunc('day', created_at) = $1` does not, because the key is wrapped in a function.
- Verify with `EXPLAIN`: you should see only the surviving partitions (or `Subplans Removed: N` for execution-time pruning). A query scanning all partitions of a 500-partition table is slower than the unpartitioned equivalent.
- Joins between identically partitioned tables can use partitionwise join/aggregate (`enable_partitionwise_join`, `enable_partitionwise_aggregate`, both off by default; they raise planning cost, enable them deliberately for the workloads that benefit).

## Sharding: the last resort, done deliberately

Sharding distributes rows across independent database nodes. It buys write scalability and data locality at the price of losing what a single PostgreSQL gives for free: cross-shard transactions, joins, unique constraints, and simple backups. Exhaust the cheaper ladder first: bigger hardware, read replicas for read scale, partitioning plus archival for data volume, caching and queue-smoothing for write spikes.

When sharding is genuinely required:

- Choose the shard key first and expect never to change it cheaply. The right key appears in nearly every query and distributes load evenly; `tenant_id` is the canonical choice for B2B SaaS. A hot tenant on one shard recreates the original problem, so plan for either key hashing plus tenant pinning or tenant-level rebalancing.
- Prefer an existing layer over hand-rolled routing: Citus (distributed tables over PostgreSQL, colocation by shard key, reference tables for shared lookups) keeps SQL semantics for colocated queries; application-level sharding (a routing map from key to cluster) is simpler conceptually but pushes joins, migrations, and rebalancing into application code forever.
- Design the invariants: cross-shard uniqueness (UUIDv7 or key-embedded IDs instead of global sequences), cross-shard workflows as sagas/outbox rather than distributed transactions, schema migrations orchestrated across all shards with skew tolerated between waves.
- Rebalancing and shard splits must exist as tested procedures before you need them, because they are needed precisely when the system is fullest.

Record the sharding decision, key choice, and rejected alternatives as an ADR; this is one of the least reversible choices a data platform makes.

## Common pitfalls

- Partitioning a table because it is "big" while every query scans all partitions; pure overhead.
- Function-wrapped partition keys in queries, silently disabling pruning.
- No automation for future partitions; inserts fail (or flood the default partition) when the calendar rolls over.
- Thousands of small partitions; planning time and lock counts dominate query cost.
- Expecting a global unique constraint on a non-key column of a partitioned table; it cannot exist.
- Retention implemented as `DELETE` on a partitioned table, forfeiting the whole point of partition dropping.
- Sharding by a key that a third of queries do not carry, forcing scatter-gather everywhere.
- Hand-rolled sharding with no rebalancing story; the first overloaded shard becomes a months-long migration.

## Definition of done

- [ ] The trigger for partitioning is named (maintenance pain, retention lifecycle, or bounded-dimension access), not table size alone.
- [ ] Partitioning method and key match the dominant query dimension; PK/unique constraints include the partition key by design, not surprise.
- [ ] `EXPLAIN` on the top queries shows pruning to the expected partition count; partitionwise settings evaluated where relevant.
- [ ] Partition creation and retention are automated (pg_partman or a scheduled job) and alerted; the default partition is monitored empty.
- [ ] Partition count stays in the hundreds-to-low-thousands band under the retention policy.
- [ ] Any sharding proposal documents the exhausted cheaper alternatives, the shard key with its distribution evidence, cross-shard invariant handling, and the rebalancing procedure, all in an ADR.
- [ ] Retention and rebalancing procedures have been executed at least once in a non-production rehearsal.
