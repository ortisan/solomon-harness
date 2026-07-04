# Tooling: scripts/scrum-master.sh

This skill governs the use of `scripts/scrum-master.sh`, the single entry point
for creating GitHub milestones and issues and for listing the backlog. The
script wraps the `gh` CLI, applies the repository's issue templates, and
degrades to a mock mode when no remote exists — so treat mock output as a dry
contract, not as created state.

## Invocation and global options

```
scripts/scrum-master.sh [global options] <subcommand> [arguments]
```

Global options, parsed before the subcommand:

- `-R, --repo <owner/repo>` — target repository. Without it, the script resolves
  the repo from `git remote origin` (both SSH and HTTPS GitHub URLs are
  recognized).
- `--dry-run` — print what would be sent to GitHub without calling the API.
- `-h, --help` — usage text.

Unknown dashed options are rejected with an error, and there is no `--title`
flag anywhere in this script: titles are positional arguments. The `--title`
footgun recorded in project memory belongs to the separate board CLI
(`python -m solomon_harness.github set-status` / `add-issue`), where passing
`--title` silently creates a duplicate project board per issue. This script
never touches the project board.

Repo resolution and mock mode: when no `-R` is given and no GitHub remote is
found, the script warns and switches to mock mode against `mock/repo`. Mock
output mirrors the real shape (including a fake two-row backlog) but creates
nothing. When not mocking, the script requires the `gh` CLI and exits with an
error if it is missing.

## Subcommands

`milestone-create "<title>" "<description>" "<due-date>"` — creates a milestone
via `gh api POST repos/<repo>/milestones`. A `YYYY-MM-DD` due date is expanded
to ISO 8601 (`T23:59:59Z`); a full ISO 8601 timestamp passes through unchanged.
Prints the new milestone number on success.

`issue-create "<title>" <feature|bug|quant|future> ["description"]` — creates an
issue with `gh issue create`, using the template matching the type under
`.github/ISSUE_TEMPLATE/`:

- `feature` -> `feature_conception.md`
- `bug` -> `bug_report.md`
- `quant` -> `quant_model_hypothesis.md`
- `future` -> `future_ideas.md`

The script parses the template's YAML frontmatter for `labels` and passes them
to `gh issue create --label`; the template body becomes the issue body, and the
optional third argument replaces the type's placeholder comment (the description
slot for feature/bug/future, the economic-rationale slot for quant). Pick the
type that matches the work: a trading model goes in as `quant`, not `feature`,
so the hypothesis fields (Sharpe target, drawdown limit, dataset) are captured.
An invalid type or a missing template file is a hard error.

`backlog-list` — runs `gh issue list` for the repo. Note the `gh` default of 30
results: a backlog past 30 open issues is silently truncated, so cross-check
with the board or `gh issue list --limit N` when counting.

`milestone-list` — lists milestones via `gh api repos/<repo>/milestones` as a
tab-separated table (title, state, due date, description). Prints
"No milestones found." when there are none.

## Failure modes

- Missing `gh` in non-mock mode: immediate error. Install and authenticate `gh`
  first.
- Template labels that do not exist in the repository: `gh issue create --label`
  fails. Create the labels once, or fix the template frontmatter.
- Duplicate milestone title: the GitHub API rejects it with a validation error;
  the script surfaces the error and exits non-zero. Run `milestone-list` first.
- The script writes a transient `err.log` in the current working directory to
  capture API stderr and removes it on both success and failure paths; run it
  from the repo root so the file never lands elsewhere.
- Mock mode looks convincing: beyond the initial warning banner, only the
  `[DRY RUN / MOCK]` prefix marks output as fake, so anything parsing the output
  must check for that prefix.

## Memory integration

Persist the same records in project memory so other agents see context. Init
once with `python agents/scrum_master/main.py db-init`, then use the
`solomon-memory` MCP tools. The ones used most: `create_milestone`, `log_issue`,
`get_open_issues`, `get_issue`, `log_handoff`, `save_session`, `save_decision`,
`get_latest_activity`. Retrieval and adjacent tools also exist:
`get_decision`, `get_session`, `save_memory`, `get_memory`, and `save_backtest`
for quant results. Log a handoff every time work routes to another specialist,
and record planning trade-offs with `save_decision`.

## Common pitfalls

- Reaching for a `--title` flag on any subcommand. It does not exist here;
  titles are positional, and the flag's real home — the board CLI — is exactly
  where it creates duplicate project boards.
- Trusting mock-mode output as real state: the fake backlog rows look like live
  issues, but nothing was created.
- Counting the backlog from `backlog-list` when more than 30 issues are open;
  the `gh` default truncates silently.
- Filing a trading-model idea as `feature`, which skips the quant template's
  hypothesis fields (Sharpe, drawdown, leakage checks).
- Creating a milestone without checking `milestone-list` first and hitting the
  duplicate-title API error.
- Creating the GitHub record but skipping the memory write, so other agents plan
  against a stale picture.
- Assuming the script manages the project board; column moves and board adds go
  through `python -m solomon_harness.github`, not through this script.

## Definition of done

- [ ] The subcommand ran against the intended repo (explicit `-R` or a verified
      `git remote origin`), not mock mode, unless a dry run was the goal.
- [ ] Issues were created with the correct type, so the matching template and
      labels applied.
- [ ] Milestones carry a title, description, and due date, and no duplicate
      title existed beforehand.
- [ ] The same milestone or issue was recorded in project memory
      (`create_milestone` / `log_issue`).
- [ ] Any routing of the new work to a specialist was logged with `log_handoff`.
