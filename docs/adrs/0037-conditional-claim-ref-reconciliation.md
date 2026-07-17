# ADR-0037: Conditional claim-ref reconciliation

- Status: accepted
- Date: 2026-07-17
- Amends: ADR-0027, ADR-0030, ADR-0034
- Deciders: software_architect, software_engineer
- Issue: #289

## Context and problem statement

ADR-0027 makes `refs/claims/issue-N` the authoritative cross-worktree
mutual-exclusion record. ADR-0034 permits a locked standing stage to repair
derived state after a GitHub snapshot reports an issue `CLOSED`. The first
implementation of issue #289 combined those decisions by calling
`release(force=True)` for each closed issue with a claim ref.

That combination is unsafe. `release(force=True)` fetches the latest ref before
deleting it. If a claimant refreshes or reacquires the ref after reconciliation
reads its GitHub state, the release deletes the new version rather than the
version that justified the decision. The first review gate for PR #314 identified
this time-of-check/time-of-use race.

A versioned implementation still remained unsafe while it read GitHub first and
the claim refs second: an issue could reopen and acquire a new ref between those
reads, making the later ref snapshot bless the active version for deletion. The
second review gate required the claim-ref snapshot to causally precede the
GitHub-state snapshot. Both races can remove an active claim and break ADR-0027's
exclusion guarantee.

The same path also needs to distinguish an unavailable claim origin from an
empty claim namespace. A mutating reconciliation pass must not treat a failed
remote read as successful convergence.

## Decision drivers

- Never delete a claim version created or refreshed after the claim-ref snapshot,
  including in the interval before the GitHub-state snapshot.
- Keep the git ref as the sole authority and preserve git's atomic
  compare-and-swap as the linearization point.
- Read the remote claim namespace once, before GitHub issue state, without a
  per-issue GitHub request or a mutable local tracking-ref cache.
- Fail closed and report whether a ref was released, changed, already absent,
  or could not be verified.
- Bound aggregate release work while reconciliation owns the repository-wide
  lock; per-subprocess deadlines must not multiply across the full issue cap.
- Bind GitHub cleanup to the same selected workspace as the authoritative git
  delete, even when the parent environment points at another repository.
- Reject non-canonical GitHub number aliases at the bulk-list trust boundary.
- Preserve the existing owner-driven `ClaimStore.release` behavior for merge
  and stage cleanup callers.
- Keep dry-run free of remote deletion, mirror writes, and assignee changes.

## Considered options

- **Force-release the latest ref.** Keep the first implementation and accept
  that `release(force=True)` fetches and deletes whatever version is current.
  Rejected because it can delete a post-snapshot heartbeat or acquisition.
- **Re-read GitHub immediately before every release.** Rejected because it adds
  one API request per claim and still cannot atomically couple GitHub issue
  state to a git-ref deletion.
- **Delete only the ref version observed in one authoritative snapshot.** Add a
  versioned snapshot and a conditional release operation to the existing
  `ClaimStore` port. Capture that snapshot before reading GitHub issue state;
  the git adapter reads versions with `git ls-remote` and deletes with
  `git push --force-with-lease=<ref>:<observed-version>`.
- **Introduce a transactional coordinator for GitHub and git refs.** Rejected
  because neither system exposes a shared transaction and a new coordinator
  would add infrastructure without removing the cross-system boundary.

## Decision outcome

Chosen option: **delete only the observed ref version**.

`ClaimStore` gains two operations while the existing methods remain unchanged:

- `fetch_versions()` returns one explicit snapshot containing an opaque version
  per issue, plus `ok` and `error`. `GitClaimStore` implements it with one
  `git ls-remote --refs origin 'refs/claims/issue-*'`; it does not update local
  remote-tracking refs. Object IDs and canonical `refs/claims/issue-N` names are
  validated. An unavailable or malformed response is not an empty result and
  makes the reconcile command exit non-zero after reporting the independent pass
  results.
