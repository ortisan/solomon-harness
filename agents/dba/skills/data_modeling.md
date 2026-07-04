# Data Modeling

A concrete standard for schema design: keys, constraints as enforced invariants, normalization versus deliberate denormalization, type selection, and temporal data. The stance: the database is the last line of defense for data integrity, so every business invariant that can be expressed as a constraint must be, and every denormalization is a documented, measured trade, never a habit. PostgreSQL is the reference engine; MySQL differences are noted only where they change the decision.

## Keys and identity

- Every table gets a primary key. For surrogate keys default to `BIGINT GENERATED ALWAYS AS IDENTITY` (SQL-standard identity, preferred over `serial`, which is a legacy macro that leaks sequence ownership quirks). `INT` overflows at 2.1 billion; the cost of `BIGINT` is 4 bytes per row, the cost of an emergency `INT`-to-`BIGINT` migration on a hot table is a full rewrite under lock. Choose `BIGINT` from day one for anything that grows.
- If keys must be generated client-side or must not reveal insert order magnitude, use UUIDv7 (RFC 9562, May 2024): time-ordered, so B-tree inserts stay right-leaning and cache-friendly. PostgreSQL 18 ships `uuidv7()` natively; earlier versions use an extension or generate in the application. Random UUIDv4 keys scatter inserts across the whole index and are a known cause of write amplification and buffer-cache churn on large tables.
- Keep natural keys as `UNIQUE` constraints even when a surrogate is the PK. The surrogate identifies the row; the unique constraint states the business identity (`UNIQUE (tenant_id, email)`). Without it, duplicates are an application bug away.

## Constraints are invariants, not decoration

Declare in the schema everything the application assumes:

- `NOT NULL` on every column unless NULL has a defined business meaning. Document what NULL means when you allow it.
- `CHECK` for domain rules: `CHECK (price_cents >= 0)`, `CHECK (status IN ('draft','active','archived'))`. A `CHECK` costs nanoseconds per write and removes a whole class of corrupt states.
- Foreign keys with an explicit action: `ON DELETE RESTRICT` by default; `CASCADE` only when the child is genuinely owned data (line items of an order), never across aggregate boundaries. Index the referencing column: PostgreSQL does not auto-index FK columns, and an unindexed FK turns every parent delete into a sequential scan of the child.
- Exclusion constraints for "no two rows may overlap" rules that `UNIQUE` cannot express (see temporal data below).
- Skipping FKs "for performance" on a distributed or very hot table is allowed only with a written justification and a compensating reconciliation job; record it as an ADR.

MySQL difference that changes the decision: `CHECK` constraints are only enforced from MySQL 8.0.16; on anything older they parse and silently do nothing, so the rule must move into triggers or the application.

## Normalization and deliberate denormalization

- Normalize to 3NF (Boyce-Codd where it falls out naturally). Each fact lives in exactly one place; update anomalies disappear by construction.
- Denormalize only when a measured read path justifies it, and prefer the safest mechanism first: a covering index, then a `MATERIALIZED VIEW` refreshed on a schedule, then a trigger- or application-maintained duplicate column. A denormalized copy is a cache; every cache needs a stated owner, an update path, and a repair query that can rebuild it from the normalized source.
- Counter caches (`comments_count` on `posts`) are legitimate but must be maintained transactionally with the child write or reconciled periodically; drifted counters erode trust in the whole dataset.
- JSONB is for genuinely schemaless payloads (webhook bodies, per-integration settings), not for dodging column design. Any JSONB field the business filters or joins on should be promoted to a real column; PostgreSQL cannot enforce `NOT NULL` or FK semantics inside a document.

## Types

- Money and quantities: `NUMERIC(precision, scale)` or integer minor units (`price_cents BIGINT`). Never `float`/`double precision` for anything summed or compared for equality; IEEE 754 rounding errors compound.
- Time: `timestamptz`, always. Plain `timestamp` stores a wall-clock reading with no zone and breaks the first time two systems disagree about local time. Store UTC, convert at the edge.
- Text: `text` with a `CHECK (length(x) <= n)` if a limit matters. `varchar(n)` and `text` have identical performance in PostgreSQL; the check constraint is easier to change later than a type.
- Enumerations: a lookup table (FK) when values carry attributes or change often; a `CHECK` on `text` for small, stable sets. PostgreSQL native `ENUM` types allow appending values easily but renaming or removing them is awkward; choose them knowingly.

## Temporal data

- Validity intervals: model as a range column, `valid_during tstzrange`, and enforce non-overlap per entity with an exclusion constraint:

```sql
CREATE TABLE price (
  product_id bigint NOT NULL REFERENCES product(id),
  amount_cents bigint NOT NULL CHECK (amount_cents >= 0),
  valid_during tstzrange NOT NULL,
  EXCLUDE USING gist (product_id WITH =, valid_during WITH &&)
);
```

- PostgreSQL 18 adds SQL-standard temporal keys (`PRIMARY KEY ... WITHOUT OVERLAPS`), which expresses the same invariant declaratively; use it on new PG18 clusters.
- History/audit: append-only history tables written by trigger (or logical decoding) with `valid_from`/`valid_to`, never in-place edits to audit rows. Keep the current-state table lean and the history table partitioned by time.
- MySQL has no range types or exclusion constraints, so overlap invariants there must be enforced in application logic or with locking patterns; this is a genuine reason to prefer PostgreSQL for temporal-heavy domains.

## Common pitfalls

- `INT` primary keys on growth tables; the overflow remediation is a locking rewrite at the worst possible time.
- Random UUIDv4 primary keys on high-insert tables, bloating and fragmenting the B-tree; use UUIDv7 or bigint identity.
- Unindexed foreign key columns, turning parent deletes and cascades into sequential scans.
- Nullable columns with no documented meaning for NULL; three-valued logic then leaks into every query (`NOT IN` with NULLs returns nothing).
- `timestamp` without time zone; the bug appears at the first DST change or cross-region deployment.
- Denormalized copies with no rebuild query and no owner; drift is discovered by customers.
- Business-critical fields buried in JSONB where no constraint can reach them.
- Relying on MySQL `CHECK` constraints pre-8.0.16, which are parsed and ignored.

## Definition of done

- [ ] Every table has a primary key; surrogate keys are `BIGINT` identity or UUIDv7, with the choice justified.
- [ ] Business identity is enforced with `UNIQUE` constraints independent of the surrogate key.
- [ ] All columns are `NOT NULL` unless NULL has a documented meaning; domain rules are `CHECK` constraints.
- [ ] Every FK has an explicit `ON DELETE` action and an index on the referencing column.
- [ ] Schema is 3NF; each denormalization has a measured justification, an update path, and a rebuild query, recorded in an ADR or the project memory.
- [ ] Money uses `NUMERIC` or integer minor units; all times are `timestamptz` in UTC.
- [ ] Temporal validity uses range types with exclusion constraints (or `WITHOUT OVERLAPS` on PG18+); audit history is append-only.
- [ ] The model was reviewed against the top five query patterns before merge, not after.
