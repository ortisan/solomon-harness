# Database Migrations

Purpose: Direct safe schema evolution with zero-downtime execution.

## Core Rules

1. Avoid Blocking Operations
   - Never run migrations that acquire exclusive locks on large tables during peak hours (e.g. adding columns with defaults in older database engines, modifying column types).
   - Use multi-step migration patterns (Expand-Contract) for structural modifications (e.g., add new column, sync data, transition reads, deprecate old column).

2. Safe Index Creation
   - Create new indexes concurrently (e.g., `CREATE INDEX CONCURRENTLY` in PostgreSQL) to prevent locking table writes.

3. Reversibility
   - Every migration script must supply a corresponding rollback schema step (`down` migration) that is validated before deployment.
