# Spec 289: force-release claim refs for GitHub-closed issues

- Issue: #289 · Status: implemented
- Date: 2026-07-17 · Author: product_owner

## Context

Raised during follow-up to the 2026-07-16 four-specialist harness verification
audit (qa / dba / loop_engineer / software_architect). The durable issue #289
records the observed orphaned ref; the untracked audit report records the
general claim-release gap but does not preserve the ref's age. This is the
sibling gap left explicitly open by spec 264
(`docs/specs/264-reconcile-outside-release-path.md`), whose Out of Scope section
names "Claim-ref release for closed issues (#289)" directly.

## Problem

`refs/claims/issue-N` is meant to protect an issue only while it is actively
being worked. The only place that ever deletes the ref is
`merge_pr_and_close` (`solomon_harness/github.py:412-433`), called solely by the
harness's own merge command. A PR merged any other way — the GitHub web UI, a
manual `gh pr merge`, a maintainer bypassing the harness — closes the issue on
GitHub but leaves the git ref on origin indefinitely. `CLAIM_TTL_SECONDS = 1800`
(`solomon_harness/claim.py:32`) and `_pr_liveness`
(`solomon_harness/claim.py:254-303`) already stop treating a closed issue's claim
as active for future claim *decisions* (acquire/reclaim), but neither one deletes
the stale ref, so it accumulates as permanent clutter on `refs/claims/*` and
misreports "claimed" to any tool that lists the refs directly (for example
`fetch_all_claims`, used by `filter_unclaimed`'s board-scan path) rather than
going through the TTL-aware `is_claim_active` gate.

## Requirements

1. `reconcile` gains a claim pass: for each issue GitHub reports CLOSED that
   still holds a claim ref in the authoritative remote snapshot, call
   `ClaimStore.release_if_version(number, observed_version)`.
2. A claim ref for a still-OPEN issue is left untouched regardless of staleness
   or liveness signal — `release_if_version()` is never called for it. TTL and
   `_pr_liveness` semantics already govern the open-issue case and are not
   duplicated or overridden here.
3. The delete uses git compare-and-swap against the version observed before the
   GitHub issue-state snapshot. A ref changed by a heartbeat, reclaim, or
   acquisition before or after that GitHub read remains untouched and is
   reported as `changed`; processing continues with later closed issues.
4. `--dry-run` reports the closed-issue numbers whose refs would be released,
   without calling `release_if_version()`, pushing a ref deletion, clearing a
   mirror, or changing an assignee. Its `ls-remote` snapshot is read-only and
   does not update local remote-tracking refs.
5. The claim pass performs no extra GitHub API round-trip. It first reads ref
   versions with one bulk `ClaimStore.fetch_versions()` call, then fetches the
   existing `issue_states` snapshot, and carries the earlier ref snapshot
   unchanged into deletion. This ordering closes the reopen/acquire interval
   between the two independent systems.
6. The claim pass runs under the same conditions as the existing passes: it is
   invoked from `_handle_reconcile_locked` only after the SurrealDB-backend
   gate and the single-driver `LoopLock` already required there — no new gate
   is introduced.
7. Live and dry-run print/stderr blocks report the claim pass's counts and any
   per-issue failures, in the same style as the existing `board_failures` and
   `would_move_board` reporting.
8. An unavailable or malformed claim-origin snapshot is explicit, performs no
   claim release, prints a claim-snapshot error, and makes `reconcile` exit
   non-zero after the other independent passes report their outcomes.

## Implementation Pointers

- `solomon_harness/claim.py:672` implements
  `fetch_claim_ref_versions(workspace_root)`. It runs one authoritative,
  read-only `git ls-remote --refs origin 'refs/claims/issue-*'`, validates the
  returned object ids and canonical `refs/claims/issue-N` names, and returns
  `{"ok", "versions", "error"}`. Origin failure and malformed output are not
  represented as an empty namespace.
- `solomon_harness/claim.py:702` implements
  `release_claim_if_version(workspace_root, issue_number, expected_version)`.
  It deletes with
  `git push --force-with-lease=<ref>:<expected_version> origin :<ref>`.
  A successful authoritative delete attempts best-effort mirror, audit, and
  assignee cleanup. A failed push performs one exact-ref `ls-remote` read and
  returns `changed`, `missing`, or `failed`; a changed ref receives no mirror
  or assignee mutation.
- `solomon_harness/claim.py:951` extends the `ClaimStore` port with
  `fetch_versions()` and `release_if_version()`. `GitClaimStore` delegates
  those methods at `solomon_harness/claim.py:1028`. The existing `fetch_all()`
  and `release()` contracts remain unchanged for all previous consumers.
- `solomon_harness/cli.py:692` implements
  `reconcile_claims(claim_store, claim_snapshot, gh_states, dry_run=False)`.
  It accepts the already-observed versions, never refetches them, filters only
  exact `CLOSED` entries, and passes each earlier version to
  `release_if_version()`. `released`, `already_absent`, `release_failures`,
  `would_release`, `snapshot_error`, and `scanned` remain separate outcomes.
- `solomon_harness/cli.py:888` wires the pass into
  `_handle_reconcile_locked`. Lines 908-912 capture the claim-ref snapshot
  before the GitHub issue snapshot; the earlier versions are passed unchanged
  at lines 917-922. Output distinguishes changed or failed per-issue releases;
  an unavailable snapshot is printed and exits non-zero after the independent
  reconciliation summaries.
- `tests/test_claim.py` contains the real bare-origin cross-snapshot regression:
  observe V1, refresh to V2 before supplying the later `CLOSED` GitHub snapshot,
  and prove V2 and its owner survive. `tests/test_reconcile.py` asserts the
  command ordering plus policy, dry-run, continuation, absent-ref, and error
  paths.

## Acceptance Criteria

```gherkin
Scenario: Happy path — a closed issue's live claim ref is released
  Given issue #173 is CLOSED on GitHub and refs/claims/issue-173 exists on origin
  When reconcile runs
  Then GitClaimStore.release_if_version(173, observed_version) is called
  And refs/claims/issue-173 is deleted from origin
  And best-effort mirror, audit, and assignee cleanup is attempted afterward

Scenario: Boundary — a still-open issue's claim is left untouched even if stale
  Given issue #200 is OPEN on GitHub and refs/claims/issue-200 exists on origin with a heartbeat older than CLAIM_TTL_SECONDS (1800s)
  When reconcile runs
  Then release_if_version() is never called for issue 200
  And refs/claims/issue-200 still exists on origin after the run

Scenario: Dry-run reports the pending release without mutating anything
  Given issue #173 is CLOSED and refs/claims/issue-173 exists on origin
  When reconcile --dry-run runs
  Then the output reports "1 claim ref(s) would be released: #173"
  And no git push deleting refs/claims/issue-173 is issued
  And GitClaimStore.release_if_version is never called

Scenario: Race path — a claim changed between ref and GitHub snapshots survives
  Given the claim snapshot observes issue #173 at V1
  And issue #173 is refreshed or acquired at V2 before the GitHub snapshot
  And the later GitHub snapshot still reports issue #173 and issue #201 CLOSED
  When reconcile completes
  Then the delete for issue #173 compares against V1, returns changed, and preserves V2
  And refs/claims/issue-201 is deleted and its best-effort cleanup is attempted
  And stderr names issue 173 and reports changed
  And reconcile still exits 0, having processed issue 201

Scenario: Snapshot failure — an unavailable claim origin fails closed
  Given GitHub issue states are available but the claim origin cannot be read
  When reconcile runs
  Then no conditional claim release is attempted
  And stderr reports the claim snapshot failure
  And reconcile exits non-zero after reporting the independent pass outcomes
```

## Verification

```bash
uv run pytest tests/test_claim.py tests/test_reconcile.py -v
uv run pytest tests/ -k reconcile -v
uv run ruff check solomon_harness/claim.py solomon_harness/cli.py tests/test_claim.py tests/test_reconcile.py
gh pr view 314 --json body --jq .body | uv run python scripts/check-adr-gate.py --body-file /dev/stdin
uv run python -m solomon_harness.cli reconcile --dry-run
```

The real bare-origin test is the concurrency proof: it snapshots V1, refreshes
the ref to V2 in the interval before supplying a later `CLOSED` GitHub snapshot,
attempts conditional deletion with V1, and asserts V2 remains. The command-path
test separately proves the ref snapshot precedes the GitHub issue snapshot. For
the live dry-run check, use a known orphaned ref for a GitHub-closed issue and
confirm the output names it; dry-run must issue no deletion push.

## Design Constraints

The pass remains behind the existing SurrealDB backend gate and repository
`LoopLock`; it adds no lock or GitHub read. ADR-0037 defines the additional
cross-worktree constraint: the `CLOSED` snapshot authorizes deletion only of
the claim version observed earlier in the same run. Git's force-with-lease CAS
is the linearization point. A heartbeat, reclaim, or acquisition in the
cross-snapshot interval or after the GitHub snapshot changes the version and
survives. Snapshot unavailability fails closed rather than consulting cached
tracking refs. Existing owner-driven `release()` callers and spec 264's
board/memory reconciliation behavior remain unchanged.

## Out of Scope

- The root cause of why a merge outside `merge_pr_and_close` skips claim
  release in the first place — that path is by design (only the harness's own
  merge command owns the release-on-merge best-effort call); this issue only
  adds the reconcile-side backstop.
- Reconciliation of reopened issues — out of scope for spec 264 for the same
  reason (a reopened issue's claim state is a live-claim-decision question,
  not a reconcile-pass question). ADR-0037 protects any ref version that changes
  after the earlier claim snapshot, including before the GitHub read.
- Replacing the git-CAS substrate or changing existing `ClaimStore.release()`
  semantics. The port gains two additive methods for standing reconciliation;
  all previous consumers retain their contracts.
- Spec 264's board-status and memory-status reconciliation behavior — shipped
  (PR #309) and unchanged by this issue.

## Traceability

- Issue: #289
- ADR: `docs/adrs/0037-conditional-claim-ref-reconciliation.md` (amends
  ADR-0027, ADR-0030, and ADR-0034)
- PR: #314
