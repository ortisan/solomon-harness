# solomon workflow conventions

Shared conventions for the `/solomon-*` workflows. Every workflow command
reads this file and follows it so the lifecycle is consistent, auditable, and
backed by the project memory. The host tool (Claude Code or Gemini CLI) provides
the model; these workflows orchestrate the specialist agents, the GitHub project,
and the memory layer.

## Lifecycle and board

Work flows through a GitHub Project (v2) board with these Status columns:

`Ideas` → `Backlog` → `Ready` → `In Progress` → `Code Review` → `QA` → `Done`

| Stage | Workflow | Driving agents | Board move |
| --- | --- | --- | --- |
| Orchestrate (scan + next) | `/solomon-loop` | scrum_master | proposes the next step |
| Capture an idea | `/solomon-idea` | product_owner | → `Ideas` |
| Create a feature/story | `/solomon-issue` | product_owner | → `Backlog` |
| Create a bug | `/solomon-bug` | qa, software_engineer | → `Backlog` |
| Refine for readiness | `/solomon-refine` | product_owner, scrum_master | `Backlog` → `Ready` |
| Implement | `/solomon-start` | scrum_master, software_engineer, software_architect | `Ready` → `In Progress` → `Code Review` |
| Review | `/solomon-review` | software_architect (code), then qa, security | `Code Review` → `QA` (then approved) |
| Deliver and release | `/solomon-release` | sre, software_engineer | `QA` → `Done` |

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

## Interaction style

When a workflow needs a decision or confirmation from the user — which next step,
which option, which target — present the choices as an enumerated list (1, 2, 3, …),
with the final option always being "Other", where the user types a free-form answer.
In Claude Code this is the AskUserQuestion tool; in the Gemini CLI, present a numbered
list and invite a free-text reply. Lead with the recommended option first and keep the
options mutually exclusive. Prefer this over an open prose question: discrete, numbered
choices keep the user's context focused and prevent dispersion.

## GitHub conventions

- Issues are created with `gh issue create`. Labels: `type:feature`, `type:bug`,
  `type:idea`, `type:chore`; plus `priority:p0|p1|p2` and `area:<domain>`.
- Branches (Git Flow): `feature/<slug>` for features, `bugfix/<slug>` for defects,
  `hotfix/<version>` for production-critical fixes. The branch name carries NO issue
  number (kept deliberately clean); `<slug>` is the kebab-cased issue title. The issue
  is linked instead by the back-link comment and the `Refs #`/`Closes #` trailers.
  Branch from `develop`.
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

## Handoff contracts (bounded context)

To keep each stage's context bounded and avoid re-reading everything, every stage
transition produces a compact **handoff contract** artifact, and the receiving
stage reads that contract as its primary input — opening additional files only
through the pointers the contract gives. This is what prevents context overflow as
work moves across stages and sessions.

Rules:

- At the end of a stage that hands off, WRITE the contract to
  `.solomon/handoffs/issue-<N>-<from>-to-<to>.md` (the `.solomon/` directory is
  gitignored local state), then call
  `log_handoff(sender, recipient, contract_type, contract_path, status)` with
  `contract_path` set to that file.
- At the start of a stage, READ the latest incoming contract first
  (`get_latest_activity` returns the most recent handoff and its `contract_path`).
  Treat it as your bounded input; open the artifacts it points to (PLAN.md, the
  diff, the ADR, the PR) only when you actually need them. Do not re-derive prior
  context from scratch.
- The contract is a summary plus pointers, kept short on purpose. The full detail
  lives in the artifacts it references and in the project memory.

Contract template:

```
# Handoff: <from-stage> -> <to-stage> · issue #<N>
- Date: <YYYY-MM-DD> · Author: <agent>
- Issue: #<N> <url> · Branch: <branch> · PR: #<M> <url> · Board: <column>

## What this stage did
<2-5 lines>

## Artifacts (open only if needed)
- PLAN.md · docs/adr/NNNN-*.md · PR #<M> · test plan · ...

## Acceptance criteria status
<which acceptance criteria are met; what remains>

## Input for the next stage (<to-stage>)
<exactly what the next stage needs to act — the bounded handoff>

## Open questions / risks
<anything the next stage must watch>
```

Each stage also persists the lifecycle facts to the project memory:

- `log_issue(github_id, title, type_, status, milestone_id)` when an issue is created
  or its status changes.
- `save_decision(title, rationale, outcome, author, branch, commit_sha)` for product,
  design, review, and release decisions (and for every ADR).
- `save_session(session_id, agent_name, task, messages)` to checkpoint long work.
- `get_open_issues` / `get_latest_activity` to resume where the team stopped.

## Single-driver lock and the loop run-log

Loop engineering turns the harness into a system that can advance work on a
cadence, so two drivers must never act on one repository at once. A documented
incident — two concurrent `/solomon-loop` drivers — produced premature merges
that bypassed the review gate and flipped `core.bare=true` on a worktree. The
safety floor prevents that by construction:

- **Single-driver lock.** Before a mutating stage runs (`loop`, `start`,
  `review`, `release`), the headless runner acquires one advisory lock anchored
  at the git *common* directory (`<common>/solomon-loop.lock`), so every linked
  worktree of the repository contends on the same file. A second driver is
  refused. The lock is a plain JSON file (the holder is auditable), and a stale
  lock — heartbeat older than the TTL, or a dead pid on the same host — is
  reclaimed automatically. Implementation: `solomon_harness/loop_lock.py`; the
  portable gate lives in `run_stage` so it enforces on both Claude Code and the
  Gemini CLI.
- **PreToolUse guard (Claude Code only).** A `loop-guard` hook in
  `.claude/settings.json` blocks `git push` / `gh pr merge` while another live
  driver holds the lock. It is defense-in-depth on top of the portable gate and
  fails open — the run_stage gate, not the hook, is the enforcement of record.
- **Recovery.** `solomon-harness loop-lock status` shows the current holder and
  whether it is stale; `solomon-harness loop-lock release` clears a stuck lock
  after a crash.
- **Run-log.** Each driven stage appends one entry to the `loop_runs` ledger in
  the project memory (the single source of truth). `solomon-harness log` renders
  a read-only, chronological feed over loop runs, decisions and handoffs, so the
  loop's own decisions are auditable. The concurrent-driver guard is the
  lockfile, never a row count — under the SQLite fallback each worktree has its
  own database, so a cross-worktree count would be invisible.

Human approval before any merge or release is unchanged: the lock bounds *who*
may drive, not *whether* a human approves. See `docs/loop-engineering.md` for the
full adaptation roadmap.

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
