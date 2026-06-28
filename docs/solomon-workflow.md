# solomon workflow conventions

Shared conventions for the `/solomon-*` workflows. Every workflow command
reads this file and follows it so the lifecycle is consistent, auditable, and
backed by the project memory. The host tool (Claude Code or Gemini CLI) provides
the model; these workflows orchestrate the specialist agents, the GitHub project,
and the memory layer.

## Lifecycle and board

Work flows through a GitHub Project (v2) board with these Status columns:

`Ideas` → `Backlog` → `Ready` → `In Progress` → `In Review` → `Done`

| Stage | Workflow | Driving agents | Board move |
| --- | --- | --- | --- |
| Orchestrate (scan + next) | `/solomon-loop` | scrum_master | proposes the next step |
| Capture an idea | `/solomon-idea` | product_owner | → `Ideas` |
| Create a feature/story | `/solomon-issue` | product_owner | → `Backlog` |
| Create a bug | `/solomon-bug` | qa, software_engineer | → `Backlog` |
| Refine for readiness | `/solomon-refine` | product_owner, scrum_master | `Backlog` → `Ready` |
| Implement | `/solomon-start` | scrum_master, software_engineer, software_architect | `Ready` → `In Progress` → `In Review` |
| Review | `/solomon-review` | qa, security, software_architect | stays `In Review` (approve or request changes) |
| Deliver and release | `/solomon-release` | sre, software_engineer | `In Review` → `Done` |

The board and helpers live in `solomon_harness/github.py`. Create the board once
with `ensure_project_board`; move cards with `set_issue_status`.

## The loop and session resumption

`/solomon-loop` is the orchestrator. It scans the project memory and the board to
find where work stopped, then proposes the single best next step — one of the
workflows above — and runs it on confirmation. It advances one stage per
invocation: when work is in flight it proposes development, review, or release;
when nothing is in progress it proposes creating a feature, bug, or refinement.

At the start of every Claude Code or Gemini CLI session, the harness surfaces the
project status (latest activity and open issues) through a SessionStart hook that
runs `solomon-harness run`, so a session always resumes where the previous one
stopped. Run `/solomon-loop` to continue from there.

## GitHub conventions

- Issues are created with `gh issue create`. Labels: `type:feature`, `type:bug`,
  `type:idea`, `type:chore`; plus `priority:p0|p1|p2` and `area:<domain>`.
- Branches (Git Flow): `feature/<issue>-<slug>` for features, `bugfix/<issue>-<slug>`
  for defects, `hotfix/<version>` for production-critical fixes. Branch from `develop`.
- Commits: Conventional Commits, no emojis (the commit-msg hook enforces this).
- Pull requests: conventional title, body that contains `Closes #<issue>`, opened
  as a draft until `/solomon-review` approves. Link the ADR if one was written.

## Issue body templates

- Feature/story: problem statement, user story (`As a … I want … so that …`),
  acceptance criteria as Given/When/Then, scope and out-of-scope, definition of ready.
- Bug: summary, steps to reproduce, expected vs actual, environment, severity, and
  a note that a regression test is required before the fix is closed.
- Idea: the job-to-be-done, the opportunity, the riskiest assumption to validate,
  and what evidence would justify promoting it to the backlog.

## Memory handoff contract

Every stage persists to the project memory through the `solomon-memory` MCP tools
so the next stage (and a future session) can resume:

- `log_issue(github_id, title, type_, status, milestone_id)` when an issue is created
  or its status changes.
- `save_decision(title, rationale, outcome, author, branch, commit_sha)` for product,
  design, review, and release decisions (and for every ADR).
- `log_handoff(sender, recipient, contract_type, contract_path, status)` at each
  stage boundary (e.g. software_engineer → qa at PR open, qa → sre at approval).
- `save_session(session_id, agent_name, task, messages)` to checkpoint long work.
- `get_open_issues` / `get_latest_activity` to resume where the team stopped.

## ADR trigger

`/solomon-start` and `/solomon-release` must evaluate whether the change is
architecturally significant using the checklist in
`agents/software_architect/skills/architecture_decisions_in_project_memory.md` and
`docs/adr/README.md`. If significant, the software_architect agent writes
`docs/adr/NNNN-<slug>.md` from `docs/adr/0000-adr-template.md`, records it with
`save_decision`, and links it in the PR. If not significant, state that explicitly
in the PR so the decision to skip an ADR is also visible.

## Authorization

These workflows perform outward-facing actions (creating issues, branches, PRs,
merges, releases). Confirm with the user before any merge or release, and never
push to a protected branch directly.
