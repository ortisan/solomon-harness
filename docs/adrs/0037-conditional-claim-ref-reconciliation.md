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
reads its GitHub and claim snapshots, the release deletes the new version rather
than the version that justified the decision. The review gate for PR #314
identified this time-of-check/time-of-use race. It can remove an active claim and
break ADR-0027's exclusion guarantee.

The same path also needs to distinguish an unavailable claim origin from an
empty claim namespace. A mutating reconciliation pass must not treat a failed
remote read as successful convergence.

## Decision drivers

- Never delete a claim version created or refreshed after the reconciliation
  snapshot.
- Keep the git ref as the sole authority and preserve git's atomic
  compare-and-swap as the linearization point.
- Read the remote claim namespace once without a per-issue GitHub request or a
  mutable local tracking-ref cache.
- Fail closed and report whether a ref was released, changed, already absent,
  or could not be verified.
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
  `ClaimStore` port. The git adapter reads versions with `git ls-remote` and
  deletes with `git push --force-with-lease=<ref>:<observed-version>`.
- **Introduce a transactional coordinator for GitHub and git refs.** Rejected
  because neither system exposes a shared transaction and a new coordinator
  would add infrastructure without removing the cross-system boundary.

## Decision outcome

Chosen option: **delete only the observed ref version**.

`ClaimStore` gains two operations while the existing methods remain unchanged:

- `fetch_versions()` returns one explicit snapshot containing an opaque version
  per issue, plus `ok` and `error`. `GitClaimStore` implements it with one
  `git ls-remote --refs origin 'refs/claims/issue-*'`; it does not update local
  remote-tracking refs. An unavailable or malformed response is not an empty
  result and makes the reconcile command exit non-zero after reporting the
  independent pass results.
- `release_if_version(issue, expected_version)` returns one of `released`,
  `changed`, `missing`, or `failed`. `GitClaimStore` uses the expected version in
  git's force-with-lease delete. A changed ref survives untouched. After a
  failed push, one exact-ref `ls-remote` read classifies the outcome without
  parsing human-facing git output.

A `CLOSED` GitHub snapshot authorizes removal only of the claim version present
in the accompanying claim snapshot. Reopening is a later authoritative event.
A claimant that acquires, re-enters, or heartbeats after reopening writes a new
version, which the conditional delete cannot remove. An unchanged pre-reopen
version remains the old claim and may converge away. This defines the safe
boundary available without a transaction spanning GitHub and git.

The mirror clear, claim audit, and assignee cleanup run only after a successful
conditional delete. A changed or failed comparison performs none of those
secondary mutations.

### Consequences

- Positive: A heartbeat, reclaim, or acquisition after the snapshot wins the
  lease comparison and remains authoritative.
- Positive: Remote-read failure is visible and cannot be reported as zero
  outstanding claim refs.
- Positive: Dry-run performs a remote read but no git push and no mirror or
  assignee mutation.
- Negative: The `ClaimStore` port has two additional result-bearing methods,
  and adapters must implement their explicit version and outcome contracts.
- Negative: A failed conditional push performs one additional exact-ref remote
  read to classify `changed`, `missing`, and `failed`.
- Negative: GitHub issue state and git refs remain separate systems. The design
  provides a safe ref-level linearization point, not a cross-system transaction.
- Follow-ups: none. Existing unconditional release callers retain their current
  contract; only standing reconciliation uses the conditional path.

## More information

- Implements issue #289 in PR #314.
- Extends ADR-0027's authoritative git-CAS invariant, ADR-0030's `ClaimStore`
  port, and ADR-0034's locked closed-issue reconciliation stage.
- The regression test refreshes a claim after the snapshot and proves the old
  version cannot delete the refreshed ref.
- This decision is also recorded in project memory via `save_decision`.
