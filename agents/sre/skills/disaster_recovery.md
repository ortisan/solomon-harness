## Disaster recovery


Plan for the loss of a region, a database, or a backup, and prove the plan by exercising it.

- **RTO** (max acceptable time to restore service) and **RPO** (max acceptable data loss window) per service. These two numbers drive every DR decision and the cost.
- **DR tiers**, choose per RTO/RPO and budget: backup-and-restore (cheapest, RTO in hours), pilot light (core minimal stack always on), warm standby (scaled-down running copy), hot standby / active-active multi-region (lowest RTO/RPO, highest cost).
- **Backups**: 3-2-1 (three copies, two media, one off-site). Encrypt backups, and make at least one copy immutable/WORM to survive ransomware and accidental deletion. Cross-region replication for the critical data store.
- **Test restores on a schedule.** An untested backup is a hypothesis. Verify the restored data is consistent and within RPO, and that a full restore meets RTO.
- **DR drills / failover gamedays**: actually fail over to the standby region on a cadence and measure against RTO/RPO. Document the region-failover runbook and keep it current.
- Pitfalls: backups that have never been restored, replication lag that silently violates RPO, a DR region missing the latest IaC changes, a failover runbook that assumes the primary is reachable.
