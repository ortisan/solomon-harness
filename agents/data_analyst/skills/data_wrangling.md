---
name: data-wrangling
description: Governs cleaning raw extracts into analysis-ready tables with pandas or Polars, covering dtype discipline, validated joins, a written missing-data policy, and memory management for single-node pipelines. Use when writing an ingestion script, reviewing a join or dedup step, or debugging a memory or dtype defect.
---

# Data Wrangling

Turning raw extracts into analysis-ready tables with pandas or Polars: explicit dtypes at the ingestion boundary, validated joins, a written missing-data policy, and memory discipline that keeps single-node work single-node. The stance: every transformation must be reproducible from the raw file by rerunning one script, and every row that is dropped or imputed must be counted and reported. Statistical imputation models and feature engineering for training belong to the `ml_engineer` agent; this skill covers analytical cleaning, not model pipelines.

## Choosing the engine

- **pandas 2.x** (Copy-on-Write on by default in pandas 3.0; on 2.x set `pd.options.mode.copy_on_write = True`) for datasets that fit comfortably in RAM — as a rule, raw size under ~1-2 GB. Use PyArrow-backed dtypes (`dtype_backend="pyarrow"` on readers) for proper nullable types and fast strings.
- **Polars 1.x** when data is 1-50 GB, when the pipeline is CPU-bound, or when you want a query optimizer: `pl.scan_parquet(...)` builds a lazy plan, pushes filters and projections down, and runs multi-threaded. The streaming engine handles larger-than-RAM inputs on one machine.
- **DuckDB** when the cleaning is naturally SQL (joins, dedup, window filters) over Parquet/CSV files; it queries pandas and Polars frames in place.
- A cluster (Spark) is a last resort — see `big_data_processing`. Do not move to distributed tooling to escape a memory problem that dtype discipline would solve.

Exchange format between steps is Parquet, never CSV: CSV loses dtypes, timezones, and NULL-vs-empty-string distinctions on every round trip.

## Dtype discipline

`object` dtype in pandas is a defect, not a default. Declare types at the boundary:

```python
import pandas as pd

df = pd.read_csv(
    "orders.csv",
    dtype={"order_id": "string", "sku": "category", "qty": "Int64"},
    parse_dates=["created_at"],
    dtype_backend="pyarrow",
)
df["created_at"] = df["created_at"].dt.tz_localize("UTC")  # naive timestamps are a bug
bad = pd.to_numeric(df["amount"], errors="coerce")
print(f"non-numeric amounts: {bad.isna().sum() - df['amount'].isna().sum()}")
```

Rules: nullable `Int64`/`boolean` instead of float-with-NaN for counts and flags; `category` for low-cardinality strings (cuts memory ~10x and speeds groupby); timezone-aware timestamps everywhere, converted to UTC on ingest; money as integer cents or `Decimal`, never float64, when sums must reconcile. In Polars, the schema is explicit by construction — pass `schema_overrides` to readers and treat a `str` column that should be `pl.Categorical` or `pl.Datetime("us", "UTC")` as unfinished work.

## Joins and deduplication

Every join states its expected cardinality and is verified:

```python
merged = orders.merge(customers, on="customer_id", how="left",
                      validate="m:1", indicator=True)
assert len(merged) == len(orders)                      # no fan-out
match_rate = (merged["_merge"] == "both").mean()
assert match_rate > 0.99, f"only {match_rate:.1%} matched"
```

`validate="m:1"` raises on duplicate keys in the dimension table — the single most common silent row-multiplication bug. Polars: `orders.join(customers, on="customer_id", how="left", validate="m:1")`.

Deduplication is a policy, not a call to `drop_duplicates()`: define the key, define the winner (usually latest `updated_at`), sort deterministically, then keep one. Report how many rows were removed. In Polars, `df.sort("updated_at", descending=True).unique(subset=["order_id"], keep="first")`.

## Missing-data policy

Distinguish three cases before touching a NaN: structurally absent (a refund has no shipping date — leave it null), missing at ingestion (a broken extract — fix upstream or quarantine), and genuinely unknown (decide per analysis). Then:

- Never `fillna(0)` on measures; zero is data. Filling a revenue NaN with 0 changes every average downstream.
- Impute only with a stated rule (constant, forward-fill within an entity, median per group) written next to the code, and add a boolean `was_imputed_<col>` column when the imputation could move a reported number.
- Report the null rate per column before and after cleaning; a null rate that changed for a column you did not touch means a join or dtype coercion ate values.
- Anything requiring model-based imputation (MICE, KNN) is a handoff to `ml_engineer`.

## Memory management

- Measure first: `df.memory_usage(deep=True)`; string-heavy frames shrink most from `category`/Arrow strings.
- Process large CSVs in chunks (`chunksize=1_000_000`) or, better, convert to Parquet once and use Polars lazy scans so only needed columns and row groups load.
- Drop columns at read time (`usecols`/projection pushdown), not after; peak memory is set by the widest intermediate frame.
- Avoid chained `df[df.x > 0].copy()` cascades that hold multiple full copies alive; with Copy-on-Write, assignment is safe, but intermediates still cost — chain with `.pipe()` or use lazy Polars where the optimizer fuses steps.

## Common pitfalls

- `object` dtype surviving to the analysis stage, making comparisons and sorts locale- and type-dependent.
- Joins without `validate=`: duplicate dimension keys multiply fact rows and inflate every sum.
- `fillna(0)` on measures, or dropping NaN rows without counting them — the report's denominator changes invisibly.
- Naive timestamps mixed with tz-aware ones; comparisons then raise, or worse, shift by the session timezone.
- Float64 money that fails reconciliation by cents after aggregation.
- CSV as the interchange format between pipeline steps, losing dtypes and NULLs on every hop.
- Dedup with `drop_duplicates()` and no ordering — which row survives depends on file order and changes between runs.
- Reaching for Spark because pandas ran out of memory on a frame that `category` dtypes and Parquet projection would have made fit.

## Definition of done

- [ ] The pipeline reruns end-to-end from the raw files with one command and produces byte-identical Parquet outputs.
- [ ] Every column has an explicit dtype; no `object` columns; timestamps are tz-aware UTC; money is not float.
- [ ] Every join declares `validate=` and asserts the expected output row count and match rate.
- [ ] Deduplication states key, winner rule, and deterministic ordering, and logs the number of rows removed.
- [ ] The missing-data policy per column is written down; imputations are flagged in a companion column; dropped-row counts are reported.
- [ ] Null rates and row counts are compared before/after cleaning and reconcile with the raw input.
- [ ] Peak memory was measured; engine choice (pandas / Polars / DuckDB) matches data size and is noted in the script header.
- [ ] Model-based imputation or feature engineering is handed to `ml_engineer`; nothing statistical is smuggled into cleaning.
