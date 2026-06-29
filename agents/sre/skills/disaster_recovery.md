# Disaster Recovery: RTO, RPO, and Tested Restores

Plan for the loss of a region, a database, or an entire backup, and prove the plan by exercising it on a cadence.

Disaster recovery is the discipline of restoring service after a failure that local redundancy cannot absorb: a region outage, a corrupted primary database, a deleted bucket, a ransomware event. In-region high availability (covered in `high_availability`) protects against single-component loss; DR protects against losing the whole blast radius. Every DR decision flows from two numbers per service, and the cost of the design scales with how aggressive those numbers are.

## RTO and RPO drive every decision

- **RTO** (Recovery Time Objective): the maximum acceptable time from the start of the disaster to restored service. It dictates the topology you pay for.
- **RPO** (Recovery Point Objective): the maximum acceptable data loss, measured backward in time from the disaster. It dictates replication or backup frequency. An RPO of 1 minute means you cannot lose more than 1 minute of writes, so asynchronous replication lag must stay under 1 minute or you are silently out of compliance.

Classify each service into a tier and assign RTO/RPO and a topology. A worked tier ladder:

| Tier | Example service | RTO | RPO | DR topology | Relative cost |
| --- | --- | --- | --- | --- | --- |
| 0 mission-critical | payments, auth | < 1 min | ~0 | active-active multi-region | 2x+ |
| 1 core | primary API + DB | < 15 min | < 1 min | warm standby + replica | ~1.4x |
| 2 supporting | internal tools | < 4 h | < 1 h | pilot light | ~1.1x |
| 3 batch/reporting | analytics, exports | < 48 h | < 24 h | backup and restore | minimal |

## DR topologies and their trade-offs

| Topology | How it works | RTO | RPO | Cost |
| --- | --- | --- | --- | --- |
| Backup and restore | Restore from backups into freshly provisioned infra | hours | hours | lowest |
| Pilot light | Core data replicated, minimal always-on stack; scale up on failover | tens of min | minutes | low |
| Warm standby | Scaled-down full copy running in the DR region; scale up and cut over | minutes | seconds-minutes | medium |
| Hot / active-active | Both regions serve live traffic behind global routing | seconds | ~zero | highest |

Move up the ladder only when the service tier and the SLA justify the spend. Active-active doubles infrastructure and forces you to solve data conflict resolution and global consistency, so reserve it for Tier 0.

## Backups: 3-2-1, immutable, verified

Follow **3-2-1-1-0**: three copies, on two media types, one off-site, one immutable/air-gapped, with zero errors after a verified restore. Encrypt every backup at rest with a KMS key whose custody is separate from the data so a single compromised account cannot both read and delete. Make at least one copy WORM (S3 Object Lock in compliance mode, or equivalent) so ransomware and accidental `delete` cannot reach it. Replicate the critical data store cross-region.

**Worked RPO check.** Suppose Tier 1 demands RPO < 1 min but the read replica's `replication_lag` p99 is 5 min during peak write load. The design is non-compliant: a region loss at peak loses up to 5 minutes of writes. The fix is synchronous or semi-synchronous replication for the commit path, smaller transaction batches, or a stricter alert on lag (`page when replication_lag > 30s for 5m`).

## DR drills and game days

An untested backup is a hypothesis, not a recovery plan. Two cadences:

- **Restore test (monthly):** restore the latest backup into an isolated environment, run integrity and consistency checks, confirm the data is within RPO, and measure the actual restore time against RTO.
- **Regional failover game day (quarterly):** actually fail over to the standby region, serve synthetic or shadow traffic, and time the cutover end to end. Treat the run like an incident, with an Incident Commander and a scribe (see `incident_response_and_runbooks`).

Keep a region-failover runbook that does **not** assume the primary is reachable: DNS/global-routing cutover, replica promotion, secret and config availability in the DR region, and a reverse path to fail back without data loss. Verify the DR region receives the same IaC changes as primary so it never drifts into an unbootable state.

## Common pitfalls

- Backups that have never been restored: you discover the format is unreadable or a table is missing during the real disaster. Reviewers reject any backup plan without a scheduled, timed restore test.
- Asynchronous replication whose lag silently exceeds the RPO: the design looks compliant on paper but loses more data than allowed. Alert on lag against the RPO threshold.
- A DR region missing the latest IaC, secrets, or images: failover lands on a stale or unbootable stack. The DR region must be in the same pipeline as primary.
- A failover runbook that assumes the primary is up (reads its DNS, its secrets, its config): it cannot run during the exact failure it exists for.
- Treating multi-AZ redundancy as DR: a region-wide or account-wide event takes all AZs at once. DR requires a separate region or provider.
- No immutable/air-gapped copy: ransomware or a credential leak deletes both the primary and the backups. At least one copy must be WORM.

## Definition of done

- [ ] Every service has an assigned tier with explicit RTO and RPO, signed off by the product owner.
- [ ] The DR topology per tier is documented and matches the RTO/RPO targets and budget.
- [ ] Backups follow 3-2-1-1-0, are encrypted, and include at least one immutable copy; the critical store replicates cross-region.
- [ ] A restore is tested monthly into an isolated environment, with measured restore time and an RPO-compliance check recorded.
- [ ] A regional failover game day runs at least quarterly, timed against RTO, and produces action items tracked to closure.
- [ ] The region-failover runbook is current, assumes the primary is unreachable, and covers cutover, replica promotion, and fail-back.
- [ ] Replication lag is monitored and alerts before it breaches the RPO.
- [ ] DR infrastructure and runbooks are committed as code, reviewed, and version-controlled per Git Flow and Conventional Commits.
