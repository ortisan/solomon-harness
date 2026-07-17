# Spec 289: force-release claim refs for GitHub-closed issues

- Issue: #289 · Status: implemented
- Date: 2026-07-17 · Author: product_owner

## Context

Raised by the 2026-07-16 four-specialist harness verification audit (qa / dba /
loop_engineer / software_architect; consolidated report in
`scratch/harness-verification-audit-2026-07-16.md`, untracked). The audit's live
sample found issue #173's claim ref still present and STALE 35 hours after its PR
merged, because the PR was not merged through the harness's own
`merge_pr_and_close`. This is the sibling gap left explicitly open by spec 264
(`docs/specs/264-reconcile-outside-release-path.md`), whose Out of Scope section
names it directly: "Claim-ref release for closed issues (#289)".

## Problem

`refs/claims/issue-N` is meant to protect an issue only while it is actively
being worked. The only place that ever deletes the ref is
`merge_pr_and_close` (`solomon_harness/github.py:412-433`), called solely by the
harness's own merge command. A PR merged any other way — the GitHub web UI, a
manual `gh pr merge`, a maintainer bypassing the harness — closes the issue on
GitHub but leaves the git ref on origin indefinitely. `CLAIM_TTL_SECONDS = 1800`
(`solomon_harness/claim.py:32`) and `_pr_liveness`
(`solomon_harness/claim.py:239-288`) already stop treating a closed issue's claim
as active for future claim *decisions* (acquire/reclaim), but neither one deletes
the stale ref, so it accumulates as permanent clutter on `refs/claims/*` and
misreports "claimed" to any tool that lists the refs directly (for example
`fetch_all_claims`, used by `filter_unclaimed`'s board-scan path) rather than
going through the TTL-aware `is_claim_active` gate.

## Requirements

1. `reconcile` gains a claim pass: for each issue GitHub reports CLOSED that
   still holds a live claim ref, call the claim store's
   `release(int(number), force=True)`.
2. A claim ref for a still-OPEN issue is left untouched regardless of staleness
   or liveness signal — `release()` is never called for it. TTL and
   `_pr_liveness` semantics already govern the open-issue case and are not
   duplicated or overridden here.
3. `release()` returning `False` for one issue (the force-with-lease push
   failed, per `solomon_harness/claim.py:608-609`) is recorded per-issue and
   does not stop the pass from processing the remaining closed issues that
   hold a ref — mirroring how `reconcile_memory`'s `board_failures` keeps a
   per-issue board-move failure from blocking sibling issues
   (`solomon_harness/cli.py:672-678`).
4. `--dry-run` reports the closed-issue numbers whose refs would be released,
   without calling `release()` and without any other git or mirror mutation.
5. The claim pass performs no extra GitHub API round-trip: it reuses the
   `issue_states` already fetched by `_fetch_reconcile_issue_states` for the
   memory pass (`solomon_harness/cli.py:842`), and reads live refs with one
   bulk `ClaimStore.fetch_all()` call rather than a per-issue fetch.
6. The claim pass runs under the same conditions as the existing passes: it is
   invoked from `_handle_reconcile_locked` only after the SurrealDB-backend
   gate and the single-driver `LoopLock` already required there — no new gate
   is introduced.
7. Live and dry-run print/stderr blocks report the claim pass's counts and any
   per-issue failures, in the same style as the existing `board_failures` and
   `would_move_board` reporting.

## Implementation Pointers

- New function `reconcile_claims(claim_store, gh_states, dry_run=False) -> dict`
  in `solomon_harness/cli.py`, placed near `reconcile_tracking_rows`
  (`cli.py:743-800`) — its closest sibling in shape: a for-loop over
  non-terminal-relevant rows, a `dry_run` branch that only appends to a
  `would_*` list, and a plain dict return with no exceptions raised across the
  call boundary.
  - Input: `gh_states` is the same `List[dict]` `_fetch_reconcile_issue_states`
    already produces for `reconcile_memory` (no second GitHub call).
  - Read the live refs once via `claim_store.fetch_all()`
    (`ClaimStore.fetch_all`, `claim.py:831`; `GitClaimStore.fetch_all`,
    `claim.py:878-879`, which delegates to `fetch_all_claims`,
    `claim.py:712-745`) — a single bulk `git fetch` + `for-each-ref` scan
    keyed by issue number, not a per-issue `get_claim_ref` fetch.
  - For each entry in `gh_states` with `state == "CLOSED"` whose issue number
    is a key in the `fetch_all()` result: if `dry_run`, append the number to
    `would_release`; otherwise call
    `claim_store.release(int(number), force=True)`
    (`ClaimStore.release`, `claim.py:823`; `GitClaimStore.release`,
    `claim.py:862-870`, which delegates to `release_claim`,
    `claim.py:559-621` — `force=True` skips the ownership/liveness branch at
    line 578 and goes straight to the `git push --force-with-lease` delete at
    line 607). On `True`, increment `released`; on `False`, append
    `{"issue": number, "ok": False}` to `release_failures` and continue the
    loop — `release_claim` never raises on a push failure
    (`claim.py:608-609` returns `False`), so no `try/except` is needed to keep
    the loop going.
  - An OPEN issue's number, even if present in the `fetch_all()` result, is
    skipped entirely — no `release()` call, no dry-run listing.
  - Return `{"released", "release_failures", "would_release", "scanned"}`,
    where `scanned` is `len(gh_states)` (mirrors `reconcile_memory`'s
    `scanned` key so the print block can follow the same pattern).
- Wire the call into `_handle_reconcile_locked`
  (`solomon_harness/cli.py:822-900`), immediately after the
  `result = reconcile_memory(...)` call at line 847 and before
  `resolved_map = _build_resolved_map(...)` at line 848:
  `claims = reconcile_claims(GitClaimStore(workspace_root), issue_states, dry_run=dry_run)`,
  constructing `GitClaimStore` (`claim.py:842-886`) from the same
  `workspace_root` the function already has in scope, and reusing the
  `issue_states` already fetched at line 842 — no new GitHub call.
- Extend the existing dry-run and live print blocks (`cli.py:854-900`) with a
  claim section that follows the same shape as the board-move block
  (`cli.py:861-866` for dry-run, `cli.py:886-892` for live): report
  `claims["would_release"]` (dry-run) or `claims["released"]` and iterate
  `claims["release_failures"]` to print a `reconcile: claim release failed for
  #<N>` line to stderr for each, mirroring the existing
  `reconcile: board move failed for #{failure['issue']}: {failure['error']}`
  line at `cli.py:888-891`.
- No change to `solomon_harness/claim.py` or `solomon_harness/github.py`:
  `release_claim`, `GitClaimStore`, and `fetch_all_claims` already provide
  every primitive this pass needs.

## Acceptance Criteria

```gherkin
Scenario: Happy path — a closed issue's live claim ref is released
  Given issue #173 is CLOSED on GitHub and refs/claims/issue-173 exists on origin
  When reconcile runs
  Then GitClaimStore.release(173, force=True) is called
  And refs/claims/issue-173 is deleted from origin
  And the claim mirror row for issue 173 is cleared

Scenario: Boundary — a still-open issue's claim is left untouched even if stale
  Given issue #200 is OPEN on GitHub and refs/claims/issue-200 exists on origin with a heartbeat older than CLAIM_TTL_SECONDS (1800s)
  When reconcile runs
  Then release() is never called for issue 200
  And refs/claims/issue-200 still exists on origin after the run

Scenario: Dry-run reports the pending release without mutating anything
  Given issue #173 is CLOSED and refs/claims/issue-173 exists on origin
  When reconcile --dry-run runs
  Then the output reports "1 claim ref(s) would be released: #173"
  And no git push deleting refs/claims/issue-173 is issued
  And GitClaimStore.release is never called

Scenario: Failure path — a release failure is recorded and the pass continues
  Given issue #173 and issue #201 are both CLOSED with a live claim ref each, and release(173, force=True) returns False (the force-with-lease push fails) while release(201, force=True) returns True
  When reconcile completes
  Then the run's release_failures list contains {"issue": 173, "ok": False}
  And refs/claims/issue-201 is deleted and its mirror cleared
  And stderr names issue 173 and reports the failure
  And reconcile still exits 0, having processed issue 201
```

## Verification

```bash
uv run pytest tests/test_reconcile.py tests/test_claim.py -k 'claim' -v
uv run pytest tests/ -k reconcile -v
uv run python -m solomon_harness.cli reconcile --dry-run
```

For the live dry-run check, run it on a repo with a known orphaned claim ref
(a `refs/claims/issue-N` on origin for an issue GitHub already reports CLOSED)
and confirm the output names that issue under the new "claim ref(s) would be
released" line. A subsequent non-dry-run confirms the ref is gone via
`git ls-remote origin 'refs/claims/*'`.

## Design Constraints

The claim pass is gated by the same conditions already enforced in
`_handle_reconcile_locked`: the SurrealDB-only backend check
(`solomon_harness/cli.py:833-840`) and the single-driver `LoopLock` acquired by
`handle_reconcile` (`cli.py:803-819`) — this issue adds no new
backend-availability decision or lock. `force=True` intentionally bypasses the
ownership/liveness branch in `release_claim`: a GitHub-CLOSED issue is a
definitive signal (unlike a heartbeat timeout, which can be a transient
session gap), so the pass does not re-derive or duplicate the TTL/liveness
logic that already governs open-issue claim *decisions*. This spec does not
re-open or re-litigate spec 264's board/memory reconciliation behavior
(`reconcile_memory`, `reconcile_tracking_rows`, `normalize_memory_statuses`),
which is shipped and unchanged.

## Out of Scope

- The root cause of why a merge outside `merge_pr_and_close` skips claim
  release in the first place — that path is by design (only the harness's own
  merge command owns the release-on-merge best-effort call); this issue only
  adds the reconcile-side backstop.
- Reconciliation of reopened issues — out of scope for spec 264 for the same
  reason (a reopened issue's claim state is a live-claim-decision question,
  not a reconcile-pass question) and not reintroduced here.
- A broader claim-store or `ClaimStore` protocol redesign — the existing
  `release()` and `fetch_all()` primitives are sufficient; no new port method
  is added.
- Spec 264's board-status and memory-status reconciliation behavior — shipped
  (PR #309) and unchanged by this issue.

## Traceability

- Issue: #289
- ADR: `docs/adrs/0027-layer-per-issue-claims-on-safety-floor.md` (claim/lease
  store) — extended, no new ADR needed
- PR: none yet
