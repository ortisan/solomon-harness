---
description: Run a task end-to-end, or continue from a previous execution
argument-hint: (optional) a focus, e.g. an issue or PR number
allowed-tools: Bash(gh:*), Bash(git:*), Bash(uv run:*), Task, Read, AskUserQuestion, mcp__solomon-memory__get_latest_activity, mcp__solomon-memory__get_open_issues, mcp__solomon-memory__save_decision, mcp__solomon-memory__log_handoff
---

You are the orchestrator for the solomon delivery lifecycle. Read
`docs/solomon-workflow.md` first. Your job: scan where work stopped, then propose
— and, on the user's confirmation, run — the single best next `/solomon-*`
workflow. `$ARGUMENTS` may narrow the focus to a specific issue or PR.

This loop is host-orchestrated and human-gated, not fully autonomous: no code
decides the next stage — the host tool (Claude Code or the Gemini CLI) executes
these markdown prompts and the specialist agents — and the merge, release, and
move-to-Done gates always require a human.

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

A headless `/solomon-loop` iteration (`solomon-harness dev loop`) has no human to
answer this card: `run_stage` prepends a directive to this prompt in that case only,
telling the model to skip this section entirely (no `AskUserQuestion` call, no
numbered list awaiting a reply) and enter Option 2 (Autonomous Mode) directly. A
direct `/solomon-workflow` invocation never receives that directive, so it always
follows the steps below unchanged.

Present the next step and execution options as a decision card with the following numbered options:
1. **Single Step (Recommended)**: Run the single recommended next workflow stage ($RECOMMENDED_CMD).
2. **Autonomous Mode (host-orchestrated, human-gated)**: Advance every eligible ready, in-progress, and reviewable task on the board in sequence, running stages (such as start, review) without re-prompting on each step. This is host-orchestrated, not fully autonomous — the host tool runs each markdown stage in turn — and it stops at the first human-gated boundary: it never merges, releases, or moves a card to Done, and it halts when all eligible tasks are completed or blocked at the human-gated Release gate.
3. **Other**: Free-text entry.

- If the user selects Option 1 (Single Step):
  - Run the recommended workflow stage by following its command file `.claude/commands/solomon-<stage>.md` or executing `uv run python -m solomon_harness.cli dev <stage> [args]`.
  - Advance one stage, record the run/decision, and exit.

- If the user selects Option 2 (Autonomous Mode):
  - Enter an autonomous loop. In each iteration:
    1. Scan the current board and database state.
    2. Determine the next step using the "Decide the next step" rules.
    3. If the next step is a permanently human-gated stage (such as `release`), skip/bypass it and evaluate the remaining rules to find the next actionable, non-human-gated task (e.g. reviewing open PRs, starting ready issues). If no actionable tasks can be progressed, break the loop, notify the user, and report the final status.
    4. Otherwise, execute the workflow stage headless by running `solomon-harness dev <stage> [args]` (equivalently `uv run python -m solomon_harness.cli dev <stage> [args]`). This is the only path that acquires the single-driver loop lock, so a concurrent headless `solomon-harness dev` run can detect contention instead of racing it. Never run the workflow logic directly in-process as an alternative — an iteration that pushes branches or opens PRs without going through `dev` holds no lock and defeats the single-driver guarantee.
    5. Save the decision and loop run to memory.
  - Present a final summary of all tasks implemented and reviewed.

## 4. Record

- `mcp__solomon-memory__save_decision` — the loop's recommendation and the chosen action, so the next session resumes from it.
- `mcp__solomon-memory__log_handoff` — when the chosen workflow hands off to the next stage.