- `release_if_version(issue, expected_version)` returns one of `released`,
  `changed`, `missing`, or `failed`. `GitClaimStore` uses the expected version in
  git's force-with-lease delete. A changed ref survives untouched. After a
  failed push, one exact-ref `ls-remote` read classifies the outcome without
  parsing human-facing git output.

The locked command captures the claim-ref snapshot before requesting GitHub
issue state and passes those versions unchanged to reconciliation. A `CLOSED`
GitHub snapshot authorizes removal only of the version present in that earlier
claim snapshot. A claimant that acquires, re-enters, or heartbeats in the
cross-snapshot interval or afterward writes a new version, which the conditional
delete cannot remove. An unchanged version remains the old claim and may
converge away. This is the safe ordering available without a transaction
spanning GitHub and git.

Best-effort mirror clear, claim audit, and assignee cleanup run only after a
successful conditional delete. A changed or failed comparison performs none of
those secondary mutations. These projections are not version-linearized with a
later acquisition: a claimant created after the successful ref deletion remains
authoritative, its heartbeat repairs the mirror, and its assignee may require a
later projection repair.

The assignee cleanup is nevertheless repository-linearized with the delete's
selected workspace: the `gh issue edit` subprocess runs with `workspace_root` as
its working directory and an explicit environment that strips ambient `GIT_*`
context and `GH_REPO`. The same environment and working directory survive the
credential-heal retry. The bulk GitHub state read uses the same environment
hygiene, and accepts only positive canonical integer issue/PR numbers rather
than coercing boolean, floating-point, signed, whitespace, or leading-zero
aliases.

The release pass also has a 60-second aggregate **start budget** while it owns
the repository `LoopLock`. Before each conditional delete it checks elapsed
monotonic time; after the budget it starts no new delete and reports the
remaining issue numbers as deferred. A release that classifies the shared claim
origin as unavailable or malformed opens the same circuit immediately.
Deterministic `changed` and `missing` outcomes continue while budget remains.
An abort is explicit and makes the command exit non-zero only after the other
independent reconciliation summaries have run. One operation already in flight
can finish beyond the start budget, but remains bounded by the existing git and
GitHub subprocess deadlines; the previous issue-count-multiplied worst case is
removed.

### Consequences

- Positive: A heartbeat, reclaim, or acquisition after the earlier claim
  snapshot wins the lease comparison and remains authoritative.
- Positive: Remote-read failure is visible and cannot be reported as zero
  outstanding claim refs.
- Positive: Dry-run performs a remote read but no git push and no mirror or
  assignee mutation.
- Positive: Ambient repository variables cannot redirect the new post-delete
  GitHub mutation or the GitHub state snapshot to a different repository.
- Positive: Origin loss or aggregate budget exhaustion cannot start an
  issue-count-sized sequence of remote timeouts while holding `LoopLock`.
- Positive: Malformed GitHub number aliases cannot select another claim ref.
- Negative: The `ClaimStore` port has two additional result-bearing methods,
  and adapters must implement their explicit version and outcome contracts.
- Negative: A failed conditional push performs one additional exact-ref remote
  read to classify `changed`, `missing`, and `failed`.
- Negative: GitHub issue state and git refs remain separate systems. The design
  provides a safe ref-level linearization point, not a cross-system transaction.
- Negative: Best-effort mirror and assignee cleanup can race a new acquisition
  after a successful delete; this can create projection drift but cannot remove
  the new authoritative ref.
- Negative: A release-pass abort can leave known closed-issue refs deferred to a
  later reconcile run; they are reported explicitly and no active ref is deleted
  speculatively.
- Follow-ups: none. Existing unconditional release callers retain their current
  contract; only standing reconciliation uses the conditional path.

## More information

- Implements issue #289 in PR #314.
- Extends ADR-0027's authoritative git-CAS invariant, ADR-0030's `ClaimStore`
  port, and ADR-0034's locked closed-issue reconciliation stage.
- The real-origin regression refreshes a claim between the ref and GitHub
  snapshots and proves the old version cannot delete the refreshed ref; a
  command-path regression enforces the snapshot order.
- This decision is also recorded in project memory via `save_decision`.
