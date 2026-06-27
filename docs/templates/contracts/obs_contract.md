# Observability Contract

## 1. Application Metrics
Define the key performance indicators (KPIs), resource utilisation, and custom business metrics tracked.
- CPU Usage: limit 80% threshold.
- Memory Usage: limit 90% threshold.
- Request Latency: p99 latency target under 200ms.

## 2. Logging Standards
Format and guidelines for application logging across all environments.
- Format: JSON formatted structured logs.
- Key attributes: timestamp, level, message, correlation_id, service_name.

## 3. Tracing Endpoints
Distributed tracing integration points across component boundaries.
- Gateway routing tracing.
- Internal service calls tracing.
- Data access tracing.

## 4. Alert Triggers
Conditions that generate system notifications, paging events, or automated recovery procedures.
- Trigger 1: Request failure rate exceeds 5% within 1 minute.
- Trigger 2: Database connection pool utilization exceeds 95% for 3 minutes.

## 5. Operations and Branches
Maintain observability configuration through deployment pipelines.
- Branches: develop for staging dashboard configs, main for production alerts.
- Commit Format: chore(observability): update dashboards and logging standards config (under Conventional Commits framework).
- Branching Model: Git Flow (features tested on feature/* before promotion).
