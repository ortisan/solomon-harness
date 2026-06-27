# SRE Best Practices

Operational standard for running production services in solomon-harness: how to set reliability targets, build deployment pipelines, test under load, respond to incidents, and recover from disasters.

## Reliability targets: SLI, SLO, SLA, error budgets

Define reliability before you defend it. Pick SLIs that reflect user pain, set SLOs against them, and treat the gap to perfection as a budget you are allowed to spend.

- **SLI**: a ratio of good events to valid events, measured as close to the user as possible (load balancer or client RUM, not server-side only). Standard categories: availability, latency, throughput, correctness, freshness, durability. Example latency SLI: "proportion of valid requests served faster than 300 ms".
- **SLO**: target for an SLI over a rolling window (use 28 or 30 days, not calendar months). State the window explicitly. Example: "99.9% of requests succeed over 28 days".
- **SLA**: the externally contracted, penalty-bearing promise. Always set the SLA looser than the internal SLO so you breach the SLO and react before you breach the contract.
- **Error budget** = 1 − SLO. This is the permitted unreliability. Spend it on releases and experiments; stop spending when it runs out.

Error budget per 30-day window (downtime equivalent):

| SLO | Budget (% requests) | ~Downtime / 30 days |
| --- | --- | --- |
| 99% | 1% | 7h 12m |
| 99.9% | 0.1% | 43m 12s |
| 99.95% | 0.05% | 21m 36s |
| 99.99% | 0.01% | 4m 19s |
| 99.999% | 0.001% | 26s |

- **Error budget policy** (write it down, get sign-off from product): when the budget is exhausted, freeze feature deploys and redirect the team to reliability work until the budget recovers. When the budget is healthy, ship faster and take more risk. The policy is the contract that makes the SLO real.
- **Burn-rate alerting**, multiwindow multi-burn-rate (Google SRE workbook pattern). Alert on budget consumption rate, not raw thresholds:
  - Fast burn, page: 14.4x burn over a 1h window (with a 5m short window to confirm) — consumes 2% of a 30-day budget in one hour.
  - Medium burn, page: 6x over 6h (with a 30m short window) — 5% of budget in six hours.
  - Slow burn, ticket: 1x over 3 days (with a 6h short window) — 10% of budget over the window.
- Pitfalls: chasing 100% (the right target is below 100%, leaving room to ship); averaging away tail latency (alert on p95/p99, not the mean); measuring success server-side while users see failures at the edge; one giant 99.99% SLO for everything instead of per-critical-journey SLOs.

## High availability

Design so that any single component can fail without taking down the service.

- **Eliminate SPOFs.** Run N+1 (survive one failure) or N+2 capacity. Spread across at least two availability zones; reach for multi-region only when the SLO and DR tier justify the cost and complexity.
- **Health checks**: separate liveness (restart me) from readiness (route traffic to me). Keep liveness shallow so a slow dependency does not trigger a restart loop; make readiness deep enough to drain on dependency failure. Add startup probes for slow-booting services.
- **Load balancing**: L4 for raw throughput, L7 for routing and TLS termination. Use least-connections or consistent hashing where session affinity or cache locality matters; round-robin otherwise. Configure outlier detection to eject unhealthy backends.
- **Resilience patterns**: timeouts on every outbound call (never unbounded), retries with exponential backoff plus jitter, retry budgets to prevent retry storms, circuit breakers, bulkheads to isolate pools, and load shedding that drops the lowest-priority traffic first. Prefer graceful degradation (serve stale cache, reduced features) over hard failure.
- **Autoscaling**: HPA on the signal that actually correlates with load (RPS or queue depth often beat CPU). Set sane min replicas for redundancy and max for cost control. Keep headroom; an autoscaler cannot save you from a cold-start stampede. Test scale-down behavior, not just scale-up.
- **Stateful systems**: use quorum-based replication (Raft/Paxos) and verify the failover actually promotes a replica. Test split-brain handling.
- Pitfalls: synchronized retries without jitter, health checks that pass while the service is useless, autoscaling on a lagging metric, "multi-AZ" that shares a single NAT gateway or database primary.

## Infrastructure and deployment pipelines

Everything is code, reviewed, versioned, and reproducible. No console clicks in production.

