# Database Performance Tuning

Purpose: Diagnose execution bottlenecks and apply indexing/query optimizations.

## Core Rules

1. Explain First
   - Run `EXPLAIN ANALYZE` on any query experiencing high response latency or CPU usage before proposing indices or changes.
   - Look for Sequential Scans (Seq Scan) on large datasets and replace them with Index Scans where possible.

2. Indexing Strategy
   - Apply B-tree indexes for equality and range queries, and specialized index types (GIN, Hash, BRIN) only when required by the datatype or access pattern.
   - Avoid over-indexing (e.g. indexing columns with low selectivity), as it degrades write performance.

3. Limit and Paginate
   - Never run unconstrained queries in production. Always apply `LIMIT` and pagination keys.
