# PLAN.md: chore(memory): mark synthetic RAID/follow-up rows terminal when their parent resolves

Problem statement: Mark synthetic RAID/follow-up rows terminal in the project memory when their parent issue or PR resolves, resolving issue #127.

## Proposed changes and boundaries
- Extend the existing `cli reconcile` sweep in `solomon_harness/cli.py` (specifically `reconcile_memory`).
- Retrieve all open issues in the database using `db.get_open_issues()`.
- Filter for synthetic tracking rows where `is_github_issue(row["github_id"])` is False.
- For each open synthetic row, parse its parent GitHub issue/PR number:
  1. Id-first rule: Extract a leading integer using pattern `^(\d+)-` from `github_id`.
  2. Title fallback rule: Extract `#(\d+)` or `PR #(\d+)` from `title`.
  3. If no parent number can be extracted, log a warning and skip the row.
- For recovered parent numbers, look up their status:
  - First, check in the already fetched `gh_states` lookup.
  - Fallback: If not present in the local lookup, fetch the single state directly using `gh issue view <parent>` via the helper `_fetch_gh_issue_state` to determine if it is `CLOSED`.
  - If the parent status is `CLOSED`, set the synthetic row status to `closed` in the database, preserving its original title, type, and milestone.
  - If the parent status is `OPEN`, leave the row open.
  - If the parent is not found on GitHub, log a warning and leave the row open.

## Target files
- `solomon_harness/cli.py`
- `tests/test_reconcile.py`

## Edge cases
- Parent recovered from ID (e.g., `68-R-01` -> 68).
- Parent recovered from title (e.g., `risk-44-01` with title `(#68)` -> 68).
- Parent number is already closed/merged on first run (backfill).
- Parent number is still open (stays open).
- Row with no recoverable parent (warning logged, left untouched).
- Parent number not found on GitHub (warning logged, left untouched).
- Real GitHub issues are never modified by this path.
- Database records are never deleted.

## TDD breakdown
1. **Red**: Write a test in `tests/test_reconcile.py` showing that synthetic rows with a closed parent (extracted from ID or title) are reconciled to `closed`.
   **Green**: Update `reconcile_memory` to fetch open issues, filter synthetic rows, extract parent number from ID/title, check its state in `gh_states`, and update its state.
   *Commit: test: add test for closed parent recovery and implement basic matching*
2. **Red**: Write tests for boundaries: parent is open, parent is not found, and row has no recoverable parent (skip-and-log).
   **Green**: Update `reconcile_memory` to handle open parent, missing parent (fallback to single issue fetch), not-found parent (warning log), and unrecoverable parent (warning log).
   *Commit: test: add tests for open/missing/unrecoverable parents and implement safety gates*
3. **Red**: Write a test ensuring that the close path does not delete any records, does not touch real GitHub issues, and behaves identically in a dry run (reporters only).
   **Green**: Ensure `reconcile_memory` preserves all rows, ignores real GitHub issues, and behaves correctly in `dry_run` mode (adds synthetic rows to `would_repair` list).
   *Commit: test: add tests for dry-run and non-deletion guarantees*

## STRIDE notes
- **Spoofing**: We run as the authenticated `gh` user, ensuring we check the actual repository state.
- **Information Disclosure**: Warning logs avoid logging database client connection strings or database internals.
- **Denial of Service**: The single issue state fallback has a timeout, so hanging `gh` calls do not block the reconciliation process indefinitely.

## Verification criteria
- Run `PYTHONPATH=. uv run pytest tests/test_reconcile.py` and verify all tests pass.