- **IaC**: Terraform/OpenTofu or Pulumi. Remote state with locking, no local state. Run drift detection on a schedule. Plan output is reviewed in PRs; pin provider and module versions. Build immutable golden images with Packer rather than mutating live hosts.
- **GitOps**: ArgoCD or Flux with git as the single source of truth for cluster state. Reconciliation, not imperative apply.
- **CI/CD stages**: lint and unit tests, build, SAST and dependency scan, sign the artifact, generate an SBOM, integration tests, deploy to staging, automated checks, promote. Gate promotion on tests passing and on the error budget being healthy.
- **Deployment strategy**: prefer canary or blue/green over a naked rolling update. Run automated canary analysis (Argo Rollouts or Flagger) that compares the canary's error rate and latency against the baseline and rolls back automatically on regression. Decouple deploy from release using feature flags.
- **Rollback**: must be one command and complete within minutes. Practice it. A deploy you cannot roll back is not done.
- **Database migrations**: backward-compatible, expand/contract (add column, dual-write, backfill, switch reads, drop old) so the schema is compatible with both the old and new app versions during the rollout. Never couple a destructive migration to the same release that stops using the column.
- **Secrets**: Vault, SOPS, or sealed-secrets. Never in git, never in plain environment files committed to the repo. Rotate on a schedule.
- Pitfalls: snowflake servers, unpinned versions, a pipeline with no rollback path, migrations that assume a single atomic cutover, manual hotfixes that drift from IaC.

## Load and resilience testing

Find the breaking point in a controlled test before traffic finds it for you.

- **Tools**: k6 or Locust (scriptable, CI-friendly), Gatling, JMeter, Vegeta or wrk for quick HTTP benchmarks.
- **Test types**: load (expected peak), stress (beyond peak to find the limit), spike (sudden surge), soak/endurance (hold load 4–24h to surface memory leaks and resource exhaustion), and breakpoint/capacity (ramp until it fails to locate the knee of the latency curve).
- **Set pass/fail thresholds up front**: target RPS, p95 and p99 latency ceilings, and a max error rate (for example p99 < 500 ms and error rate < 0.1% at 2x expected peak). A load test with no thresholds is a demo, not a test.
- **Realistic conditions**: production-like data volume, representative payload mix, and cold caches where that matters. Warm-cache tests lie about real capacity.
- **Chaos engineering**: inject faults deliberately (instance kill, latency, packet loss, AZ outage, dependency failure) with a defined steady-state hypothesis and a blast-radius limit. Run scheduled gamedays. Tools: a Chaos Monkey-style killer, fault-injection meshes.
- Pitfalls: load-testing a single instance and extrapolating, ignoring downstream dependency limits (DB connections, third-party rate limits), running once and never again, no abort/kill switch on the test itself.

## Incident response and runbooks

Reduce time-to-mitigation. Roles and runbooks are decided before the incident, not during it.

- **Severity levels** with explicit response targets: SEV1 (full outage or data loss, immediate page, all-hands), SEV2 (major degradation, page on-call), SEV3 (minor, business-hours ticket), SEV4/5 (low impact). Define each in writing so paging is unambiguous.
- **Roles**: Incident Commander (owns the response, makes decisions, does not debug), Operations/Ops Lead (executes the fixes), Communications Lead (status page and stakeholder updates), Scribe (timeline). For small incidents one person may hold several, but the IC role is always explicit.
- **Track the operational metrics**: MTTD (detect), MTTA (acknowledge), MTTR (resolve), MTBF (between failures). Drive MTTA and MTTR down with better alerts and runbooks.
- **On-call**: PagerDuty or Opsgenie with a tiered escalation policy and a documented secondary. Cap pages per shift; sustained pager fatigue is an incident in itself. Every page must be actionable.
- **Runbook structure**, one per known failure mode: symptoms and the alert that fires, dashboards/queries to confirm, step-by-step mitigation, escalation path, and post-mitigation verification. Keep them next to the alert that triggers them.
- **Alerts**: symptom-based (user-facing SLO burn), not cause-based noise. Every alert links to a runbook. Delete alerts nobody acts on.
- **Blameless postmortem** within 5 business days for every SEV1/SEV2: timeline, contributing factors, what went well, action items with owners and due dates tracked to closure. Blame the system and the gaps, never the engineer.

## Disaster recovery

Plan for the loss of a region, a database, or a backup, and prove the plan by exercising it.

