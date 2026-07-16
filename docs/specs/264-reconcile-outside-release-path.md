# Spec 264: run cli reconcile outside the release path and extend it to Done

- Issue: #264 · Status: ready
- Date: 2026-07-16 · Author: product_owner

## Context

Raised by the 2026-07-14 ecosystem audit (process lens); re-confirmed live by the 2026-07-16 verification audit. `cli reconcile` exists as a first-class CLI subcommand and already handles the memory-status half of GitHub/board drift, but is only ever invoked from inside the release stage's own gap-filing steps.

## Problem

Because reconcile only runs at release cadence — which can be weeks apart — board and memory drift accumulates for the entire span between releases. A live snapshot showed 20 of 47 open issues (43%) off the board entirely and 8 closed issues stranded in non-Done columns. Reconcile also only ever wrote the memory-status half of the fix; it never moved a GitHub-closed issue's board card to Done, so even a timely run left the board-column half of the drift untouched.

## Requirements

1. `cli reconcile` (or an equivalent best-effort call) runs on a standing cadence independent of the release path — either folded into the existing SessionStart digest or registered as a new standing loop stage.
2. The standing invocation is a fast no-op when there is nothing to reconcile, with no perceptible delay to whichever surface triggers it.
3. Reconcile is extended to move a GitHub-closed issue's board card to `Done` when it is not already there, reusing the existing board-status-move primitive rather than a new API call path.
4. The existing release-path invocation of reconcile is unchanged (this is additive, not a replacement).
5. A partial failure (memory status fixed, board move fails, or vice versa) is reported distinctly per issue, never silently dropped.

## Implementation Pointers

- `solomon_harness/cli.py:707` (`handle_reconcile(workspace_root, dry_run)`) — current: the only caller of this function across the whole `/solomon-*` command surface is the release stage's own gap-filing/close-out steps (per `docs/solomon-workflow.md`'s Deliver/release description); no `SessionStart` hook, cron, or standing loop stage calls it independently. Expected: add a second, independent standing call site (see the two wiring options below).
- `solomon_harness/cli.py:555-706` (`reconcile_memory`, `normalize_memory_statuses`, `reconcile_tracking_rows` — the three passes `handle_reconcile` composes) — current: each sets a memory row's status to a terminal value (`closed`/`done`) or normalizes it; none of the three touches the GitHub Project board column. Expected: after `reconcile_memory` identifies a GitHub-closed issue, call `solomon_harness.github.set_issue_status(issue_number, "Done")` for its board card, reusing the exact primitive `merge_pr_and_close` already uses for the same transition, rather than inventing a new board-move helper.
- `solomon_harness/github.py` (`set_issue_status`, and the partial-failure reporting shape inside `merge_pr_and_close`: `{"ok": False, "error": ..., "merged": True, ...}`) — the reporting pattern the new board-column reconcile path should mirror when the memory write succeeds but the board write fails, so a caller can tell the two outcomes apart.
- `solomon_harness/cli.py:97` (`handle_run`, the SessionStart entry point that already calls `gather_digest`) — the first wiring option: fold a best-effort `handle_reconcile(workspace_root, dry_run=False)` call in here, guarded so any failure degrades silently and never blocks or slows SessionStart beyond a fast-no-op budget.
- `solomon_harness/workflows.py:16-27` (`LOCKED_STAGES`, which already lists `scan-arch`/`scan-dedup` alongside `workflow`, `loop`, `start`, `review`, `release`) plus `.claude/commands/solomon-scan-arch.md` — the second wiring option: register a new standing stage here with its own command file, mirroring the `scan-arch`/`scan-dedup` cadence pattern already documented for `loop_engineer`, if that fits the existing infrastructure better than folding into SessionStart.
- Board-target safety: the mutation must use the bare `set-status` form that targets the single repo board (#5); never pass `--title` (the prior footgun that silently created duplicate boards per issue).

## Acceptance Criteria

```gherkin
Scenario: A standing reconcile closes both halves of the drift
  Given a GitHub-closed issue whose board card is still in "Code Review" and whose memory status is still "in_progress"
  When the new standing reconcile runs
  Then the board card moves to "Done"
  And the memory status becomes terminal in the same run

Scenario: Boundary — a fast no-op when there is nothing to reconcile
  Given the standing reconcile runs (via SessionStart or a new standing loop stage) and there is nothing to reconcile
  When it completes
  Then it is a fast no-op with no perceptible session-start delay

Scenario: Boundary — the release-path invocation is unchanged
  Given the existing release-path reconcile call
  When a release runs
  Then its behavior is unchanged (no regression)
  And reconcile still runs there too, additively

Scenario: Failure path — a partial write is reported distinctly, not dropped
  Given the standing reconcile's board-column write fails for one issue (e.g., a missing Status field or option) while its memory-status write already succeeded
  When the run completes
  Then that issue is reported as ok: False with the memory write already recorded as done
  And it is never silently dropped from the run's output
```

## Verification

```bash
uv run python -m solomon_harness.cli reconcile --dry-run   # before and after, on a repo with known drift
uv run pytest tests/test_cli.py tests/test_memory.py -k reconcile -v
gh project item-list 5 --owner ortisan --limit 200   # cross-referenced against gh issue list --state closed; expect 0 stranded off Done after a run
```

## Design Constraints

The standing invocation must be best-effort and never block or perceptibly slow SessionStart, mirroring the existing digest timeout discipline in `digest.py`'s `_run_with_timeout`. The release-path invocation is untouched (additive, not replaced). Board-column writes reuse the existing `set_issue_status` primitive (bare form, board #5) rather than a new GitHub API call path.

## Out of Scope

The underlying causes of why cards go off-board or fail to write canonical statuses in the first place (tracked separately, e.g. #173). Claim-ref release for GitHub-closed issues (#289). A full board-hygiene redesign beyond widening reconcile's reach and cadence.

## Traceability

- Issue: #264
- ADR: none yet
- PR: #<M once opened>
