# ADR-0034: Closed-issue board projection reconciliation

- Status: accepted
- Date: 2026-07-16
- Amends: ADR-0020 (scope of the human `Done` gate), ADR-0033 (operational shape of `reconcile`)
- Deciders: software_architect, loop_engineer, software_engineer
- Issue: #264

## Context and problem statement

GitHub is the authoritative source for whether an issue is open or closed, while
the Project board and project memory are projections of that lifecycle state.
Those projections can diverge after a merge or manual close. At the audit that
created issue #264, eight closed issues were still outside `Done`; issue #280 was
already terminal in memory but remained in `Code Review` on the board.

The existing `reconcile` command repairs terminal memory rows but only runs from
the release path. PR #309 initially widened it to write `Done` for every closed
issue on every `SessionStart`, in a daemon thread abandoned after a five-second
join. That design conflicts with three accepted constraints: board mutation must
be single-driver (ADR-0010), idempotent reconciliation must not rewrite converged
state (ADR-0006/ADR-0033), and merge, release, and the lifecycle decision that
originates `Done` are human-gated (ADR-0020 and the autonomy policy).

The architectural question is whether a standing process may repair a stale
board projection after GitHub already records the terminal decision, and where
that work may run without weakening the human gate.

## Decision drivers

- Preserve human authority over the terminal lifecycle decision: automation must
  not merge, close, release, or infer terminality from a non-terminal signal.
- Converge the board and memory after an authoritative GitHub closure, including
  cards absent from the canonical board.
- Make a converged run a read-only no-op; the number of writes must be proportional
  to detected drift, not to repository history.
- Serialize every mutable pass across linked worktrees and leave no background
  worker after the command returns or times out.
- Keep `SessionStart` responsive and read-oriented.
- Reuse the existing canonical-board `set_issue_status` mutation primitive and
  preserve the release-path invocation.

## Considered options

- **A. Reconcile from `SessionStart` in a daemon thread.** Join for a short budget
  and let unfinished work continue in the background.
- **B. Add a locked standing stage that repairs only a closed issue's stale
  projection.** Compare the canonical card status before writing and give every
  external read an explicit deadline.
- **C. Detect drift automatically but require a new interactive confirmation for
  each board repair.** Keep all literal `Done` writes behind a prompt.
- **D. Write `Done` for every issue returned as closed.** Rely on the Projects API
  to absorb redundant edits.

## Decision outcome

Chosen: **B — a locked standing stage with a closed-only projection repair**.

The human gate protects the authoritative terminal decision, not the mechanical
repair of a derived view after that decision already exists. A standing
reconciliation run may write the canonical board card to `Done` only when the
same validated GitHub snapshot reports the issue `CLOSED`. It may not close or
reopen an issue, merge a pull request, create a release, move an issue that the
snapshot reports `OPEN`, or derive terminality from memory or board state.
`/solomon-review` remains the only workflow that can originate the normal
merge-to-`Done` transition, after explicit human confirmation (ADR-0020).

The exception is intentionally narrow:

1. The bulk issue read validates issue numbers and allow-lists GitHub states.
   It also reads `projectItems` and selects the item whose project title matches
   the repository's canonical board title. Missing, malformed, or ambiguous
   matches count as drift; only an unambiguous `Done` match suppresses a write.
2. `reconcile_memory` calls the existing
   `set_issue_status(issue_number, "Done")` primitive only for a `CLOSED` issue
   whose canonical projection is not already `Done`. The primitive retains its
   established find-or-add behavior and never creates a missing board.
3. Memory repair and board repair remain independent outcomes. A failed board
   write is returned per issue with `ok: False`; a memory write that already
   succeeded is not rolled back or hidden.
4. `handle_reconcile` acquires the git-common-dir `LoopLock` before opening the
   database or reading GitHub and releases it in `finally`. The lock is reentrant
   for a release or `dev reconcile` process carrying the same session id. A live
   foreign holder causes a fail-fast refusal.
5. `/solomon-reconcile` is a schedulable `dev` stage, registered in
   `LOCKED_STAGES` and allowed at L2/L3 as this explicit projection-repair
   exception. L1 remains report-only. `SessionStart` performs no reconciliation
   network call and starts no mutable thread.
6. Every direct bulk `gh` subprocess has an explicit timeout. A timeout fails the
   synchronous command; no worker is detached and no partial sweep continues
   after the lock is released.
7. The existing release command continues invoking the same `reconcile` CLI
   command. This standing stage is additive, not a replacement.

A is rejected because Python cannot cancel a running thread: returning after
`join(timeout)` releases control without stopping the database/GitHub writes, and
a daemon may race another driver or be killed mid-sweep. C preserves the literal
wording of the old gate but does not meet the standing-convergence requirement;
it also asks a human to approve a projection of a closure the human already
performed. D is rejected because it turns a no-op into O(number of closed issues)
writes and repeated multi-process `gh` traffic.

### Consequences

- Positive: closed issues converge outside release cadence; a second converged
  run performs zero board writes; SessionStart has no added network latency; all
  mutable paths share one lock; a failed or timed-out command has no surviving
  worker; release behavior remains additive and unchanged.
- Negative: the autonomy documentation must distinguish an authoritative
  terminal decision from repair of its derived projection. The stage can add a
  previously absent closed issue to the canonical board through the existing
  primitive. GitHub issue state and Project status do not offer a cross-resource
  transaction, so the repair is based on one validated snapshot; a later manual
  reopen is a new authoritative event and must be handled by the normal lifecycle
  rather than hidden inside this terminal backstop.
- Follow-ups: none required for issue #264. Reconciliation of reopened issues or
  claim refs remains outside this slice; claim-ref release is tracked by #289.

## More information

- Implements issue #264 and PR #309.
- Builds on ADR-0006's GitHub-source-of-truth and idempotent terminal backstop,
  ADR-0010's single-driver lock, ADR-0020's interactive merge ownership, and
  ADR-0033's status write-through and reconciliation orchestration.
- Implementation seams: `handle_reconcile`, `_fetch_gh_issue_states`,
  `_canonical_board_status`, and `reconcile_memory` in
  `solomon_harness/cli.py`; `STAGES`/`LOCKED_STAGES` in
  `solomon_harness/workflows.py`; and `AUTOMATION_ALLOWED_STAGES` in
  `solomon_harness/loop_policy.py`.
- This decision is also recorded in project memory via `save_decision`.
