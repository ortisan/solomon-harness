# ADR-0027: Layering per-issue claims on safety floor

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
- **Rejected: SurrealDB compare-and-set as the mutual-exclusion authority.** Raised during the #51 refinement; rejected because ADR-0010 already ruled out database-backed guards for exactly this arbitration job: under the SQLite fallback each worktree has its own database file, so no database write can arbitrate cross-worktree exclusion. The memory layer keeps a best-effort mirror for queryability only.

## Decision outcome

Chosen option: **Option 2 (Layer)**, because it preserves the repository-level safety floor for headless cadence runs (satisfying ADR-0010 constraints against concurrent git/config corruption) while introducing fine-grained issue isolation that allows multiple parallel developer worktrees or serialized/coordinated loop tasks to progress without double-picking.

### Consequences

- Positive: Enables safe parallel sessions by preventing double-picking at the issue level. An issue is leased to a session id; concurrent sessions attempting to start or loop-scan it will skip or reject it.
- Negative: Additional complexity of managing two distinct locking/leasing mechanisms (repo-wide single-driver lock vs per-issue claim/lease).
- Follow-ups:
  - Implement claim acquisition in `solomon-start`, filter in `solomon-loop`, claim cleanup on merge/release, stale reclaim via a 30-minute heartbeat TTL, and CLI commands `claim status` / `claim release` (shipped).
  - Heartbeat writer (shipped): a `start` stage that runs longer than the claim TTL before a PR exists must not become reclaimable mid-implementation. `workflows.run_stage` spawns a daemon thread after a successful claim that periodically calls `claim.refresh_claim` (default every 600 seconds, overridable via `SOLOMON_CLAIM_HEARTBEAT_INTERVAL_SECONDS`), and stops it in a `finally` block regardless of how the stage ends.
  - Fail-closed reclaim (shipped): a reclaim decision that cannot confirm the issue's PR/review liveness (a `gh` failure, not merely "no PR found") must never steal an existing claim. `claim_issue` treats a liveness check that could not be determined as if the existing claim were still active; only a verifiably unclaimed issue, or the same session re-entering its own claim, proceeds regardless of liveness uncertainty.
  - A `ClaimStore` port/hexagonal extraction (separating the git-CAS mechanics behind an interface) is tracked separately and intentionally deferred; this ADR's implementation keeps the claim logic as a single `solomon_harness/claim.py` module.

## Storage and read path

The store is **hybrid**, with one authoritative layer and one best-effort mirror:

- **Authoritative: git CAS on `refs/claims/issue-N`.** Every decision that
  grants, denies, or revokes a claim (`claim_issue`, `release_claim`,
  `is_claim_active`) reads and writes only this ref, compare-and-swapped via
  `git push --force-with-lease`. It is the only substrate visible across
  every worktree of the repository and under the SQLite memory fallback, so
  it is the sole source of truth for mutual exclusion.
- **Best-effort mirror: the project memory (SurrealDB, or its SQLite
  fallback).** `claim_issue` and `release_claim` also write/clear a `Claim`
  record (`claim:issue-N`) through the existing `DatabaseClient.save_memory`
  path, purely so the current holder is queryable via the memory MCP tools
  and the session-start digest (`claim.get_claim_holder`) without a live git
  fetch. This mirror is never consulted to decide whether a claim can be
  taken, stolen, or released, and a failure writing or clearing it
  (SurrealDB unreachable, SQLite locked) is logged and swallowed — it can
  never change a claim operation's boolean result.

### Degraded-mode behavior

- **Memory layer down (SurrealDB unreachable, SQLite fallback busy).** The
  git ref still governs every claim decision unchanged; only the mirror
  write/clear is skipped (logged at warning level), so the digest and MCP
  tools may show a stale or missing holder until the memory layer recovers,
  while `start`/`release` correctness is unaffected.
- **Git or network down (no `origin`, offline, `git`/`gh` unavailable).**
  Reads that filter a list of issues for display (`MemoryService.get_open_issues`,
  the direct board-scan path in `solomon_harness.github.list_open_issues`,
  and `claim.filter_unclaimed`) degrade to the unfiltered list rather than
  failing the scan, and log a warning rather than passing silently — the
  scan becomes noisier (a claimed issue can still surface), never unsafe,
  because the real enforcement is `claim_issue`'s own CAS at `start` time,
  not the scan.
  - The **reclaim** decision inside `claim_issue` is the one exception to
    "degrade to unfiltered and proceed": when it cannot confirm PR/review
    liveness for an issue that already has an existing claim, it fails
    closed and refuses to steal that claim, rather than risking a double-pick
    on a transient `gh` outage.

## More information

This decision is also recorded in the project memory via `save_decision`.
