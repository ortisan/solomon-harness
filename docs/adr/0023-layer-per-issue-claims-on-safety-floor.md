# ADR-0023: Layering per-issue claims on safety floor

- Status: accepted
- Date: 2026-07-06
- Deciders: software_architect, software_engineer, scrum_master
- Issue: #51

## Context and problem statement

In a concurrent development environment where multiple sessions (both headless cadence loops and interactive developer sessions) can run on the same repository, there is a risk that sessions double-pick or collide on the same issue. ADR-0010 introduced a repo-wide single-driver lock to serialize headless cadence drivers and prevent worktree/git configuration corruption. However, the repo-wide lock blocks concurrent execution entirely, preventing safe parallel development even on different issues. We need to introduce a mechanism (per-issue claim/lease) that enables concurrency while preventing collision, and reconcile this with the existing single-driver lock concurrency model.

## Decision drivers

- Concurrency and safety: Concurrent sessions must be able to run in parallel without double-picking the same issue.
- Maintain safety floor: We must preserve the repository-level protections of the single-driver lock (ADR-0010) for headless loops.
- Bounded scope: The claim mechanism should isolate issues at the issue level.
- Robustness: The mechanism must be resilient to unstable memory layers (e.g. SurrealDB connection dropouts) and process crashes (stale leases).

## Considered options

- **Option 1: Replace the repo-wide lock with per-issue claims.** Completely discard the repo-wide lock in favor of per-issue lease files/records.
- **Option 2: Layer per-issue claims on top of the repo-wide lock.** Keep the repo-wide lock to serialize headless cadence runs (preventing git/workspace/hook races) and add per-issue claims to isolate issues across all runs (including interactive developers or different worktrees).

## Decision outcome

Chosen option: **Option 2 (Layer)**, because it preserves the repository-level safety floor for headless cadence runs (satisfying ADR-0010 constraints against concurrent git/config corruption) while introducing fine-grained issue isolation that allows multiple parallel developer worktrees or serialized/coordinated loop tasks to progress without double-picking.

### Consequences

- Positive: Enables safe parallel sessions by preventing double-picking at the issue level. An issue is leased to a session id; concurrent sessions attempting to start or loop-scan it will skip or reject it.
- Negative: Additional complexity of managing two distinct locking/leasing mechanisms (repo-wide single-driver lock vs per-issue claim/lease).
- Follow-ups: Implement claim acquisition in `solomon-start`, filter in `solomon-loop`, claim cleanup on merge/release, stale reclaim via a 30-minute heartbeat TTL, and CLI commands `claim status` / `claim release`.

## More information

This decision is also recorded in the project memory via `save_decision`.
