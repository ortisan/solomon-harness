# Database Administration

Purpose: Define backup, security, replication, and high availability policies.

## Core Rules

1. Principle of Least Privilege
   - Application connections must use isolated credentials with access restricted only to the schemas and tables required for operation.
   - Restrict administrative permissions (superuser) to structural migration stages only.

2. Backup and Disaster Recovery
   - Maintain automated, point-in-time recovery (PITR) and daily snapshot backup schedules.
   - Perform periodic restore drills to verify snapshot recovery time objectives (RTO).

3. Connection Pooling
   - Use dedicated connection pooling proxies (e.g., PgBouncer) for application architectures with highly dynamic scaling behavior.
