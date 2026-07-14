---
name: data-quality-and-validation
description: Governs executable data-quality checks at pipeline boundaries: pandera and Great Expectations schema contracts, freshness/completeness/uniqueness/validity checks, source reconciliation, and block-versus-warn severity policy. Use when a pipeline lacks validation, a number needs reconciling against source, or a quality alert fires.
---

# Data Quality and Validation

Data quality expressed as executable expectations at pipeline boundaries: schema contracts on ingestion, freshness/completeness/uniqueness checks on every table a report depends on, and reconciliation against the source system before a number is published. The stance: an unchecked dataset is an unverified claim, and a dashboard fed by one is a liability. Checks live in version control next to the pipeline, run automatically, and have a declared severity — block or warn — decided before the first failure, not during it.

## Expectations as code

Two house tools; pick by where the data lives:

- **pandera** (>= 0.20; validates pandas and Polars frames) for in-process pipelines. Contracts are typed classes, so they double as documentation and are unit-testable.
- **Great Expectations (GX Core 1.x)** when checks must run against warehouse tables (Postgres, ClickHouse via SQLAlchemy) on a schedule and produce persisted validation results and data docs. If the warehouse is dbt-managed, prefer dbt tests (`unique`, `not_null`, `accepted_values`, `relationships`) as the first layer — they run where transformations run.

```python
import pandera.pandas as pa
from pandera.typing import Series

class Orders(pa.DataFrameModel):
    order_id: Series[str] = pa.Field(unique=True)
    amount_cents: Series[int] = pa.Field(ge=0, le=50_000_000)   # cap catches unit errors
    status: Series[str] = pa.Field(isin=["placed", "paid", "refunded", "cancelled"])
    created_at: Series[pa.DateTime] = pa.Field(nullable=False)

    class Config:
        strict = True   # unexpected columns are an error, not a shrug

validated = Orders.validate(df, lazy=True)  # lazy=True collects ALL failures, not the first
```

`strict = True` matters: new upstream columns arriving unannounced are a schema change someone should approve. `lazy=True` matters: fix-one-rerun-fail-again loops waste a day.

## The core check dimensions

Every table feeding a report gets, at minimum:

- **Freshness**: `max(event_ts)` lag against an explicit SLA (e.g. "orders lands within 2 h; alert at 4 h"). Check the event time, not the load time — a loader that runs on schedule but copies an empty delta passes a load-time check.
- **Completeness**: row count vs a baseline — same weekday last week within a tolerance band (say ±30%), or count parity with the source system. Also per-column null-rate ceilings on business-critical fields.
- **Uniqueness**: duplicate rate on the declared primary key = 0, enforced, because most warehouse loads are at-least-once and reruns create duplicates.
- **Validity**: ranges, enums, and cross-field rules (`refunded_at >= created_at`; `status = 'refunded'` implies `refund_amount_cents > 0`).
- **Consistency**: referential checks — orphaned foreign keys below a stated threshold, and cross-table invariants like `sum(order_lines.amount) = orders.amount` per order.

Thresholds are versioned constants with a comment explaining each number, not folklore in someone's head.

## Reconciliation

Before any externally visible number ships, reconcile the analytical copy against the operational source for the same window:

1. Compare `COUNT(*)` and `SUM` of the key measure per day for the trailing 14 days; tolerance for money is exact (0 cents) unless a documented timing difference (late-arriving refunds) says otherwise.
2. If aggregates disagree, bisect: per-day, then per-hour, then sample 20 mismatched rows and inspect. The cause is usually timezone bucketing, soft-deleted rows, or a status filter difference — write the finding down where the next analyst will look.
3. Automate the aggregate comparison as a scheduled check; a reconciliation done once is a snapshot, not a control.

## Severity, quarantine, and alerting

- **Block** (pipeline halts, downstream tables not refreshed): schema contract violations, PK duplicates, money reconciliation failures. Wrong data published is worse than stale data with a banner.
- **Warn** (publish, page nobody, file a ticket): drifting null rates, volume near the band edge, orphan rates creeping up.
- Failing rows on row-level checks go to a quarantine table (`orders_rejected` with a `reason` column and load timestamp) so they can be fixed and replayed; silently dropping them turns a data bug into a completeness bug.
- Every alert names an owner and the first diagnostic query to run. Alerts without a runbook line get ignored within a month.
- Track the pass rate over time; a check that has never failed in six months and a check that fails weekly and gets muted are both signals to redesign.

What this skill does not cover: statistical drift detection and anomaly models on distributions belong to `ml_engineer`; fixing the upstream schema or load process belongs to `dba`/`sre` — file the handoff with the failing check attached.

## Common pitfalls

- Checking load timestamps instead of event timestamps for freshness — an empty successful load passes.
- No `strict` schema, so upstream column renames flow through as a wall of NULLs that every downstream null-tolerant aggregate absorbs.
- Fail-fast validation (first error only), hiding the other nine problems until the next run.
- Uniqueness assumed ("it's the primary key upstream") but never enforced on the at-least-once loaded copy.
- Row-level failures silently dropped instead of quarantined, converting a visible bug into invisible undercounting.
- Reconciliation run once at launch, then never again as timezones, filters, and source schemas drift.
- Tolerance thresholds with no rationale, tuned only to stop the alert from firing.
- Muting a flapping check instead of fixing the check or the data — a muted block is a warn with worse paperwork.

## Definition of done

- [ ] Every table feeding a published report has freshness, completeness, uniqueness, validity, and consistency checks in version control.
- [ ] Schema contracts are strict (unexpected columns fail) and validate lazily (all failures reported per run).
- [ ] Each check has a declared severity; block-severity failures verifiably stop downstream refresh.
- [ ] Freshness checks use event time with a stated SLA and alert threshold.
- [ ] PK uniqueness is enforced on the analytical copy, not assumed from the source.
- [ ] Row-level failures land in a quarantine table with a reason code and can be replayed.
- [ ] Money and key-measure reconciliation against the source runs on a schedule with documented tolerances; last run is green.
- [ ] Every alert names an owner and a first diagnostic step.
- [ ] Distribution-drift modeling is delegated to `ml_engineer`; upstream fixes are filed to `dba`/`sre` with the failing check attached.
