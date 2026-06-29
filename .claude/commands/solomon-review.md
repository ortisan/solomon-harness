---
description: Review a pull request through QA, security, and architecture gates, then approve or request changes
argument-hint: [pr-number]
allowed-tools: Bash(gh:*), Bash(git:*), Bash(uv run:*), Task, Read, Write, mcp__solomon-memory__save_decision, mcp__solomon-memory__log_issue, mcp__solomon-memory__log_handoff, mcp__solomon-memory__save_session, mcp__solomon-memory__get_open_issues, mcp__solomon-memory__get_latest_activity
---

You are running the Review stage of the solomon lifecycle for PR #$ARGUMENTS.

First, read `docs/solomon-workflow.md` and `docs/adr/README.md` so the board
columns, labels, the ADR trigger, and the memory handoff contract are exact. This
stage is driven by three specialist agents — qa, security, and software_architect.
Delegate the heavy analysis to each via the Task tool (the `.claude/agents`
subagents); do not review with a single generic pass.

## 1. Establish context
- `gh pr view $ARGUMENTS` and `gh pr diff $ARGUMENTS` to read the change and its
  linked issue. Identify the issue number from the `Closes #<issue>` line.
- Check the board card is `Code Review`; if not, `uv run python -m solomon_harness.github ensure-board`
  then `uv run python -m solomon_harness.github set-status --issue <issue> --status "Code Review"`.
- Pull prior context: `mcp__solomon-memory__get_latest_activity` first — read the
  latest incoming handoff contract at its `contract_path` (the start -> review
  contract) and treat it as the bounded input, reviewing the diff through the
  pointers it gives (PLAN.md, the diff, the ADR, the PR) only as needed instead of
  re-deriving the whole context. Then `mcp__solomon-memory__get_open_issues` for known
  debt and the design this change claims to implement (link any ADR referenced in the
  PR body).

## 2. Run the three lenses (delegate, in parallel where possible)
- qa agent: verify the test pyramid (`the_test_pyramid_target_distribution`) and the
  `ci_quality_gates` skill, then actually run the suite —
  `uv run pytest --cov --cov-branch --cov-report=term-missing`. Confirm new and
  changed behavior has covering tests and the full suite is green.
- security agent: STRIDE pass per `threat_modeling_with_stride` plus an SAST sweep
  (`sast` skill) over the diff. Flag any secret, injection, or unmitigated boundary.
- software_architect agent: apply the `architecture_review_gate` checklist against
  the design contracts, the fitness functions, and any ADR the change touches.
  If the change is architecturally significant but no ADR exists, that is a blocker.

Board: the software_architect's code review is the `Code Review` gate. Once it
passes with no blockers, move the card to `QA`
(`uv run python -m solomon_harness.github set-status --issue <issue> --status "QA"`)
and run the qa and security lenses there. A blocker at either gate keeps the card
in its current column and requests changes.

Each lens returns findings tagged blocker, major, or minor.

## 3. Decide the verdict
- Block approval (request changes) on: missing tests for changed behavior, a failing
  test run, a failing fitness function or quality gate, an unmitigated high-value
  STRIDE threat, or a missing required ADR — any blocker.
- Approve only when there are zero blockers and zero open majors.

## 4. Post the outcome (confirm with the user before submitting the review)
- Inline, specific findings: `gh pr comment $ARGUMENTS --body "<finding + file:line>"`
  for each concrete issue, one comment per finding.
- Summary verdict: `gh pr review $ARGUMENTS --approve` or
  `gh pr review $ARGUMENTS --request-changes --body "<blocking findings>"`.
- On an **approve** verdict, take the PR out of draft: run `gh pr ready $ARGUMENTS`.
  This is mandatory, not optional — a draft PR cannot be merged, so leaving it in
  draft strands an approved change. The command is idempotent (a no-op if already
  ready). If `gh pr review --approve` is refused because the reviewer authored the PR
  (single-maintainer self-review), the posted comment is the approval of record and
  `gh pr ready` is still what advances the PR; run it regardless.
- File each blocker/major as a tracked issue with `mcp__solomon-memory__log_issue`.

## 5. Persist to memory
- `mcp__solomon-memory__save_decision` with the review outcome (title, rationale,
  outcome go/no-go, author, branch, commit_sha) in ADR shape.
- On approval only: write the compact review -> release handoff contract to
  `.solomon/handoffs/issue-<issue>-review-to-release.md` using the template in
  `docs/solomon-workflow.md` (go/no-go verdict, findings, what to release), then
  `mcp__solomon-memory__log_handoff(sender="qa", recipient="sre",
  contract_type="release-candidate",
  contract_path=".solomon/handoffs/issue-<issue>-review-to-release.md", status="approved")`
  so the Release stage can resume.
- `mcp__solomon-memory__save_session` capturing what was reviewed, the verdict, and
  the linked decision and issue IDs.

State explicitly whether an ADR was required and whether one exists. Do not push,
merge, or change the board to `Done` here — Review moves the card `Code Review` →
`QA` and ends in `QA`; release is a separate stage. Output direct, professional
English, no emojis.
