# Big Data Processing

Purpose: Optimize calculations over large datasets using distributed or columnar engines (Spark, ClickHouse).

## Core Rules

1. Avoid Data Shuffling
   - Minimize operations requiring cluster-wide partition redistribution (joins on non-partition keys, broad aggregations) to prevent execution bottlenecks.
   - Filter and reduce the dataset size as early as possible in the execution graph (Push-down predicate).

2. Columnar Optimization
   - In columnar databases like ClickHouse, query only the columns needed. Never write `SELECT *`.
   - Organize primary keys to match the sorting/filtering patterns of analytical queries.

3. Partition and Bucket
   - Distribute data partitions by a logical high-level grouping (e.g. date, region) to enable partition pruning during queries.
