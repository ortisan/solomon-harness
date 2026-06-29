---
description: Orchestrate the lifecycle — scan where work stopped and propose/run the next /solomon-* step
argument-hint: (optional) a focus, e.g. an issue or PR number
allowed-tools: Bash(gh:*), Bash(git:*), Bash(uv run:*), Task, Read, AskUserQuestion, mcp__solomon-memory__get_latest_activity, mcp__solomon-memory__get_open_issues, mcp__solomon-memory__save_decision, mcp__solomon-memory__log_handoff
---

You are the orchestrator for the solomon delivery lifecycle. Read
`docs/solomon-workflow.md` first. Your job: scan where work stopped, then propose
— and, on the user's confirmation, run — the single best next `/solomon-*`
workflow. `$ARGUMENTS` may narrow the focus to a specific issue or PR.

## 1. Scan the current state

Gather these and summarize them concisely:

- `mcp__solomon-memory__get_latest_activity` — the last recorded session or handoff (where the team stopped). If it returns a handoff with a `contract_path`, read that handoff contract first and treat it as the bounded input — open the artifacts it points to (PLAN.md, the diff, the ADR, the PR) only when you need them, instead of re-deriving prior context.
- `mcp__solomon-memory__get_open_issues` and `gh issue list --state open` — open work and its labels.
- `gh pr list --state open` — pull requests and their review/approval state.
- The board columns (Ready / In Progress / Code Review / QA) via `gh project item-list` or `solomon_harness.github`.

## 2. Decide the next step (first match wins)

1. A pull request that is **approved** → `/solomon-release <pr>`.
2. A pull request **open and awaiting review** → `/solomon-review <pr>`.
3. An issue **In Progress** with a branch but no PR yet → resume with `/solomon-start <issue>` (continue the TDD loop and open the PR).
4. A **Ready** issue (refined, Definition of Ready met) → `/solomon-start <issue>`.
5. A **Backlog** issue not yet refined → `/solomon-refine <issue>`.
6. An **Idea** worth promoting → `/solomon-issue` (or `/solomon-refine`).
7. **Nothing in progress and the backlog is empty** → there is no work to advance; ask the user whether to create one — `/solomon-idea`, `/solomon-issue`, or `/solomon-bug` — and what it is about.

If `$ARGUMENTS` names a specific issue or PR, evaluate that item and pick its next step.

## 3. Propose as an enumerated decision card, confirm, run

Present the next step as a decision card, not an open prose question — discrete,
numbered choices keep the user's context focused (see "Interaction style" in
`docs/solomon-workflow.md`):

- In two to four lines, summarize where things stopped and what is in flight. You
  can read `solomon-harness log` for the recent loop / decision / handoff trail.
- Offer the single recommended next step first, then any genuinely credible
  alternatives the ladder surfaced, as numbered options whose last entry is always
  "Other" (a free-text answer). Each option is the exact `/solomon-*` command and
  its target. In Claude Code use the AskUserQuestion tool; in the Gemini CLI
  present the numbered list and invite a free-text reply.
- Wait for the pick. Outward-facing actions (creating issues or PRs, merging,
  releasing) always require an explicit go-ahead.
- On the pick, run that workflow by following its command file
  `.claude/commands/solomon-<stage>.md` and delegating to its driving agents.
  Advance one stage per invocation; re-run `/solomon-loop` to continue.

## 4. Record

- `mcp__solomon-memory__save_decision` — the loop's recommendation and the chosen action, so the next session resumes from it.
- `mcp__solomon-memory__log_handoff` — when the chosen workflow hands off to the next stage.

Never advance more than one stage without checking in. The loop proposes; the user decides.
