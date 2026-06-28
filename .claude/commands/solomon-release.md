---
description: Run the production readiness review, then merge and release an approved PR (sre).
argument-hint: [pr-number]
allowed-tools: Bash(gh:*), Bash(git:*), Bash(uv run:*), Bash(scripts/wiki-sync.sh:*), Task, Read, Write, Edit, mcp__solomon-memory__log_issue, mcp__solomon-memory__save_decision, mcp__solomon-memory__save_release, mcp__solomon-memory__log_handoff, mcp__solomon-memory__save_session, mcp__solomon-memory__get_latest_activity
---

Read `docs/solomon-workflow.md` first and follow the Deliver/release stage exactly. Drive this as the **sre** specialist; delegate the production readiness review and release mechanics to the `.claude/agents/sre` subagent via the Task tool, grounded in its `production_readiness_review` and `release_engineering_and_progressive_delivery` skills. This is the `QA` → `Done` transition.

PR to release: **$ARGUMENTS** (a PR number). If empty, stop and ask for it.

## 1. Gather state
- First read the latest incoming handoff with `mcp__solomon-memory__get_latest_activity` and open its `contract_path` (the review → release contract). Treat it as the bounded input for this release; open the artifacts it points to (PLAN.md, the diff, the ADR, the PR) only when needed instead of re-deriving prior context.
- `gh pr view $ARGUMENTS --json number,title,state,mergeable,reviewDecision,headRefName,baseRefName,body,statusCheckRollup` — confirm it is open, `APPROVED`, mergeable, and that required checks are green. If review is not approved or checks fail, stop and report; do not proceed to merge.
- Read the linked issue from the PR body (`Closes #<issue>`) and `gh issue view <issue>`.
- Confirm the board exists with `uv run python -m solomon_harness.github ensure-board`.

## 2. Production Readiness Review (PRR)
Have the sre subagent walk the PRR checklist from `production_readiness_review.md` against this change and produce one verdict (GO / GO-WITH-CONDITIONS / NO-GO):
- SLIs/SLOs with an explicit rolling window and an enforced error-budget policy.
- Actionable burn-rate alerts, an overview dashboard, capacity/load headroom with N+1.
- A tested, automated rollback independent of the change; backward-compatible (expand/contract) migrations.
- A staffed on-call rotation, escalation path, reachable runbooks; every hard dependency has a failure mode and mitigation.

File each gap with `mcp__solomon-memory__log_issue` (and `gh issue create` with `type:chore` + `priority:*` when it needs tracking on the board). A **NO-GO** or any launch-blocking gap halts the release — report and stop. A **GO-WITH-CONDITIONS** records each condition, owner, and due date.

## 3. ADR re-check
Re-evaluate architectural significance for anything that emerged during review, using `docs/adr/README.md` and the software_architect checklist. If significant, delegate the ADR to the software_architect subagent (`docs/adr/NNNN-<slug>.md`), record it with `save_decision`, and link it in the PR. If not, note in the PR that no ADR is needed.

## 4. Confirm, then merge and release
Summarize the PRR verdict, the version bump, and the changelog entry, then **ask the user to confirm before merging or releasing**. Never push to a protected branch directly. Only after explicit approval:
- `gh pr merge $ARGUMENTS --squash --delete-branch` (this closes the linked issue).
- Bump the version in `pyproject.toml` (semver: patch/minor/major per the change).
- Update `CHANGELOG.md` (create it if absent) with the version, date, and a concise entry.
- Commit on `develop` with a Conventional Commit (`chore(release): vX.Y.Z`), then tag: `git tag -a vX.Y.Z -m "Release vX.Y.Z"` and push the tag.
- `gh release create vX.Y.Z --title "vX.Y.Z" --notes "<changelog section>"`.

## 5. Close out
- Move the card: `uv run python -m solomon_harness.github set-status --issue <issue> --status "Done"`.
- Refresh the living wiki: run `uv run python -m solomon_harness.cli wiki` to regenerate
  `docs/wiki/Code-Overview.md` from the re-indexed code, then append one line to
  `docs/wiki/Delivered.md` (create it if absent) recording the delivered issue (number,
  title, version, date). Sync to the GitHub wiki with `scripts/wiki-sync.sh`.
- Record the delivered release in the project memory: `mcp__solomon-memory__save_release(version="vX.Y.Z", tag="vX.Y.Z", notes="<changelog section>", issue_github_id="<issue>", milestone_id="<milestone if any>", commit_sha="<merge SHA>")`.
- `mcp__solomon-memory__save_decision` for the release: title `Release vX.Y.Z`, the PRR verdict and conditions, outcome, author `sre`, the `develop` branch, and the merge commit SHA.
- Write the compact release → done handoff contract to `.solomon/handoffs/issue-<issue>-release-to-done.md` using the template in `docs/solomon-workflow.md` (release notes, the version/tag, what shipped, and any GO-WITH-CONDITIONS follow-ups).
- `mcp__solomon-memory__log_handoff(sender="sre", recipient="done", contract_type="release", contract_path=".solomon/handoffs/issue-<issue>-release-to-done.md", status="completed")`.
- `mcp__solomon-memory__save_session` to checkpoint the PRR baseline for the next release.

Report the released version, the merge commit, the board move, and any GO-WITH-CONDITIONS follow-ups.
