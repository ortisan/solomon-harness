# Spec 264: run cli reconcile outside the release path and extend it to Done

- Issue: #264 · Status: ready
- Date: 2026-07-16 · Author: product_owner

## Context

Raised by the 2026-07-14 ecosystem audit and re-confirmed on 2026-07-16.
`cli reconcile` is a first-class command, but its only workflow call site was the
release path. A live snapshot found 20 of 47 open issues off-board and eight
closed issues outside `Done`; issue #280 was already terminal in memory while its
card remained in `Code Review`.

## Problem

Release cadence can be weeks apart, so board/memory drift remains visible for the
entire interval. The terminal backstop repaired memory but not the canonical
Project card. The first PR implementation then over-corrected: every closed issue
was rewritten on every `SessionStart`, in a daemon thread that could outlive its
timeout and bypass the single-driver lock.

## Requirements

1. Reconciliation has a standing, schedulable invocation independent of release:
   `/solomon-reconcile` / `solomon-harness dev reconcile`.
2. `SessionStart` starts no reconciliation worker or board mutation. The standing
   no-op bulk-reads state and performs zero board writes when all closed cards are
   already `Done`.
3. For each GitHub-closed issue, reconcile compares the canonical repository
   board status and calls the existing bare
   `set_issue_status(issue_number, "Done")` primitive only when the card is absent
   or not already `Done`.
4. The command acquires the shared git-common-dir `LoopLock` before database or
   GitHub access. A second live driver is refused. Direct bulk subprocesses have
   explicit deadlines and no mutable worker survives command return.
5. The existing release-path invocation remains additive and behavior-compatible.
6. Memory and board outcomes are independent. If memory repair succeeds and the
   board write fails, that issue is retained in `board_failures` with `ok: False`,
   the memory repair remains recorded, and stderr names the issue and error.
7. Automation never originates terminal authority: it does not merge, close,
   release, or move an issue whose validated GitHub snapshot is `OPEN`. The
   closed-only projection exception is governed by ADR-0034.

## Implementation Pointers

- `solomon_harness.cli.handle_reconcile` — public lock boundary. It acquires
  `LoopLock(stage="reconcile")` and delegates to `_handle_reconcile_locked`, so
  direct CLI, standing-stage, and release callers share one mutation guard.
- `solomon_harness.cli._fetch_gh_issue_states`,
  `_fetch_reconcile_issue_states`, and `_canonical_board_statuses` — one bounded
  bulk read validates GitHub issue states; a second exact canonical-board
  snapshot is joined by issue number. Do not use `issue.projectItems` for the
  board decision: live issue #6 includes a deleted same-title project's stale
  item alongside the canonical card.
- `solomon_harness.claim.fetch_board_items` — reuses the established
  owner/title/oldest-project lookup and requests `--limit 1000`, so old cards are
  not hidden by `gh project item-list` pagination.
- `solomon_harness.cli.reconcile_memory` — memory repair stays gated by an
  existing non-terminal row; board repair is separately gated by `CLOSED` plus
  `board_status != "Done"`. Dry-run uses the same predicate.
- `solomon_harness.github.set_issue_status` — unchanged board mutation primitive.
  Use its bare form only; never pass `--title`. It resolves the single canonical
  board and refuses to create a missing board.
- `solomon_harness.workflows.STAGES` / `LOCKED_STAGES` and
  `solomon_harness.loop_policy.AUTOMATION_ALLOWED_STAGES` — register the standing
  stage, require the single-driver lock, allow it at L2/L3, and keep L1
  report-only.
- `.claude/commands/solomon-reconcile.md` and its Gemini mirror — execute the CLI
  command only and explicitly forbid merge, close, release, or an open-issue
  terminal move.

## Acceptance Criteria

```gherkin
Scenario: A standing reconcile closes both projections
  Given a GitHub-closed issue whose canonical card is in "Code Review" and whose memory status is "in_progress"
  When the locked standing reconcile runs
  Then the memory status becomes terminal
  And the existing board primitive moves the canonical card to "Done"

Scenario: A converged repository is a write-free no-op
  Given every GitHub-closed issue has a canonical card already in "Done"
  When reconcile runs again
  Then no board-status write is attempted
  And SessionStart has no reconciliation call or background worker

Scenario: A concurrent driver is refused
  Given another live session holds the repository loop lock
  When reconcile starts
  Then it exits non-zero before opening memory or calling GitHub

Scenario: The release invocation remains additive
  Given the existing release path invokes cli reconcile
  When release runs
  Then the same memory, tracking, normalization, and board summaries are produced
  And the standing stage has not replaced the release call

Scenario: A partial board failure remains visible
  Given memory repair succeeds for a closed issue and its board write fails
  When reconcile completes
  Then memory remains terminal
  And board_failures contains that issue with ok: False
  And stderr reports the issue-specific failure

Scenario: An outbound read reaches its deadline
  Given the bulk gh issue read does not return within GH_TIMEOUT_SECONDS
  When reconcile runs
  Then the synchronous command fails and releases its lock
  And no daemon thread or detached mutable process continues the sweep
```

## Verification

```bash
uv run pytest tests/test_reconcile.py tests/test_claim.py tests/test_workflows.py tests/test_loop_policy.py tests/test_command_gates.py -k 'reconcile or Reconcile or fetch_board_items' -v
uv run pytest tests/ -k reconcile -v
uv run python -m solomon_harness.cli reconcile --dry-run
gh issue list --state closed --limit 1000 --json number,state
gh project item-list 5 --owner ortisan --limit 1000 --format json
```

For the live check, cross-reference the last two commands and expect no closed
issue whose exact board-#5 status differs from `Done` after a successful non-dry
run. The second dry-run must report zero board moves.

## Design Constraints

The standing path is synchronous, single-driver, and separately schedulable; it
does not run during SessionStart. A converged board is write-free. Every external
subprocess has a deadline. Board mutation reuses the existing canonical-board
primitive. The closed-only exception and human-gate boundary are defined by
ADR-0034.

## Out of Scope

The root causes that omit cards or miss normal status write-through (tracked
separately, including #173). Claim-ref release for closed issues (#289).
Reconciliation of reopened issues. A broader board-hygiene redesign.

## Traceability

- Issue: #264
- ADR: `docs/adrs/0034-closed-issue-board-projection-reconciliation.md`
- PR: #309
