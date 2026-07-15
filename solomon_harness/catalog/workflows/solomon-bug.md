---
description: File a structured bug report, label and prioritize it, place it on the board Backlog, and record it in memory.
argument-hint: <bug description, with repro steps / env / severity if known>
---

You are running the `/solomon-bug` stage. Read
`docs/solomon-workflow.md` first and follow it exactly: this is the bug-entry
stage, the issue is labeled `type:bug`, and the card lands in `Backlog`.

Adopt the driving specialists for this stage: **qa** (defect triage, severity,
the regression-test gate) and **software_engineer** (reproduction plausibility,
suspected area). For non-trivial triage — reconstructing repro steps, judging
severity, or scoping the suspected component — delegate through the host's native specialist-delegation mechanism to the
`qa` and `software_engineer` subagents in `agents/` and fold their
findings into the report. Keep the writing direct and professional; no emojis.

Raw input to shape: {{arguments}}

Steps:

1. Parse `{{arguments}}` into the bug template from the workflow doc. Produce a
   Markdown body with these exact sections:
   - **Summary** — one or two sentences.
   - **Steps to reproduce** — a numbered, deterministic list.
   - **Expected vs actual** — what should happen against what does.
   - **Environment** — OS, runtime/version, branch or commit, config relevant to
     the defect.
   - **Suspected location** — the `file:line`(s) most likely at fault, from a
     quick read of the code, and where the fix will land. This is the bug's
     implementation-ready pointer, so the implementer does not start from a blank
     page; write `TBD` only when triage genuinely cannot narrow it.
   - **Severity** — classify and map to a priority: `p0` data loss / outage /
     security, `p1` broken core flow with no workaround, `p2` degraded or
     cosmetic with a workaround.
   - **Verification** — the exact command(s) that reproduce the defect now and
     prove the fix later: the failing test to add, or a manual repro to run.
   - **Regression test required** — an explicit note that the fix is not closeable
     until a failing test reproducing this bug exists and then passes
     (TDD: red before green).
   - **Acceptance criteria** — the observable conditions the fix must meet, as
     `Given/When/Then`: the repro scenario now passes and no adjacent behavior
     regresses.
   - **Definition of Ready** — the repro is deterministic, severity and priority are
     assigned, and the suspected area is scoped; `/solomon-refine` completes any gaps
     before the fix starts.
   - **Definition of Done** — the failing regression test exists and then passes, the
     fix is merged with CI green, and no new failures appear; the bug is not closeable
     until its Definition of Done holds. `/solomon-review` and `/solomon-release`
     enforce it.
2. If repro steps, environment, or severity are missing and cannot be inferred,
   ask the user the minimum questions needed rather than inventing details.
3. Ensure the board exists once: `uv run python -I -m solomon_harness.github ensure-board`.
4. Show the user the drafted title, labels (`type:bug`, `priority:<p0|p1|p2>`,
   and an `area:<domain>` label if one fits), and the body. Creating an issue is
   an outward-facing action: get explicit confirmation before proceeding.
5. On approval, create the issue:
   - Ensure the standard labels exist first: `uv run python -I -m solomon_harness.github ensure-labels`
     (create a new `area:<domain>` with `gh label create "area:<domain>" --color BFD4F2 --force`).
   - `gh issue create --title "<title>" --label "type:bug" --label "priority:<pN>" --body "<body>"`
     (add `--label "area:<domain>"` when applicable). Capture the issue number and URL.
6. Move the card to Backlog:
   `uv run python -I -m solomon_harness.github set-status --issue <n> --status "Backlog"`.
7. Persist to memory per the handoff contract:
   - `log_issue(github_id=<n>, title=<title>, type_="bug", status="Backlog", milestone_id=null)`.
   - Write the compact handoff contract to `.agents/solomon/state/handoffs/issue-<n>-bug-to-refine.md`
     using the template in `docs/solomon-workflow.md` (a summary plus pointers to the
     issue and its repro/severity), so `/solomon-refine` reads it as its bounded input.
   - `log_handoff(sender="qa", recipient="software_engineer", contract_type="bug_report", contract_path=".agents/solomon/state/handoffs/issue-<n>-bug-to-refine.md", status="open")` to hand the defect to implementation; keep the returned handoff id.
   - `save_session(...)` to checkpoint if triage required substantial subagent work;
     pass `issues=[<n>]` (the worked_on edge, ADR-0018). When a session was saved,
     `link_session_handoff(session_id=<that session id>, handoff_id=<the returned handoff id>)` records the produced edge.
8. Report back the issue URL, the assigned priority, and a one-line reminder that
   the regression test is the close gate.

Do not branch, fix, or open a PR here — that begins at `/solomon-start`.

Present every decision, confirmation, and next-step choice through the host's native enumerable input mechanism, or as a numbered list ending in "Other" when structured input is unavailable — never as an open prose question or a command to copy. This is the non-negotiable Enumerable decisions rule in `agents/AGENTS.md`.