- **RTO** (max acceptable time to restore service) and **RPO** (max acceptable data loss window) per service. These two numbers drive every DR decision and the cost.
- **DR tiers**, choose per RTO/RPO and budget: backup-and-restore (cheapest, RTO in hours), pilot light (core minimal stack always on), warm standby (scaled-down running copy), hot standby / active-active multi-region (lowest RTO/RPO, highest cost).
- **Backups**: 3-2-1 (three copies, two media, one off-site). Encrypt backups, and make at least one copy immutable/WORM to survive ransomware and accidental deletion. Cross-region replication for the critical data store.
- **Test restores on a schedule.** An untested backup is a hypothesis. Verify the restored data is consistent and within RPO, and that a full restore meets RTO.
- **DR drills / failover gamedays**: actually fail over to the standby region on a cadence and measure against RTO/RPO. Document the region-failover runbook and keep it current.
- Pitfalls: backups that have never been restored, replication lag that silently violates RPO, a DR region missing the latest IaC changes, a failover runbook that assumes the primary is reachable.

## Mandatory competencies carried into SRE work

These project rules apply to every change an SRE ships (tooling, pipelines, runbook automation, load harnesses):

- **TDD is mandatory** (Red, Green, Refactor). Write the failing test first, including for IaC modules, deployment scripts, and alerting logic. Follow SOLID and keep modules small with clear contracts. Preserve existing docstrings and comments unrelated to your change.
- **QA**: mandatory unit and integration tests for all new code and logic changes. Mock every external API and cloud service so tests run hermetically and offline. Verify any backtesting or simulation logic explicitly where present.
- **ML/quant guards** (whenever SRE touches numeric or model-adjacent automation, capacity forecasting, or autoscaler tuning): validate tensor/array shapes before critical operations, guard against division-by-zero and float overflow, use cross-validation and out-of-sample tests, and ensure zero data leakage. If you formulate any model hypothesis, state target Sharpe ratio, drawdown limit, profit factor, latency and slippage constraints, the dataset and features, and the model architecture.
- **Security (STRIDE)** during design of every pipeline and endpoint: Spoofing (authenticate service identities), Tampering (sign artifacts and configs), Repudiation (immutable audit logs), Information Disclosure (encrypt in transit and at rest, strip secrets from logs and error messages), Denial of Service (rate limits, timeouts, payload-size caps, load shedding — directly your availability concern), Elevation of Privilege (least privilege, RBAC on every endpoint). Keep credentials in a secret manager, never in git history.
- **Observability**: emit structured JSON logs carrying `trace_id` and `span_id`, instrument counters/gauges/histograms with service/region/operation tags, and propagate W3C trace context across service boundaries so SLIs are measurable end to end.
- **Git Flow and Conventional Commits**: develop on `feature/*` or `bugfix/*`, hotfix production from `hotfix/*` off main. Commit as `type(scope): description` in the imperative, first line under 72 characters, no emojis.

## Definition of done

- [ ] Every critical user journey has an SLI, an SLO with an explicit rolling window, and a documented error-budget policy.
- [ ] Multiwindow burn-rate alerts page on fast burn and ticket on slow burn; every alert links to a runbook.
- [ ] No single points of failure; N+1 capacity and at least two AZs verified by an actual failover test.
- [ ] Outbound calls have timeouts, backoff-with-jitter retries, and a circuit breaker or load-shedding fallback.
- [ ] Infrastructure is in version-controlled IaC with remote locked state; no manual production changes.
- [ ] Deploys are canary or blue/green with automated rollback that completes in minutes; rollback has been exercised.
- [ ] Schema migrations are backward-compatible (expand/contract).
- [ ] Load test with defined RPS and p95/p99 latency and error-rate thresholds passes at 2x expected peak; a soak test ran clean.
- [ ] Severity levels, on-call escalation, and incident roles are documented; runbooks exist for known failure modes.
- [ ] RTO and RPO are defined per service; backups follow 3-2-1 with one immutable copy and a verified restore.
- [ ] A DR failover drill ran within the agreed cadence and met RTO/RPO.
- [ ] STRIDE threats reviewed (DoS mitigations in place); secrets in a manager, not git; error messages stripped of internals.
- [ ] New code has unit and integration tests with all external services mocked; TDD followed.
- [ ] Blameless postmortems for SEV1/SEV2 closed with owned, dated action items.
- [ ] Branch follows Git Flow; commits follow Conventional Commits with no emojis.
