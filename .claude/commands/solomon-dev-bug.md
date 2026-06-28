---
description: File a structured bug report, label and prioritize it, place it on the board Backlog, and record it in memory.
argument-hint: <bug description, with repro steps / env / severity if known>
allowed-tools: Bash(gh:*), Bash(git:*), Bash(uv run:*), Task, Read, mcp__solomon-memory__log_issue, mcp__solomon-memory__log_handoff, mcp__solomon-memory__save_session
---

You are running the `/solomon-dev-bug` stage. Read
`docs/solomon-dev-workflow.md` first and follow it exactly: this is the bug-entry
stage, the issue is labeled `type:bug`, and the card lands in `Backlog`.

Adopt the driving specialists for this stage: **qa** (defect triage, severity,
the regression-test gate) and **software_engineer** (reproduction plausibility,
suspected area). For non-trivial triage — reconstructing repro steps, judging
severity, or scoping the suspected component — delegate via the Task tool to the
`qa` and `software_engineer` subagents in `.claude/agents/` and fold their
findings into the report. Keep the writing direct and professional; no emojis.

Raw input to shape: $ARGUMENTS

Steps:

1. Parse `$ARGUMENTS` into the bug template from the workflow doc. Produce a
   Markdown body with these exact sections:
   - **Summary** — one or two sentences.
   - **Steps to reproduce** — a numbered, deterministic list.
   - **Expected vs actual** — what should happen against what does.
   - **Environment** — OS, runtime/version, branch or commit, config relevant to
     the defect.
   - **Severity** — classify and map to a priority: `p0` data loss / outage /
     security, `p1` broken core flow with no workaround, `p2` degraded or
     cosmetic with a workaround.
   - **Regression test required** — an explicit note that the fix is not closeable
     until a failing test reproducing this bug exists and then passes
     (TDD: red before green).
2. If repro steps, environment, or severity are missing and cannot be inferred,
   ask the user the minimum questions needed rather than inventing details.
3. Ensure the board exists once: `uv run python -m solomon_harness.github ensure-board`.
4. Show the user the drafted title, labels (`type:bug`, `priority:<p0|p1|p2>`,
   and an `area:<domain>` label if one fits), and the body. Creating an issue is
   an outward-facing action: get explicit confirmation before proceeding.
5. On approval, create the issue:
   `gh issue create --title "<title>" --label "type:bug" --label "priority:<pN>" --body "<body>"`
   (add `--label "area:<domain>"` when applicable). Capture the issue number and URL.
6. Move the card to Backlog:
   `uv run python -m solomon_harness.github set-status --issue <n> --status "Backlog"`.
7. Persist to memory per the handoff contract:
   - `log_issue(github_id=<n>, title=<title>, type_="bug", status="Backlog", milestone_id=null)`.
   - `log_handoff(sender="qa", recipient="software_engineer", contract_type="bug_report", contract_path="<issue URL>", status="open")` to hand the defect to implementation.
   - `save_session(...)` to checkpoint if triage required substantial subagent work.
8. Report back the issue URL, the assigned priority, and a one-line reminder that
   the regression test is the close gate.

Do not branch, fix, or open a PR here — that begins at `/solomon-dev-start`.
