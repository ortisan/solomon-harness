# Plan: Per-issue claim/lease so concurrent sessions never double-pick an issue

Link to issue: #51

## Problem Statement

When concurrent or parallel automation/developer sessions run on the same repository, they can select and work on the same issue simultaneously. This results in collisions, duplicate work trees, and race conditions on git/board state. We need a per-issue claim/lease mechanism to guarantee mutual exclusion at the issue level, while preserving the repository-level single-driver safety floor from ADR-0010.

## Proposed Change and Boundary

We will introduce a per-issue lease mechanism:
1. **Durable Lease Source of Truth (Git CAS)**: The lease is represented by a remote git reference `refs/claims/issue-<number>`. The reference points to an empty commit object whose commit message is a JSON record containing:
   - `session_id`: Unique identifier for the claiming session (from environment `SOLOMON_SESSION_ID` / `CLAUDE_SESSION_ID` or hostname/pid).
   - `acquired_at`: ISO timestamp of acquisition.
   - `heartbeat_at`: ISO timestamp of the latest heartbeat refresh.
2. **Atomic Compare-And-Swap (CAS)**:
   - To claim: we attempt to push a new commit to `refs/claims/issue-<number>` using `--force-with-lease=refs/claims/issue-<number>:`, expecting it to not exist.
   - To reclaim a stale lease: we force-push using `--force-with-lease=refs/claims/issue-<number>:<old-sha>`.
3. **Lease Liveness Criteria**: A lease is active if:
   - It is held by another session AND the elapsed time since its `heartbeat_at` / `acquired_at` is <= 30 minutes.
   - **OR** it is protected because the issue has an open in-review Pull Request or is in `Code Review` / `QA` status on the project board.
4. **Integration**:
   - **Start stage (`/solomon-start`)**: Atomically claims the issue before creating the branch/worktree/PLAN/PR. Rejects the operation if another session holds an active lease. Assigns the issue to the harness user as a fast-scan indicator.
   - **Loop stage (`/solomon-loop`)**: Fetches all claims from the remote using `git ls-remote` / `git fetch refs/claims/*` and filters out any active claimed issues from candidate selection.
   - **Release/Release-prep/Done transitions**: Releases the claim upon closing/merging the issue or manually via the CLI.
   - **CLI interface**: `solomon-harness claim status <issue>` and `solomon-harness claim release <issue>`.

## Target Files

- `solomon_harness/claim.py` (New module)
- `solomon_harness/cli.py` (Expose `claim status` / `claim release` subparsers)
- `solomon_harness/workflows.py` (Interpose claim checks before `start` / filter in `loop`)
- `tests/test_claim.py` (New unit & integration tests)

## STRIDE Notes

- **Spoofing**: We identify sessions using a session ID. Inside the same runner, session ID is unique (derived from pid/host).
- **Tampering**: Claims are written as git commits to `refs/claims/*`. This leverages Git's integrity validation and remote branch protection.
- **Repudiation**: The commit message holds the session details, creating an immutable audit trail of who leased what.
- **Information Disclosure**: Claims do not store PII, only metadata.
- **Denial of Service**: Heartbeat TTL of 30 minutes allows automatic stale claim takeover in case of session crashes.

## Edge Cases and Observable Outcomes

- **Race to claim**: If two sessions run `/solomon-start 51` concurrently, only one git push succeeds; the second receives a non-fast-forward/rejected push error and aborts with a clear message.
- **Stale claim with active PR**: If a session crashes but already opened a PR, the claim is NOT reclaimable until the PR is merged/closed.
- **Heartbeat re-entry**: A nested workflow stage (running under the same parent session) inherits the same `session_id` and can re-enter/update the lease.

## TDD Steps

1. **Step 1 (Red)**: Write unit tests in `tests/test_claim.py` for parsing claim metadata, calculating TTL liveness, and determining stale reclaims.
2. **Step 2 (Green)**: Implement `solomon_harness/claim.py` base logic: `get_current_session_id`, parsing JSON from commits, and liveness check.
3. **Step 3 (Red)**: Write tests for atomic claim pushing (`claim_issue`), stale reclaiming, and releasing claims.
4. **Step 4 (Green)**: Implement `claim_issue`, `release_claim`, and `fetch_all_claims` using git subprocesses with `--force-with-lease`.
5. **Step 5 (Red/Green)**: Integrate claim check into `solomon_harness/workflows.py` `run_stage` for `stage == "start"`. Write test verifying a start on a claimed issue is blocked.
6. **Step 6 (Red/Green)**: Integrate claimed issue filtering in `solomon_harness/memory_service.py` `get_open_issues` (or similar loop scan points). Write test verifying loop excludes active claimed issues.
7. **Step 7 (Red/Green)**: Expose `claim status` / `claim release` subparsers in `solomon_harness/cli.py`. Write CLI integration tests.

## Verification Criteria

- Run `pytest tests/test_claim.py` and verify all tests pass.
- Run complete `pytest` suite and ensure no regressions.
- Verify `solomon-harness claim status 51` prints status when claimed.
