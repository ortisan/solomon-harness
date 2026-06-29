---
description: Cut a release for a completed milestone (or an on-demand patch batch): run the library readiness gate, then open the chore/release prep PR for the human to merge (sre).
argument-hint: [milestone]
allowed-tools: Bash(gh:*), Bash(git:*), Bash(uv run:*), Bash(scripts/wiki-sync.sh:*), Task, Read, Write, Edit, mcp__solomon-memory__log_issue, mcp__solomon-memory__save_decision, mcp__solomon-memory__save_release, mcp__solomon-memory__log_handoff, mcp__solomon-memory__save_session, mcp__solomon-memory__get_latest_activity
---

Read `docs/solomon-workflow.md` first and follow the Deliver/release stage exactly. Drive this as the **sre** specialist; delegate the readiness gate and release mechanics to the `.claude/agents/sre` subagent via the Task tool, grounded in its `release_engineering_and_progressive_delivery` skill (the library readiness gate and the reversibility kernel). This is the `QA` → `Done` transition.

This stage cuts a release for a **milestone**, never a single PR. A tag is cut when a GitHub milestone reaches 0 open issues with CI green on main; the routine per-PR squash-merge that closes each issue and burns down the milestone now happens in `/solomon-review` close-out, not here. The release object is the milestone: an **epic** milestone is titled with its SemVer minor (`v0.4.0`) and closing it cuts that MINOR; a **theme/hardening** milestone is titled by theme and closing it cuts a PATCH whose version is computed at cut time.

Release target: **$ARGUMENTS** — a milestone title or number. Leave it empty to cut an on-demand PATCH for an accumulated batch (the escape valve) without waiting for a milestone to fully close. This is never a PR number.

## 1. Gather state
- Read the latest incoming handoff with `mcp__solomon-memory__get_latest_activity` and open its `contract_path`. The review → release contracts written as each milestone issue closed are supplementary context; open the artifacts they point to (PLAN.md, the diffs, the ADRs, the PRs) only when you actually need them, instead of re-deriving prior context.
- Resolve the release target with `uv run solomon-harness release plan $ARGUMENTS` (read-only, headless-safe). It detects the target — the milestone at 0 open issues, or the on-demand batch — computes the SemVer bump from Conventional Commits in `git log <last-tag>..main --first-parent` (highest wins), and prints the planned version and the rendered CHANGELOG section. Pre-1.0: a window containing any `feat` or a BREAKING CHANGE bumps MINOR; otherwise `fix`/`perf`/`refactor`/`revert` bumps PATCH; a window of only chore/docs/ci/test/style/build is non-releasable. If `release plan` reports the milestone still has open issues or the window is non-releasable, stop and report — there is nothing to tag.
- Confirm CI is green on main: `gh run list --branch main --limit 1 --json conclusion,status,headSha`. A red or in-progress main halts the release.
- Confirm the board exists with `uv run python -m solomon_harness.github ensure-board`.

## 2. Library readiness gate
This is a tag-release library (distributed as a git tag plus a GitHub Release of the source tree) with no running service, so the SLO/canary/burn-rate/on-call Production Readiness Review does not apply. Have the sre subagent run the **library readiness gate** and produce one verdict (GO / GO-WITH-CONDITIONS / NO-GO). Verify on main now:
- Tests and lint are green: `uv run pytest` and `uv run ruff check .`.
- The package imports: `uv run python -c "import solomon_harness"`.
- The console script runs: `uv run solomon-harness --help`.
- `uv run solomon-harness release check` passes. This is the fail-closed invariant: the planned tag == the `pyproject.toml` version == the top `CHANGELOG.md` heading (Keep a Changelog, dated today), the tag does not already exist, and tests + ruff are green. The three-way equality is only fully satisfiable once `release prep` (Step 4) writes the bump and the CHANGELOG section, so it goes green on the `chore/release-vX.Y.Z` branch and CI re-enforces it on the prep PR — it is what gates the human merge.

Carry forward only the **reversibility kernel** from progressive delivery, and confirm each holds:
- Tags are immutable and never moved; a bad release is superseded by the next PATCH — a revert PR that ships forward — never by re-tagging.
- Rollback is that revert PR auto-shipping the next patch; there is no separate rollback path to staff.
- Memory-store schema changes (SurrealDB/SQLite) are backward-compatible expand/contract migrations.

