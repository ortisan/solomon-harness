# Database Security and Access Control

The database-side security standard: least-privilege role design, row-level security for tenant isolation, authentication and TLS, auditing, and the non-negotiable of parameterized queries. The stance: secure-by-default per the house STRIDE baseline; the database enforces isolation itself rather than trusting every application bug not to happen, and no secret or overprivileged role ships because it was expedient.

## Least privilege, concretely

- Applications connect as a dedicated DML-only role that owns nothing. Ownership implies destructive rights (`DROP`, `TRUNCATE`) and bypasses row-level security by default; the runtime role should be unable to alter the schema even if fully compromised.
- Split roles by function: `migrator` (DDL, used only by the migration pipeline), `app_write` (DML), `app_read` (SELECT, for read paths and dashboards), `replicator` (REPLICATION only). Humans get individual login roles and elevate via `SET ROLE` so actions are attributable.
- Deny by default: revoke `CREATE ON SCHEMA public` (already the default from PostgreSQL 15), grant `USAGE` on schemas explicitly, and never grant to `PUBLIC`. Use `ALTER DEFAULT PRIVILEGES` so future objects follow the policy automatically.
- No superuser in any application path, CI pipeline, or dashboard tool. Superuser is break-glass, logged, and rare.

## Row-level security for tenant isolation

RLS makes the server enforce the tenant boundary even when a query forgets its `WHERE tenant_id = ...`:

```sql
ALTER TABLE orders ENABLE ROW LEVEL SECURITY;
ALTER TABLE orders FORCE ROW LEVEL SECURITY;  -- applies to the table owner too

CREATE POLICY tenant_isolation ON orders
  USING (tenant_id = current_setting('app.tenant_id')::bigint)
  WITH CHECK (tenant_id = current_setting('app.tenant_id')::bigint);
```

The application sets the tenant once per transaction: `SET LOCAL app.tenant_id = '42'` (`SET LOCAL` so it cannot leak across pooled connections in transaction pooling). Rules:

- `USING` filters reads; `WITH CHECK` gates writes. Omitting `WITH CHECK` lets a tenant insert rows into another tenant's space that it can never read back.
- `FORCE ROW LEVEL SECURITY` is required if the connecting role owns the table; superusers and roles with `BYPASSRLS` skip policies regardless, which is exactly why the app role must be neither.
- Keep policy predicates cheap and indexable (`tenant_id` equality against a session setting); a subquery-per-row policy becomes the table's performance ceiling. Verify plans with `EXPLAIN` as the app role.
- Test RLS negatively in CI: connect as the app role, set tenant A, assert tenant B's rows are invisible and unwritable.

## Authentication and transport

- Password auth is `scram-sha-256` only (the default `password_encryption` since PostgreSQL 14). MD5 is broken and formally deprecated in PostgreSQL 18; migrate any remaining md5 verifiers. Prefer certificate or IAM/OAuth-based auth where the platform provides it (PG18 adds an OAuth mechanism).
- `pg_hba.conf` is an ordered firewall: first match wins. No `trust` lines outside single-user local development, no `0.0.0.0/0` rows, narrowest CIDR and database/role scoping per line, `hostssl` (not `host`) for anything off-box. Review it in code review; it belongs in configuration management, not hand edits.
- TLS: `ssl = on` with real certificates. The client side matters just as much: `sslmode=require` encrypts but does not authenticate the server; man-in-the-middle needs `sslmode=verify-full` (hostname check against the CA). Connection strings in production use `verify-full` with a pinned CA bundle.
- Secrets: no credentials in code, images, or repository files (house rule). Inject via secret manager or environment at deploy time; rotate on personnel change; give each service its own credential so revocation is surgical.

## SQL injection: parameterize, always

Every value reaching SQL travels as a bound parameter; string interpolation into SQL is a rejected review, no exceptions for "internal" inputs:

```python
cur.execute("SELECT * FROM orders WHERE customer_id = %s AND status = %s",
            (customer_id, status))          # psycopg: values bound, never formatted
```

Identifiers (table/column names) cannot be parameters; when dynamic, allowlist them or quote via `psycopg.sql.Identifier` / `quote_ident`. In `PL/pgSQL`, use `EXECUTE ... USING` and `format('%I', ...)`, never `format('%s', ...)` for identifiers. ORMs parameterize by default; raw-SQL escape hatches (`text()`, `raw()`) are where injection re-enters, so grep for them in review.

## Auditing and encryption

- `log_connections = on`, `log_disconnections = on`. `log_statement = 'ddl'` gives schema-change history; `log_statement = 'all'` at production volume is both a performance and a secrets problem (it logs bound values in some paths and every literal), so for real audit requirements use pgAudit: `pgaudit.log = 'ddl, role, write'`, scoped per role with `ALTER ROLE ... SET pgaudit.log`.
- Ship logs off-host; an attacker with DB-host access edits local logs first.
- Encryption at rest: full-volume/filesystem encryption (or the cloud provider's storage encryption) as baseline. Column-level encryption for regulated fields is an application-layer concern with real key-management cost; do not improvise it with `pgcrypto` and a key stored in the same database.
- Keep the attack surface small: install only needed extensions, and remember `COPY ... PROGRAM` and file FDWs are superuser-gated for a reason; do not grant `pg_execute_server_program` casually.

## Common pitfalls

- App role owns its tables, so RLS without `FORCE` silently does not apply to it; the isolation everyone assumed is off.
- RLS policies with `USING` but no `WITH CHECK`: cross-tenant writes pass validation.
- `SET` (not `SET LOCAL`) for the tenant GUC under transaction pooling; tenant context bleeds between requests via the shared connection.
- `sslmode=require` treated as "TLS done" while the client never verifies the server identity.
- One shared credential across services and humans; rotation becomes an outage, attribution impossible.
- `log_statement = 'all'` capturing passwords and tokens into world-readable logs.
- A single `f"WHERE id = {user_input}"` in a maintenance script; injection does not care that it was "just internal tooling".
- `pg_hba.conf` accreted by hand until an early broad rule shadows every careful one below it.

## Definition of done

- [ ] Roles are split migrator/app_write/app_read/replicator; the runtime role owns no objects and has no superuser or `BYPASSRLS`.
- [ ] Grants are deny-by-default with `ALTER DEFAULT PRIVILEGES` in versioned migrations; nothing granted to `PUBLIC`.
- [ ] Multi-tenant tables have RLS with both `USING` and `WITH CHECK`, `FORCE ROW LEVEL SECURITY`, `SET LOCAL` tenant context, and negative cross-tenant tests in CI.
- [ ] Authentication is scram-sha-256 or stronger; no md5, no `trust`; `pg_hba.conf` is reviewed configuration with narrow scopes and `hostssl`.
- [ ] Clients connect with `sslmode=verify-full` and a managed CA; certificates rotate before expiry.
- [ ] All SQL uses bound parameters; dynamic identifiers are allowlisted or safely quoted; raw-SQL escape hatches were grepped and reviewed.
- [ ] pgAudit (or equivalent) covers DDL, role, and write events per policy; logs ship off-host; secrets absent from code and logs.
- [ ] The threat model (STRIDE) for the data layer is recorded, with compromised-app-role as an analyzed scenario.
