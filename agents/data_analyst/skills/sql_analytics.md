# SQL Analytics

Analytical SQL that is correct first and fast second: window functions instead of self-joins, CTEs instead of nested subqueries, grouping sets instead of UNION stacks, and explicit handling of the NULL, duplicate, and boundary cases that silently corrupt aggregates. Write for the dialect actually in use — Postgres 16+ and ClickHouse 25.x differ in ways that change results, not just performance. Query plans, index design, and server tuning belong to the `dba` agent; hand off once a correct query needs physical optimization.

## Window functions

Use windows for ranking, deduplication, running totals, and period-over-period deltas. A self-join that emulates `LAG()` is a review rejection: it is slower and fans out on duplicate keys.

- `ROW_NUMBER()` for "one row per key" dedup; `RANK()` leaves gaps on ties, `DENSE_RANK()` does not. Pick deliberately and add a tiebreaker column to the `ORDER BY` so results are deterministic.
- Know the default frame: with an `ORDER BY`, the frame is `RANGE BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW`, which includes **all peer rows with equal sort values**. A running total over a non-unique `order_date` will jump in steps. For true row-wise accumulation say `ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW` explicitly.
- Name repeated windows once: `WINDOW w AS (PARTITION BY user_id ORDER BY ts)` and reference `OVER w`.
- Filtering on a window result requires a wrapper query in Postgres; ClickHouse and DuckDB support `QUALIFY`:

```sql
-- latest row per user (Postgres: wrap in a CTE and WHERE rn = 1)
SELECT * FROM events
QUALIFY ROW_NUMBER() OVER (PARTITION BY user_id ORDER BY ts DESC, event_id DESC) = 1;
```

Postgres also offers `DISTINCT ON (user_id) ... ORDER BY user_id, ts DESC`, which is idiomatic and usually faster for this pattern.

## CTEs and query structure

Structure multi-step logic as a pipeline of named CTEs, each doing one thing, each independently runnable while debugging. Since Postgres 12, plain CTEs are inlined by the planner; add `MATERIALIZED` only when you need to force one evaluation of an expensive step referenced twice. Recursive CTEs (`WITH RECURSIVE`) are the standard tool for org charts and bill-of-materials walks; always include a depth guard column to stop cycles.

## Grouping sets

Replace UNION-of-aggregates with one pass:

```sql
SELECT region, product, SUM(revenue) AS revenue,
       GROUPING(region) AS is_region_total, GROUPING(product) AS is_product_total
FROM sales
GROUP BY GROUPING SETS ((region, product), (region), ());
```

`ROLLUP(a, b)` and `CUBE(a, b)` are shorthands. Use `GROUPING()` to distinguish subtotal rows from genuine NULL dimension values; never rely on `region IS NULL` for that.

## Correctness patterns

These are the defects that pass a smoke test and still ship wrong numbers.

- **NULL logic.** `NOT IN (subquery)` returns zero rows if the subquery yields a single NULL; use `NOT EXISTS`. `COUNT(*)` counts rows, `COUNT(col)` skips NULLs — choose intentionally. Aggregates ignore NULLs, so `AVG(col)` is not `SUM(col)/COUNT(*)`.
- **Join fan-out.** Joining a fact table to a one-to-many side multiplies rows and inflates every downstream SUM. Pre-aggregate the many side in a CTE to the join grain, then join. Verify: row count of the result equals row count of the driving table for a 1:1 enrichment join.
- **Division.** Guard every ratio with `NULLIF(denominator, 0)`. In Postgres, `1/4` is integer division returning 0 — cast one operand: `1.0 * numer / NULLIF(denom, 0)`.
- **Date boundaries.** Use half-open intervals: `ts >= '2026-06-01' AND ts < '2026-07-01'`. `BETWEEN` on timestamps silently drops everything after midnight of the last day. Store UTC; convert with `ts AT TIME ZONE 'America/Sao_Paulo'` only at the grouping/reporting edge, and say so in the query.
- **Duplicates.** State the expected grain of every table you join in a comment, and assert it when unsure: `SELECT key, COUNT(*) FROM t GROUP BY key HAVING COUNT(*) > 1 LIMIT 10`.

## Dialect notes: Postgres vs ClickHouse

- ClickHouse `uniq()` is approximate (HyperLogLog-class, roughly 1-2% error); use `uniqExact()` when the number goes in a financial report, `uniq()` for dashboards at scale.
- ClickHouse `any(col)` returns an arbitrary value per group — convenient, nondeterministic. Prefer `argMax(col, ts)` to get "the value from the latest row", which also replaces the `ROW_NUMBER = 1` pattern cheaply.
- On a `ReplacingMergeTree`, deduplication happens at merge time, asynchronously. A plain `SELECT` can see duplicates; use the `argMax` pattern or `FINAL` (and know `FINAL` pays a merge cost at read time).
- Aggregate combinators (`sumIf`, `countIf`, `-State`/`-Merge`) replace `CASE WHEN` pivots and enable pre-aggregated materialized views. Postgres's equivalent conditional aggregate is `SUM(x) FILTER (WHERE cond)`.
- ClickHouse hash joins build the right-hand table in memory: put the small table on the right and filter it first. Postgres's planner reorders joins itself; ClickHouse mostly will not.
- Quoting and case sensitivity differ; keep identifiers lower_snake_case everywhere so it never matters.

## Common pitfalls

- Running total computed with a default `RANGE` frame over non-unique sort keys — peer rows collapse into steps; specify `ROWS`.
- `NOT IN` against a nullable column returning an empty result that looks like "no offenders".
- Fan-out joins inflating SUM/COUNT; the reviewer must ask for the grain of each joined table.
- `BETWEEN` on a timestamp column truncating the final day to midnight.
- Treating ClickHouse `uniq()` output as exact, or reading a `ReplacingMergeTree` without `FINAL`/`argMax` and reporting duplicated rows.
- `SELECT *` in ClickHouse: it is columnar; reading unneeded columns multiplies I/O.
- Subtotal rows from `ROLLUP` mistaken for NULL-dimension data because `GROUPING()` was not selected.
- Nondeterministic top-1 queries: `ORDER BY` without a tiebreaker, or ClickHouse `any()` where `argMax` was intended.

## Definition of done

- [ ] Every joined table's grain is stated and, where uncertain, asserted with a duplicate-key check.
- [ ] Result row count reconciles with the driving table (or the change is explained in the query comment).
- [ ] All ratios use `NULLIF` guards; no integer division; no unguarded `NOT IN` on nullable columns.
- [ ] Date filters use half-open intervals; timezone conversion is explicit and applied only at the reporting edge.
- [ ] Window frames are explicit (`ROWS` vs `RANGE`) wherever an `ORDER BY` is present, and orderings include a tiebreaker.
- [ ] Dialect-correct constructs used: `QUALIFY`/`DISTINCT ON`, `argMax` vs `any`, `uniqExact` where exactness is required, no `SELECT *` on columnar stores.
- [ ] The query is committed to the repository with a one-line statement of the business question it answers.
- [ ] Physical tuning needs (indexes, ORDER BY key changes, server settings) are handed to the `dba` agent, not patched around in the query.