File each gap with `mcp__solomon-memory__log_issue` (and `gh issue create` with `type:chore` + `priority:*` when it needs tracking on the board). A **NO-GO** or any blocking gap halts the release — report and stop. A **GO-WITH-CONDITIONS** records each condition, owner, and due date.

## 3. ADR re-check
Re-evaluate architectural significance for anything that emerged across the milestone, using `docs/adr/README.md` and the software_architect checklist. If significant, delegate the ADR to the software_architect subagent (`docs/adr/NNNN-<slug>.md`), record it with `save_decision`, and link it in the prep PR. If not, note that no ADR is needed.

## 4. Confirm, then open the release prep PR
Summarize the planned version, the rendered CHANGELOG section, and the readiness verdict, then **ask the user to confirm before opening the prep PR**. Never push to a protected branch directly, and never hand-edit `pyproject.version` or add a CHANGELOG heading by hand — `release prep` writes them, and a CI check rejects any non-release PR that touches them. Only after explicit approval:
- `uv run solomon-harness release prep` — creates the ephemeral `chore/release-vX.Y.Z` branch, writes the computed `pyproject.toml` bump and the `CHANGELOG.md` section, commits `chore(release): vX.Y.Z`, opens the PR, then stops. It opens a PR only; it never merges.
- The **human merges that prep PR** — that merge is the human release gate. Ask the user to merge it; do not merge it yourself. CI re-runs `release check` on the PR (Step 2 invariant) before it is mergeable.
- On the merge to main, **CI is the single owner of tag and publish**: the resulting main push carries the `chore(release): vX.Y.Z` commit, and the release workflow creates and pushes the annotated tag `vX.Y.Z` (tags are not branch-protected; CI uses the default `GITHUB_TOKEN` with `contents:write`, no PAT, and never pushes a commit to protected main) and publishes the GitHub Release (`draft:false`) with the CHANGELOG section as the notes. Do **not** run `gh release create` by hand — a manual published release racing the auto-published one is exactly what this removes.

This stage never squash-merges a feature branch and never commits on a `develop` branch (there is none — the repo is trunk-only). The routine per-PR squash-merge that closes each issue lives in `/solomon-review` close-out.

## 5. Close out
After the prep PR is merged and CI has tagged and published:
- Move the board: close the milestone and move any of its cards still showing `QA` to `Done` (`uv run python -m solomon_harness.github set-status --issue <issue> --status "Done"` for each lagging card; most close automatically on their PR merge during review).
- Refresh the living wiki: run `uv run python -m solomon_harness.cli wiki` to regenerate `docs/wiki/Code-Overview.md` from the re-indexed code, then append one line per shipped issue to `docs/wiki/Delivered.md` (create it if absent) recording the milestone, the issue (number, title), the version, and the date. Sync to the GitHub wiki with `scripts/wiki-sync.sh`.
- Record the delivered release in the project memory: `mcp__solomon-memory__save_release(version="vX.Y.Z", tag="vX.Y.Z", notes="<changelog section>", issue_github_id="<epic or representative issue>", milestone_id="<resolved milestone>", commit_sha="<chore(release) commit on main>")`. The `milestone_id` is now always resolvable from `release plan`.
- `mcp__solomon-memory__save_decision` for the release: title `Release vX.Y.Z`, the computed bump and the milestone scope, the readiness verdict and any conditions, outcome, author `sre`, branch **main** (not develop), and the `chore(release): vX.Y.Z` commit SHA.
- Write the compact release → done handoff contract to `.solomon/handoffs/release-vX.Y.Z-to-done.md` using the template in `docs/solomon-workflow.md` (release notes, the version/tag, what shipped across the milestone, and any GO-WITH-CONDITIONS follow-ups).
- `mcp__solomon-memory__log_handoff(sender="sre", recipient="done", contract_type="release", contract_path=".solomon/handoffs/release-vX.Y.Z-to-done.md", status="completed")`.
- `mcp__solomon-memory__save_session` to checkpoint the released milestone and the readiness baseline for the next release.

Report the released version and tag, the prep-PR merge commit, the milestone closed, the board move, and any GO-WITH-CONDITIONS follow-ups. Output direct, professional English, no emojis.
