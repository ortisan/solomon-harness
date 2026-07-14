---
name: replication-and-high-availability
description: Covers replicating PostgreSQL and surviving node loss: streaming physical replication, logical replication, the sync versus async durability trade-off, and automated failover with Patroni. Use when designing a high-availability topology or reviewing a failover or promotion decision.
---

# Replication and High Availability

How to replicate PostgreSQL and survive node loss: streaming physical replication, logical replication, the synchronous/asynchronous durability trade, and automated failover with Patroni. The stance: replication settings are an RPO/RTO contract written in configuration; decide the acceptable data loss and downtime first, then derive the topology, and never let an automation and a human fight over who promotes.

## Streaming (physical) replication

The default HA building block: the standby replays the primary's WAL byte-for-byte, so it is an exact physical copy, same major version, whole cluster.

- `wal_level = replica`, standbys created from a base backup (`pg_basebackup` or pgBackRest restore) with `primary_conninfo` set.
- Always use replication slots so the primary retains WAL a disconnected standby still needs, and always cap them: `max_slot_wal_keep_size` (for example `100GB`). An uncapped slot for a dead standby fills the primary's disk and takes the whole service down; this is one of the most common self-inflicted PostgreSQL outages.
- Hot standby serves read-only queries. Long-running standby queries conflict with WAL replay; choose between query cancellation (`max_standby_streaming_delay`, default 30 s) and primary-side bloat (`hot_standby_feedback = on` makes the primary retain dead tuples for standby queries). Analytics standbys often run with feedback off and generous delay, accepting cancellations.
- Monitor lag in bytes, per standby, from the primary:

```sql
SELECT application_name,
       pg_wal_lsn_diff(pg_current_wal_lsn(), replay_lsn) AS replay_lag_bytes,
       write_lag, flush_lag, replay_lag
FROM pg_stat_replication;
```

## Synchronous vs asynchronous: the RPO decision

Asynchronous (default): commits return after local flush; a primary loss loses whatever the standby had not received. RPO is the replication lag at failure time (typically milliseconds, unbounded under load spikes).

Synchronous: `synchronous_standby_names` plus `synchronous_commit` define the contract per transaction:

| `synchronous_commit` | Guarantee on commit return | Cost |
| --- | --- | --- |
| `off` | Not even local durability (bounded loss window on crash) | Fastest; only for expendable writes |
| `local` | Flushed on primary only | Async replication behavior |
| `remote_write` | Standby received and handed to OS | Small added latency; loses on simultaneous OS crash |
| `on` (default when sync names set) | Standby flushed WAL to disk | RPO zero for acknowledged commits |
| `remote_apply` | Standby applied it (visible to reads) | Highest latency; read-your-writes on standby |

- Use quorum: `synchronous_standby_names = 'ANY 1 (s1, s2)'` so one slow or dead standby does not freeze all commits. With exactly one sync standby and no quorum, that standby's failure blocks every write on the primary: a self-built availability outage in exchange for durability.
- `synchronous_commit` is settable per transaction (`SET LOCAL synchronous_commit = off`) so bulk or low-value writes skip the sync tax while money-moving writes keep it.

## Logical replication

Publications/subscriptions replicate row changes, not bytes: works across major versions, replicates a subset of tables, targets a writable cluster.

- Use it for: near-zero-downtime major upgrades (PG17+ `pg_createsubscriber` converts a physical standby into a logical subscriber), selective data distribution, and feeding downstream systems.
- Know the limits: DDL is not replicated (schema changes must be applied on both sides, subscriber first for additive changes), sequences are not replicated (resync them at cutover), and large transactions replay with latency. Conflicts on the subscriber (unique violations) stop the subscription until resolved.
- PostgreSQL 17 added failover slots (`failover = true` on the slot plus `sync_replication_slots = on` on the standby), so logical subscribers survive a physical failover of their publisher; before 17, a failover silently orphaned logical slots.

## Failover with Patroni

Manual failover fails at 3 a.m. The house pattern is Patroni (4.x) managing PostgreSQL under a distributed consensus store (etcd, Consul, or Kubernetes objects).

- Mechanics: the leader holds a lease in the DCS (`ttl` default 30 s, `loop_wait` 10 s, `retry_timeout` 10 s). If the leader cannot renew, replicas race to acquire the lock; eligibility respects `maximum_lag_on_failover` (default 1 MB) so a badly lagged replica does not win and amplify data loss.
- Fencing: a primary that loses DCS connectivity demotes itself when the lease expires; that self-demotion is what prevents split-brain. Enable the DCS failsafe mode deliberately (it keeps the primary running through a total DCS outage when all members are reachable) and understand the trade before turning it on. On bare metal, add the watchdog device so a hung Patroni process cannot leave a zombie primary.
- Set `use_pg_rewind: true` so the demoted old primary can rejoin by rewinding its diverged WAL instead of requiring a full re-clone (requires `wal_log_hints = on` or data checksums).
- With `synchronous_mode: true` Patroni only promotes a standby that was synchronous, making failover lossless; `synchronous_mode_strict` refuses to disable sync replication even when no standby is available (durability over availability, chosen explicitly). Patroni 4 also supports quorum commit.
- Operate through Patroni, never around it: `patronictl switchover` (planned, zero data loss), `patronictl failover` (forced), `patronictl restart/reload`. A manual `pg_ctl promote` behind Patroni's back creates the split-brain the whole system exists to prevent. Route applications via the Patroni-aware entrypoint (HAProxy on the REST `/primary` health check, or `target_session_attrs=read-write` in libpq multi-host DSNs).

MySQL note: the equivalent decisions live in semi-synchronous replication or Group Replication with GTIDs plus an orchestrator; the same RPO/quorum/fencing reasoning applies, but tooling differs enough that the design should be re-derived, not copied.

## Common pitfalls

- Replication slot for a decommissioned standby left in place with no `max_slot_wal_keep_size`; primary disk fills, everything stops.
- Single synchronous standby without `ANY` quorum: its reboot freezes all commits on the primary.
- Treating async lag as zero; the one time it matters (failover under peak load), minutes of writes are gone.
- `hot_standby_feedback = on` for a standby running 6-hour analytics queries, silently bloating the primary.
- Logical replication cutover without resyncing sequences; the new primary immediately throws duplicate-key errors.
- Promoting manually while Patroni holds the leader lock: two primaries, diverged WAL, restore-from-backup afternoon.
- Failover tested never, or only on an idle cluster; lag-gated promotion and client rerouting behave differently under load.
- DCS sized or placed carelessly (single etcd node, or etcd sharing disks with the database), making the consensus layer the least available component.

## Definition of done

- [ ] RPO and RTO are stated numbers agreed with the service owner; the sync/async choice and quorum layout are derived from them and recorded in an ADR.
- [ ] Replication slots are used and capped with `max_slot_wal_keep_size`; slot health and byte lag are alerted on.
- [ ] Synchronous setups use `ANY n (...)` quorum; per-transaction `synchronous_commit` downgrades are documented where used.
- [ ] Patroni (or the chosen failover manager) is the only actor that promotes; runbooks use `patronictl`; `use_pg_rewind` and lag-gated failover are configured.
- [ ] Client routing follows the leader automatically (health-checked proxy or multi-host DSN); no hardcoded primary IPs.
- [ ] Logical replication designs account for DDL, sequence, and conflict handling; failover slots enabled on PG17+.
- [ ] Failover is drilled on a loaded staging cluster at least quarterly: kill the primary, measure detection, promotion, client recovery, and data loss against the stated RPO/RTO.
