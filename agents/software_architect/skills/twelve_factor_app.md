---
name: twelve-factor-app
description: Governs the fifteen-factor structural constraints for a deployable service — one codebase per deploy, declared dependencies, environment-supplied config, attached backing services, build-release-run separation, statelessness, port binding, disposability, dev/prod parity, stdout logging, and API-first contracts. Use when designing a new service's deployment shape or reviewing whether it violates a factor.
---

# Twelve-Factor App

Treat the Twelve-Factor App as hard structural constraints on every service you design: one versioned codebase builds an immutable artifact that runs as stateless, disposable, share-nothing processes configured entirely from the environment. The canonical source is `12factor.net` (Adam Wiggins, Heroku, 2011); "Beyond the Twelve-Factor App" (Kevin Hoffman, O'Reilly, 2016) refines it and adds API-first, telemetry, and security as first-class concerns, giving the fifteen-factor model used below. Your job here is the design-time decision — what the structure must look like so the service is deployable, scalable, and replaceable. The runtime and operational side (probe tuning, rollout strategy, shutdown drills) belongs to the `sre` agent; reference it rather than re-specifying it.

## Codebase, dependencies, config (factors 1-3)

- **Factor 1 — one codebase, many deploys.** One app maps to exactly one repository tracked in Git; the same commit is deployed to dev, staging, and prod as different *deploys*, never different code. Design implication: a service boundary is a deployable boundary. If two teams must release independently, they get two codebases and a contract between them, not a shared trunk with feature flags standing in for a split. Shared code becomes a versioned dependency, not a second app smuggled into the same repo.
- **Factor 2 — explicitly declared, isolated dependencies.** Every dependency is named with a version and resolved from a committed lockfile; nothing is assumed present on the host. Python: `pyproject.toml` plus a committed `uv.lock` (uv 0.7.x, 2026) or `poetry.lock`; pin the base image by digest (`python:3.13-slim@sha256:...`). Node: `pnpm-lock.yaml` / `package-lock.json`. The container image is the isolation boundary — no `apt-get install` at runtime, no reliance on a system Python.
- **Factor 3 — config in the environment.** Anything that varies between deploys (URLs, credentials, toggles, hostnames) is read from environment variables at process start, never compiled into the artifact. The litmus test: the repo could be open-sourced this minute without leaking a secret. Group reads in one typed settings object, not scattered `os.getenv` calls.

```python
# pydantic-settings 2.x: one typed boundary for all env-supplied config.
from pydantic import PostgresDsn
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="APP_", frozen=True)
    database_url: PostgresDsn          # APP_DATABASE_URL, injected per deploy
    surreal_url: str | None = None     # mirrors this repo's SURREAL_URL override
    log_level: str = "INFO"
```

This repo already follows factor 3: `SURREAL_URL` / `SURREAL_USER` / `SURREAL_PASS` override `.agents/solomon/config/project.json` at runtime. Keep secrets out of the image and out of Git; inject them via Kubernetes `Secret`, External Secrets Operator, or Vault, and decrypt repo-stored config with SOPS. Credential handling detail is owned by the `security` and `auth_engineer` agents.

## Backing services and build/release/run (factors 4-5)

- **Factor 4 — backing services as attached resources.** Databases, queues, caches, SMTP, and third-party APIs are reached only through a connection URL in config, so a local instance and a managed one are swapped without a code change. Design implication: every backing service sits behind a port/interface you define (a design contract — see `design_contracts_as_component_boundaries`), so it is replaceable. This repo's SurrealDB-primary / SQLite-fallback store is exactly an attached resource selected by config — but note that swapping the *engine* this way is a dev/prod parity risk (factor 10), not a free win; document it as a deliberate tradeoff.
- **Factor 5 — strict build, release, run separation.** Three stages, one direction, no skipping back. *Build* compiles the commit into an immutable artifact (an OCI image). *Release* binds that exact image to a deploy's config and gets a unique, monotonic id. *Run* starts processes from a release; it never mutates code. Consequence: every release is immutable and individually rollback-able, and you can never edit code on a running box. CI is the only thing that builds; production is never `git pull`-ed or hot-patched.

```dockerfile
# Multi-stage Dockerfile: build is isolated, the run image carries no toolchain.
FROM python:3.13-slim@sha256:... AS build
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev          # fail if lockfile drifts from manifest

FROM python:3.13-slim@sha256:... AS run
COPY --from=build /app/.venv /app/.venv
COPY . .
# config arrives at run time via env; the image is the same across all deploys
CMD ["uv", "run", "uvicorn", "app:api", "--host", "0.0.0.0", "--port", "8080"]
```

## Stateless processes, port binding, concurrency (factors 6-8)

- **Factor 6 — stateless, share-nothing processes.** Each process keeps nothing durable in memory or local disk between requests; any state that must survive lives in a backing service (Postgres, Redis). In-process caches are allowed only as a throwaway optimization that a cold process can rebuild. Design implication: no sticky sessions, no "the cache is on node 3" — session and workflow state externalize to Redis/datastore so any replica can serve any request. This is the single most load-bearing factor for horizontal scale.
- **Factor 7 — export services via port binding.** The app is self-contained and binds its own port; it is not injected as a module into a runtime web server (no app-as-Tomcat-WAR, no Apache `mod_php`). Uvicorn/Gunicorn binds the port; the orchestrator routes to it. This makes a service equally a backing service for something upstream (factor 4 from the other side).
- **Factor 8 — concurrency via the process model.** Scale out by running more processes, partitioned by *type* (web, worker, scheduler), not by growing one process with threads. Express the process formation explicitly:

```procfile
web:    uv run uvicorn app:api --host 0.0.0.0 --port 8080
worker: uv run python -m app.worker
```

  Each type maps to its own horizontally scalable unit — a Kubernetes `Deployment` with an `HPA`, or separate Heroku/Nomad process types. The architecture decision is *which* work is a web process versus an async worker, and where the queue boundary sits between them.

## Disposability and dev/prod parity (factors 9-10)

- **Factor 9 — disposability.** Processes start fast (seconds, not minutes) and shut down gracefully on `SIGTERM`: stop accepting new work, drain in-flight requests, then exit. Crash-only design — a process can die at any instant without corrupting state — forces queued jobs to be idempotent and re-runnable. The architectural obligations are fast cold start (lazy-load heavy resources, keep the image lean) and idempotency on every retried operation; the exact `terminationGracePeriodSeconds`, `preStop` hook, and probe timing are `sre`'s call.
- **Factor 10 — dev/prod parity.** Minimize the gap in time (deploy hourly, not quarterly), personnel (the author deploys), and tools (same backing-service *types* everywhere). The classic violation is using a lightweight stand-in locally and the real engine in prod — SQLite in dev, Postgres in prod. Run the real backing services as containers in dev (Docker Compose / Testcontainers) so behavior matches. Where a fallback engine is unavoidable (as with this repo's SQLite fallback), record it as a known parity gap with a test that exercises both backends.

```yaml
# Kubernetes Deployment: port binding (7), concurrency by replicas (8),
# disposability via probes + graceful drain (9). Probe values are sre-owned.
spec:
  replicas: 4
  template:
    spec:
      terminationGracePeriodSeconds: 30
      containers:
        - name: web
          image: registry/app@sha256:...     # immutable release artifact (5)
          ports: [{ containerPort: 8080 }]
          readinessProbe: { httpGet: { path: /healthz, port: 8080 } }
          envFrom: [{ secretRef: { name: app-config } }]   # config from env (3)
```

## Logs and admin processes (factors 11-12)

- **Factor 11 — logs as event streams.** The app writes one structured event per line to `stdout`/`stderr` and never opens, rotates, or ships a log file itself. The execution environment captures the stream and routes it to the aggregator. Design implication: logging is fire-and-forget structured JSON; the pipeline, retention, and dashboards are designed by the `observability` agent, but the *contract* — emit to stdout, structured, with a correlation/trace id — is an architectural constraint you set.
- **Factor 12 — admin processes as one-off processes.** Migrations, backfills, and one-off scripts run in the *same release and environment* as the long-running processes, as a one-shot invocation (a Kubernetes `Job` from the same image, `release exec`), not by SSH-ing in and running ad hoc code against prod. This keeps admin tasks under the same dependency isolation and config, so a migration tested in CI runs identically in prod.

## Beyond the twelve factors: API first, telemetry, security

Kevin Hoffman's additions close gaps the original twelve leave open for distributed, cloud-native systems:

- **API first.** Design and publish the interface contract before implementation — OpenAPI 3.1 for REST, a `.proto` for gRPC, an AsyncAPI doc for event-driven flows — and let producers and consumers build against the mock. This is the cloud-native form of this role's `design_contracts_as_component_boundaries` output: the contract is the boundary, versioned and consumer-tested (Pact), so services evolve independently without a synchronized release.
- **Telemetry.** Treat metrics, traces, and health as designed outputs, not afterthoughts. Standardize on OpenTelemetry (OTLP) for traces and metrics so the app emits vendor-neutral signals; define the RED/USE signals and SLIs at design time (see `non_functional_requirements`). The collection and alerting design is the `observability` agent's; here you mandate that every service is instrumented and propagates trace context.
- **Security / authentication and authorization.** Authn/authz, secret handling, and transport security are designed in from the first sketch, not bolted on. As architect you specify *where* the trust boundaries and policy enforcement points sit; the mechanism — OAuth/OIDC, sessions, MFA, OPA/Rego policy — is owned by the `auth_engineer` and `security` agents. Cross-reference them in the ADR rather than restating their content.

Record any deliberate deviation from a factor in an Architectural Decision Record (see `architectural_decision_records`): name the factor, the constraint it forces, why you are bending it, and the parity or operational cost incurred.

## Common pitfalls

- Config baked into the image or read from a checked-in `config.prod.yaml`, so a new environment needs a rebuild — reject; config must come from the environment at run time (factor 3).
- Stateful processes: in-memory sessions, local-disk uploads, or a per-node cache treated as durable — reject; it blocks horizontal scale and breaks on any restart (factor 6).
- Sticky sessions / node affinity used to paper over hidden process state — reject; fix the statelessness, do not pin the load balancer.
- Mutating a running deploy (SSH hot-patch, `git pull` on the box, editing code in the container) — reject; it destroys the immutable-release guarantee and makes rollback impossible (factor 5).
- A backing service reached through a hardcoded host instead of a config URL, so local and prod cannot be swapped — reject (factor 4).
- Different backing-service engines between dev and prod (SQLite vs Postgres, in-memory queue vs SQS) with no parity test — reject or document as an explicit, tested gap (factor 10).
- The app writing and rotating its own log files instead of streaming to stdout — reject; the environment owns log routing (factor 11).
- Migrations run by hand against prod instead of as a one-off job on the deployed release — reject; it escapes dependency and config isolation (factor 12).
- Threads-only scaling inside a single fat process where the workload needs independent web/worker units — reject; partition by process type (factor 8).
- API contract written after the implementation ships, forcing consumers to reverse-engineer it — reject; contract precedes code (API first).
- Telemetry and authz treated as a later sprint — reject; both are design-time concerns with named owners (`observability`, `auth_engineer`).

## Definition of done

- [ ] Each service is one repository producing one immutable artifact; independent release needs imply separate codebases joined by a contract.
- [ ] Dependencies are fully declared with a committed lockfile and a digest-pinned base image; nothing relies on host-provided packages.
- [ ] All deploy-varying config and every secret are supplied via the environment through one typed settings boundary; the repo leaks no credential.
- [ ] Every backing service is reached through a config-supplied URL behind a defined interface, and is swappable without code change.
- [ ] Build, release, and run are separated; releases are immutable, uniquely identified, and rollback-able; no path mutates running code.
- [ ] Processes are stateless and share-nothing, with all durable state in backing services and no sticky-session dependency.
- [ ] Services are self-contained and export via port binding; concurrency is expressed as scalable process types (web/worker/scheduler).
- [ ] Disposability holds: fast startup, `SIGTERM` graceful drain, and idempotent retried operations; probe/grace tuning is delegated to `sre`.
- [ ] Dev/prod parity is kept; any engine substitution (e.g. SQLite fallback) is documented as a parity gap with a test covering both backends.
- [ ] Logs are structured events on stdout/stderr with trace correlation; the pipeline is delegated to `observability`.
- [ ] Admin/migration tasks run as one-off jobs on the same release and environment, never as manual prod edits.
- [ ] API-first contract (OpenAPI/AsyncAPI/proto) exists before implementation; telemetry (OpenTelemetry) and authn/authz boundaries are designed in and cross-referenced to their owning agents.
- [ ] Every deliberate deviation from a factor is captured in an ADR with its rationale and cost.
