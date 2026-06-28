---
description: Start development on a Ready issue: branch, PLAN.md, TDD loop, ADR check, draft PR.
argument-hint: [issue-number]
allowed-tools: Bash(gh:*), Bash(git:*), Bash(uv run:*), Task, Read, Write, Edit, mcp__solomon-memory__get_issue, mcp__solomon-memory__log_issue, mcp__solomon-memory__save_decision, mcp__solomon-memory__log_handoff, mcp__solomon-memory__save_session
---

Begin implementation of issue **#$ARGUMENTS**. First read `docs/solomon-workflow.md`
and follow its lifecycle, branch/label conventions, ADR trigger, and memory handoff
contract exactly. This stage is driven by three specialists — delegate the heavy work
to their subagents via the Task tool: `scrum_master` (branch + board), `software_engineer`
(PLAN.md + TDD), and `software_architect` (ADR evaluation).

Confirm with the user before any push or PR creation. Never push to `develop` or `main`.

## 1. Load context
- `gh issue view $ARGUMENTS` to read the title, body, acceptance criteria, and labels.
- `mcp__solomon-memory__get_issue("$ARGUMENTS")` for prior context; check the card is in
  `Ready`. If it is not refined, stop and tell the user to run `/solomon-refine` first.
- Derive a kebab `<slug>` from the issue title. Choose `feature/` if labeled `type:feature`
  (or idea/chore) and `bugfix/` if labeled `type:bug`.

## 2. Branch and move to In Progress (scrum_master)
- Confirm the branch name with the user, then:
  `git fetch origin && git switch develop && git pull && git switch -c feature/$ARGUMENTS-<slug>`.
- `uv run python -m solomon_harness.github ensure-board` (idempotent), then
  `uv run python -m solomon_harness.github set-status --issue $ARGUMENTS --status "In Progress"`.
- `mcp__solomon-memory__log_issue(github_id=$ARGUMENTS, title=..., type_=..., status="in_progress", milestone_id=...)`.

## 3. Plan (software_engineer, plan_authoring skill)
- Write `PLAN.md` at the repo root with all required sections: problem statement (link #$ARGUMENTS),
  proposed change and the boundary it touches, target files, edge cases as observable outcomes,
  a 3–8 step red/green TDD breakdown (one commit each), STRIDE notes when input/auth/data/external
  surface is touched, and objectively checkable verification criteria.
- Record the design decision: `mcp__solomon-memory__save_decision(title, rationale, outcome, author="software_engineer", branch="feature/$ARGUMENTS-<slug>")`.
- Show PLAN.md to the user before coding.

## 4. ADR evaluation (software_architect)
- Evaluate architectural significance against `docs/adr/README.md` and the
  `architecture_decisions_in_project_memory` skill (new dependency/datastore, changed public
  contract or data model, cross-cutting pattern, quality-attribute trade-off, hard to reverse).
- If significant: the `software_architect` subagent copies `docs/adr/0000-adr-template.md` to
  `docs/adr/NNNN-<slug>.md` (next number), fills the MADR sections, and records it with
  `mcp__solomon-memory__save_decision(title="ADR-NNNN: ...", outcome="Status: Accepted\n...", author="software_architect", branch="feature/$ARGUMENTS-<slug>")`.
- If not significant: state that explicitly (you will repeat it in the PR body).

## 5. TDD implementation (software_engineer, tdd_red_green_refactor)
- Run the loop per PLAN.md step: write the failing test (Red), minimal code to pass (Green),
  refactor on green. Commit each step with a Conventional Commits message; the commit-msg hook
  enforces format and bans emojis.
- Keep the diff inside the PLAN.md target-files fence; re-plan if it strays.

## 6. Draft PR, In Review, handoff
- Confirm with the user, then push: `git push -u origin feature/$ARGUMENTS-<slug>`.
- Open a draft PR: `gh pr create --draft --base develop --title "<conventional title>" --body "..."`.
  The body must contain `Closes #$ARGUMENTS`, summarize the change, and either link the ADR
  (`docs/adr/NNNN-<slug>.md`) or state that no ADR was warranted and why.
- `uv run python -m solomon_harness.github set-status --issue $ARGUMENTS --status "In Review"`.
- `mcp__solomon-memory__log_handoff(sender="software_engineer", recipient="qa", contract_type="pull_request", contract_path="<pr-url>", status="ready")`.
- `mcp__solomon-memory__save_session(session_id="start-$ARGUMENTS", agent_name="software_engineer", task="Implement #$ARGUMENTS", messages=...)` to checkpoint.
- Report the branch, PR URL, ADR decision, and that qa should run `/solomon-review`.
