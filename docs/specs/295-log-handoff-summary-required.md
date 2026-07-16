# Spec 295: every log_handoff call site passes a non-empty summary

- Issue: #295 · Status: ready
- Date: 2026-07-16 · Author: product_owner

## Context

Raised by the 2026-07-16 four-specialist harness verification audit (qa / dba / loop_engineer / software_architect; consolidated report in `scratch/harness-verification-audit-2026-07-16.md`). `log_handoff`'s `summary` parameter was added as an additive mitigation for handoff contract files disappearing with worktree teardown, but the audit found no command file actually passes it.

## Problem

`contract_path` points into `.solomon/handoffs/` inside per-issue worktrees, which are deleted on merge. When a later session reads `get_latest_activity` to resume, the handoff's `contract_path` no longer resolves, and because no caller passes `summary`, the row's `summary` field is also empty — the documented fallback is dead in practice, and a resume lands with no usable context for that stage transition.

## Requirements

1. Every command file under `.claude/commands/*.md` that calls `log_handoff` passes a non-empty `summary` argument: a 2-5 line "what this stage did" synopsis, matching the text already written into the contract file at `contract_path`.
2. `docs/solomon-workflow.md`'s Handoff contracts section documents `summary` as a required argument on every `log_handoff` call, not an optional afterthought.
3. The `.gemini` command mirrors carry the same `summary=` argument as their `.claude` sources.
4. A regression test proves that once a handoff's `contract_path` file no longer exists, `get_latest_activity` still returns a non-empty `summary` for that handoff.
5. The existing default-empty behavior of the `summary` parameter itself is unchanged (backward-compatible for any caller not yet covered by this fix).

## Implementation Pointers

- `solomon_harness/tools/database_client.py:2774-2818` (`log_handoff`) — `summary: str = ""` is already an accepted, additive parameter per its own docstring (`:2781-2792`: "so a resume survives worktree teardown even when the contract file... is gone"). No signature change is needed; the gap is entirely at the callers.
- `docs/solomon-workflow.md:351-373` ("Handoff contracts") — current: documents the 5-argument call `log_handoff(sender, recipient, contract_type, contract_path, status)` with no mention of `summary`. Expected: state that `summary` is a required, non-empty sixth argument on every call.
- `.claude/commands/solomon-start.md:151` — current: `mcp__solomon-memory__log_handoff(sender="software_engineer", recipient="qa", contract_type="pull_request", contract_path=".solomon/handoffs/issue-$ARGUMENTS-start-to-review.md", status="open")` with no `summary=`. Expected: add `summary="<2-5 line synopsis of what start produced>"`.
- `.claude/commands/solomon-review.md:96` — same defect (`sender="qa", recipient="sre", ...`); same fix.
- `.claude/commands/solomon-release.md:59` — same defect (`sender="sre", recipient="done", contract_type="release", ..., status="done"`); same fix.
- `.claude/commands/solomon-bug.md:69` — same defect (`sender="qa", recipient="software_engineer", contract_type="bug_report", ..., status="open"`); same fix.
- `.claude/commands/solomon-idea.md:60` — same defect (`sender="product_owner", ...`); same fix.
- `.claude/commands/solomon-issue.md:112` — same defect (product_owner -> scrum_master contract); same fix.
- `.claude/commands/solomon-refine.md:119` — a seventh concrete call site not in the audit's named sample: `mcp__solomon-memory__log_handoff` sender `product_owner` recipient `software_engineer`, `contract_type` `prd`, `status` `pending`, described in prose with no `summary`. Same fix, and it must be swept in by the grep gate even though it was not individually named.
- The `.gemini/commands/*.toml` mirrors of every file above — regenerate via `uv run python scripts/generate-integrations.py` after the `.claude` sources are fixed, so both hosts carry the same `summary=` argument.
- `solomon_harness/curator.py:303` — the one existing caller that already passes `summary`; use its string shape (a short, past-tense sentence) as the model for every fixed call site; no code change needed here.
- `tests/test_database_client_resilience.py:239` (`test_handoff_then_session_still_surfaces_contract_path`) — the nearest existing worktree-teardown-shaped test; add a sibling test (or extend this one) asserting the handoff's `summary` field is non-empty after the `contract_path` file is deleted from disk, and that `get_latest_activity` surfaces it.
- `tests/test_typed_states.py:127` (`test_log_handoff_summary_defaults_empty`) — documents today's default-empty behavior for an omitted argument; leave it in place as the default-parameter contract test and add the new test above as a distinct assertion about the fixed call sites, not a replacement.

## Acceptance Criteria

```gherkin
Scenario: A command file passes a non-empty summary on handoff
  Given software_engineer completes the start-to-review stage for issue #214
  When it calls mcp__solomon-memory__log_handoff(sender="software_engineer", recipient="qa", ...)
  Then the call includes summary="<2-5 line synopsis of what this stage did>"
  And the summary is not an empty string

Scenario: Every command file that calls log_handoff is covered, not a sample
  Given the command files under .claude/commands/*.md matched by `grep -l log_handoff .claude/commands/*.md`
  When `grep -L "summary=" $(grep -l log_handoff .claude/commands/*.md)` runs
  Then it returns no file names (zero call sites missing summary=)

Scenario: Boundary — the contract file is already gone
  Given a handoff was logged with summary="qa approved PR #214, merged to main" and contract_path pointing at a worktree-scoped file
  And the worktree (and its contract file) has since been deleted
  When get_latest_activity() is called
  Then the returned handoff still carries summary="qa approved PR #214, merged to main"
  And no error is raised for the missing contract_path

Scenario: Failure path — a caller omits summary
  Given a new command file adds a log_handoff call without summary=
  When the CI grep-based check from the second scenario runs
  Then it fails and names the offending file, blocking merge before the gap reaches main
```

## Verification

```bash
uv run pytest tests/ -k handoff -v
uv run python scripts/validate-workflows.py
grep -L "summary=" $(grep -l log_handoff .claude/commands/*.md)   # expect no output
```

## Design Constraints

Additive-only change to `log_handoff` (already additive per its own docstring); no database migration. Command-file edits touch only the `log_handoff` call line, not surrounding step numbering. `.gemini` mirrors must stay byte-identical to `.claude` sources per the existing drift-check convention. Issue-derived text still reaches the summary only through the Write tool at contract-authoring time — this fix does not change that discipline.

## Out of Scope

Changing `log_handoff`'s signature or the `handoffs.summary` database column — the field already exists and works; this is a call-site fix. `solomon_harness/curator.py`'s existing summary logic — already correct, untouched. A broader handoff-contract redesign — covered by ADR-0016/ADR-0018 already; this issue only closes the enforcement gap.

## Traceability

- Issue: #295
- ADR: ADR-0016 (summary field origin), ADR-0018
- PR: #<M once opened>
