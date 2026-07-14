---
name: backup-recovery-and-pitr
description: Sets the PostgreSQL backup standard: logical dumps versus physical base backups, continuous WAL archiving, point-in-time recovery, and the restore drills that make RPO/RTO numbers real. Use when designing a backup strategy, planning a recovery, or reviewing whether RPO/RTO is rehearsed.
---

# Backup, Recovery, and PITR

The standard for PostgreSQL backups: logical dumps versus physical base backups, continuous WAL archiving, point-in-time recovery, and the drills that make RPO/RTO numbers real. The stance: a backup that has not been restored recently is a hope, not a backup; the deliverable of this skill is a measured, rehearsed recovery, and the backup is merely its input.

## Choose the mechanism by what you need back

| Property | Logical (`pg_dump`/`pg_dumpall`) | Physical (base backup + WAL) |
| --- | --- | --- |
| Granularity | Database/schema/table | Whole cluster only |
| Cross-version/arch restore | Yes (standard upgrade path) | No (same major, same platform) |
| Point-in-time recovery | No: snapshot at dump start | Yes: any instant in the archive window |
| Restore speed at scale | Slow (rebuild + reindex everything) | Fast (copy back + replay) |
| Size/cost | Compact | Larger; incrementals mitigate |

Production databases of any size get physical backups with WAL archiving as the primary mechanism; logical dumps are the complement for per-table restore, seeding environments, and major-version moves. They are not alternatives; run both where the data matters.

Logical specifics: use the custom or directory format, parallel where possible: `pg_dump -Fd -j 8 -f /backup/app db` and `pg_restore -j 8`. `pg_dump` is consistent (one snapshot for the whole run) and does not block writers. It excludes globals (roles, tablespaces): capture them with `pg_dumpall --globals-only` or the restore recreates tables owned by nobody.

Never "back up" a running cluster by copying the data directory with `cp`/`rsync` outside the backup API; the copy is torn and will not start.

## WAL archiving and PITR

Continuous archiving turns backups from daily snapshots into a timeline you can rewind to any second:

- `archive_mode = on` with an `archive_command` (or `archive_library`) that is atomic, verifies success, and never overwrites an existing segment. If archiving fails, PostgreSQL retains WAL locally and `pg_wal` grows until the disk fills: alert on `pg_stat_archiver.failed_count` and on archive lag.
- `archive_timeout` (for example `60s`) bounds RPO on quiet systems by forcing segment switches; with it, the worst-case loss from losing the primary and its disk is roughly one timeout interval plus copy time.
- PITR: restore the most recent base backup before the target moment, provide `restore_command`, set the target, and choose what happens on arrival:

```ini
restore_command = 'pgbackrest --stanza=main archive-get %f "%p"'
recovery_target_time = '2026-07-03 14:31:00+00'
recovery_target_action = 'pause'   # inspect before promoting
```

  Recovery pauses at the target; verify the data (is the bad `DELETE` absent?), then `SELECT pg_wal_replay_resume()` or promote. Every promotion starts a new timeline; the archive keeps old timelines so a wrong target can be retried.
- The canonical PITR use case is not hardware loss (replicas cover that) but human error: a bad migration or an unqualified `UPDATE`. Recover to the instant before the mistake on a separate instance, extract the damaged rows, and repair the live database surgically instead of rolling the whole service back in time.

## Tooling

Do not hand-roll archive scripts. pgBackRest (2.x) is the house default: full/differential/incremental backups, parallel and compressed (zstd), repository encryption, S3/Azure/GCS targets, retention policies (`repo1-retention-full=2`), automatic WAL archiving integration, and `--type=time` restores that write the recovery configuration for you. Barman is an acceptable alternative. Plain `pg_basebackup` suits small setups; PostgreSQL 17 adds native incremental backups (`pg_basebackup --incremental` with `summarize_wal = on`, combined at restore with `pg_combinebackup`), but a managed tool still earns its keep in retention, verification, and restore ergonomics.

Verify integrity continuously: enable data checksums on the cluster, run `pgbackrest verify` on the repository, and treat backup-job success as a metric with an alert on staleness (no successful full within the policy window).

## RPO, RTO, and the drill

Write the two numbers down per service and derive the design:

- RPO (max acceptable data loss): nightly dumps give RPO up to 24 h; WAL archiving gives roughly `archive_timeout`; synchronous replication gives near zero. Backups and replication answer different failures: replication faithfully replicates the operator's mistake within milliseconds, so it never replaces PITR.
- RTO (max acceptable downtime): dominated by restore-and-replay time, which grows with database size and distance from the last base backup. Frequent incrementals shorten replay; a warm standby restored continuously from the archive (delayed replica) can cut RTO for the human-error case.
- Retention: align with business/regulatory needs, for example 2 weekly fulls, daily differentials, 14 days of WAL, plus a monthly archived offsite. Apply 3-2-1: three copies, two media, one offsite/immutable (object lock) so ransomware or a compromised credential cannot erase the last copy.
- Drill quarterly at minimum, and after any topology change: restore to a scratch instance, PITR to an arbitrary timestamp, run application-level validation and `amcheck`, and record the wall-clock time as the measured RTO. The drill also proves the runbook: a restore that requires the one person who wrote the script is a single point of failure.

## Common pitfalls

- Backups taken, restores never tested; the failure is discovered during the incident.
- `archive_command` that fails silently or non-atomically: either corrupt archives or a primary outage from a full `pg_wal`.
- Only replication, no PITR: the bad `DELETE` reaches every replica in milliseconds.
- Logical dumps restored without globals; ownership and grants are wrong everywhere.
- Backup repository on the same storage/account as the database, or deletable with the same credentials the server holds.
- RPO/RTO never written down, so the design is defended with adjectives instead of numbers.
- Restoring a physical backup onto a different major version or architecture and losing hours before reading the error.
- Filesystem-copy "backups" of a running cluster.

## Definition of done

- [ ] RPO and RTO are explicit numbers per service, recorded with the design in an ADR or the project memory.
- [ ] Physical base backups plus continuous WAL archiving run under pgBackRest (or equivalent), with retention policy and offsite/immutable copy configured.
- [ ] Globals are captured alongside logical dumps; per-table restore path exists.
- [ ] Archiving health is monitored: failed archive count, archive lag, backup staleness, repository verification.
- [ ] PITR runbook exists with concrete commands, including target-time recovery, pause-and-inspect, and the surgical-repair variant for human error.
- [ ] A restore drill ran within the last quarter: scratch restore, PITR to arbitrary time, integrity and application validation, measured RTO compared against the target.
- [ ] Backup credentials cannot delete the repository (separate account or object lock); checksums enabled on the cluster.
