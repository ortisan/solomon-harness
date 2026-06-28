# SQL Analytics

Purpose: Construct complex, readable, and highly optimized analytical SQL.

## Core Rules

1. Use Common Table Expressions (CTEs)
   - Write structured CTEs rather than deeply nested subqueries to improve query readability and optimization.

2. Leverage Window Functions
   - Use window functions (`ROW_NUMBER()`, `RANK()`, `LAG()`, `LEAD()`, `SUM() OVER`) for temporal analyses, ranking operations, and running totals instead of self-joins.

3. Optimize Joins and Filters
   - Place filtering predicates (`WHERE` clauses) on indexed partition columns early. Avoid joins on calculated fields (e.g. joining on `LOWER(email)`), as they disable standard indices.
