---
description: Start development on a Ready issue: branch, PLAN.md, TDD loop, ADR check, draft PR.
argument-hint: [issue-number]
---

Begin implementation of issue **#{{arguments}}**. First read `docs/solomon-workflow.md`
and follow its lifecycle, branch/label conventions, ADR trigger, and memory handoff
contract exactly. This stage is driven by three specialists — delegate the heavy work
to their subagents through the host's native specialist-delegation mechanism: `scrum_master` (branch + board), `software_engineer`
(PLAN.md + TDD), and `software_architect` (ADR evaluation).

Confirm with the user before any push or PR creation. Never push to `develop` or `main`.

## 1. Load context
- First read the incoming handoff contract: `project-memory get_latest_activity` returns the
  latest `refine -> start` contract and its `contract_path`. Treat that contract as your bounded input
  and open the artifacts it points to (the refined issue, acceptance criteria) only when you need them,
  instead of re-deriving prior context.
- `gh issue view {{arguments}}` to read the title, body, acceptance criteria, and labels.
- Acquire the per-issue claim BEFORE creating any branch, PLAN, or worktree (ADR-0027 —
  interactive sessions get the same mutual exclusion as headless runs):
  `uv run solomon-harness claim acquire {{arguments}}`. A non-zero exit means another live
  session holds the issue (the error names the holder and claim age) or its liveness
  could not be confirmed — STOP and report that to the user; do not proceed, do not
  release the other session's claim. The claim is released automatically on merge, by a
  failed headless run, or manually with `solomon-harness claim release {{arguments}}`.
- `project-memory get_issue("{{arguments}}")` for prior context; check the card is in
  `Ready`. If it is not refined, stop and tell the user to run `/solomon-refine` first.
- **Capability Check** (see "Capability check" in `docs/solomon-workflow.md`):
  Verify the project has the capability (agent + skills) this issue needs.
  The deterministic router core builds the verdict (ADR-0008); you supply the
  match judgment as data — never build inline Python over issue text.
  - Write your demand and match judgment to `.agents/solomon/state/broker/route-{{arguments}}.json`
    with the host's file-write mechanism (so issue-derived text never touches a shell string):
    `{"demand": "<one-line capability demand>", "match": {"agent": <name or null>, "rationale": "<why>", "alternatives": [], "missing_capability": <text or null>, "nearest_agent": <name or null>}}`
  - Run `uv run python -I -m solomon_harness.cli broker route --file .agents/solomon/state/broker/route-{{arguments}}.json`
    and read the verdict JSON. The core validates the match against the catalog
    and fails closed (exit 3) on an empty catalog or a matcher-contract violation.
  - Route verdict: note the routed agent and continue the stage.
  - Gap verdict, interactive session: present the choice through the host's native enumerable input mechanism:
    1. Acquire the capability via the broker (recommended) — adapt the named
       skill into the nearest agent, or create the suggested agent.
    2. Proceed without acquiring (the gap stays recorded).
    3. Other.
    On option 1, write the proposal to `.agents/solomon/state/broker/proposal-{{arguments}}.json`
    (`{"kind": "adapt_skill", "source_name": "...", "skill_name": "...", "agent_name": "...", "issue": "{{arguments}}"}` or
    `{"kind": "create_agent", "agent_name": "...", "title": "...", "description": "...", "duties": ["..."], "issue": "{{arguments}}"}`),
    then run `uv run python -I -m solomon_harness.cli broker apply --file .agents/solomon/state/broker/proposal-{{arguments}}.json`.
    Read the result JSON and stop execution (do not proceed to Step 2):
    - `adapt_skill` returns `mode: reviewed_pr`; report its `pr_url`.
    - `create_agent` returns `mode: direct_registration`; report its `agent_path`,
      confirm that native adapters were compiled, and tell the user that
      `restart_required: true` means a new session is needed to load the agent.
  - Gap verdict, non-interactive/headless run: acquisition is human-gated and
    `broker apply` refuses it (exit 3) — do not attempt it. Record the gap
    verdict in the run report and continue the stage without acquiring.
- Derive a kebab `<slug>` from the issue title. Choose `feature/` if labeled `type:feature`
  (or idea/chore) and `bugfix/` if labeled `type:bug`.

## 2. Worktree and move to In Progress (scrum_master)
- The branch follows Git Flow and reflects the task: `feature/<slug>` (or
  `bugfix/<slug>` for `type:bug`), where `<slug>` is the kebab-cased issue title
  (trim to ~6 words). The branch name carries NO issue number — keep it clean; the branch
  maps back to the issue via the back-link comment and the `Refs #` / `Closes #` trailers.
  Confirm the name with the user.
- Create the branch in its own **isolated git worktree** instead of switching the current
  checkout, so the main checkout and any other in-flight issue stay untouched (a dirty tree
  never blocks a start, and several issues can be in flight at once):
  ```
  git fetch origin
  uv run python -I -m solomon_harness.cli worktree feature/<slug> --base develop
  ```
  Use `--base main` when the repository has no `develop` branch. The helper is idempotent
  (re-running reuses the existing worktree) and prints the absolute worktree path; on a
  conflicting path, or a branch already checked out elsewhere, it stops with a clear message
  and changes nothing. `cd` into the printed path and run the rest of this workflow
  (PLAN.md, ADR, TDD, commits, PR) from inside that worktree. The worktree lives at the
  sibling path `<repo>-worktrees/feature-<slug>` documented in `docs/solomon-workflow.md`.
- Bidirectional link: comment the branch onto the issue —
  `gh issue comment {{arguments}} --body "Started on branch \`feature/<slug>\` in a dedicated worktree."` —
  so the issue points to the branch and the branch name points back to the issue.
- `uv run python -I -m solomon_harness.github ensure-board` (idempotent), then
  `uv run python -I -m solomon_harness.github set-status --issue {{arguments}} --status "In Progress"`.
- `project-memory log_issue(github_id={{arguments}}, title=..., type_=..., status="in_progress", milestone_id=...)`.

## 3. Plan (software_engineer, plan_authoring skill)
- Write `PLAN.md` at the repo root with all required sections: problem statement (link #{{arguments}}),
  proposed change and the boundary it touches, target files, edge cases as observable outcomes,
  a 3–8 step red/green TDD breakdown (one commit each), STRIDE notes when input/auth/data/external
  surface is touched, and objectively checkable verification criteria.
- Record the design decision: `project-memory save_decision(title, rationale, outcome, author="software_engineer", branch="feature/<slug>")`.
- Show PLAN.md to the user before coding.

## 4. ADR evaluation (software_architect)
- Evaluate architectural significance against `docs/adrs/README.md` and the
  `architecture_decisions_in_project_memory` skill (new dependency/datastore, changed public
  contract or data model, cross-cutting pattern, quality-attribute trade-off, hard to reverse).
- If significant: the `software_architect` subagent copies `docs/adrs/0000-adr-template.md` to
  `docs/adrs/NNNN-<slug>.md` (next number), fills the MADR sections, and records it with
  `project-memory save_decision(title="ADR-NNNN: ...", outcome="Status: Accepted\n...", author="software_architect", branch="feature/<slug>")`.
- If not significant: state that explicitly (you will repeat it in the PR body).
- Either way the PR body will carry exactly one canonical, machine-checked
  line (`scripts/check-adr-gate.py` fails CI otherwise):
  `ADR: docs/adrs/NNNN-<slug>.md` when a record was written, or
  `ADR: not warranted — <reason>` when the checklist did not trip.

## 5. Choose the implementation mode, then implement (software_engineer)
- Before writing any production or test code, ask how this issue should be implemented,
  using the enumerated-options style from `docs/solomon-workflow.md`:
  1. **Automatic** — the agent implements it now via the TDD loop below (recommended).
  2. **Manual** — a developer implements it by hand.
  3. **Other** — free-form answer.
  Do not create or modify any file inside the PLAN.md target-files fence until a mode is chosen.
  Print the chosen mode as `Implementation mode: <Automatic|Manual> (selected)`.
- Non-interactive runs (the headless `solomon-harness dev start`, where there is no one to
  answer): do not block on the prompt. Default to Automatic and print
  `Implementation mode: Automatic (non-interactive default)` before the loop, so CI never hangs
  on stdin and the mode used is visible in the run output.

- **Automatic mode** — run the loop per PLAN.md step: write the failing test (Red), minimal code
  to pass (Green), refactor on green. Commit each step with a Conventional Commits message that
  references the issue (end the body with `Refs #{{arguments}}`) for bidirectional tracking; the
  commit-msg hook enforces format and bans emojis. Keep the diff inside the PLAN.md target-files
  fence; re-plan if it strays. Then continue to step 6.

- **Discovered-problem protocol** (see the section of that name in `docs/solomon-workflow.md`) —
  implementation routinely surfaces a *different* problem: an unrelated defect, a better approach,
  a missing test, a refactor worth doing. File it as a NEW issue (`/solomon-bug` for a defect,
  `/solomon-issue` for a feature/improvement, a `type:chore` for cleanup) whose body links this one
  with `Refs #{{arguments}}`. Never append the discovery as a comment on issue #{{arguments}}, and never
  silently widen this change beyond the PLAN.md target-files fence. If the discovery blocks #{{arguments}},
  stop and present the choice to the user as enumerated options (file-and-continue, file-and-switch,
  Other) — do not rescope unilaterally; a headless run files the `Refs #{{arguments}}` issue, records the
  block in its report, and stops rather than expanding scope.

- **Manual mode** — do NOT write any production or test code and do NOT open a PR. Report, with
  concrete values, the worktree path, the branch `feature/<slug>`, and the PLAN.md path as the
  developer's starting point, plus the ADR decision from step 4. Leave the board card in
  `In Progress` (do not advance it to Code Review). Tell the developer: implement by hand using
  PLAN.md, then re-run `/solomon-start {{arguments}}` to open the draft PR and move to Code Review,
  or open the PR yourself and run `/solomon-review`. Checkpoint the choice with
  `project-memory save_session(session_id="start-{{arguments}}", agent_name="software_engineer", task="Manual implementation chosen for #{{arguments}}", messages=..., issues=[{{arguments}}])` and stop here. Skip step 6.

## 6. Draft PR, Code Review, handoff
- Confirm with the user, then push: `git push -u origin feature/<slug>`.
- Open a draft PR: `uv run python -I -m solomon_harness.cli github pr-create --draft --base develop --title "<conventional title>" --body "..."`.
  The body must contain `Closes #{{arguments}}`, summarize the change, and carry the
  canonical ADR line from step 4 — `ADR: docs/adrs/NNNN-<slug>.md` or
  `ADR: not warranted — <reason>` — which the CI ADR gate enforces verbatim.
- `uv run python -I -m solomon_harness.cli github set-status --issue {{arguments}} --status "Code Review"`.
- Write the start -> review handoff contract to `.agents/solomon/state/handoffs/issue-{{arguments}}-start-to-review.md`
  using the template in `docs/solomon-workflow.md`: the PR link, PLAN.md, the ADR decision, what changed,
  and how to verify (the test plan). Keep it compact — a summary plus pointers.
- `project-memory log_handoff(sender="software_engineer", recipient="qa", contract_type="pull_request", contract_path=".agents/solomon/state/handoffs/issue-{{arguments}}-start-to-review.md", status="open")`; keep the returned handoff id.
- `project-memory save_session(session_id="start-{{arguments}}", agent_name="software_engineer", task="Implement #{{arguments}}", messages=..., issues=[{{arguments}}])` to checkpoint; `issues` writes the worked_on edge so resume is a graph query, not a task-string parse (ADR-0018).
- `project-memory link_session_handoff(session_id="start-{{arguments}}", handoff_id=<the returned handoff id>)` to record the produced edge.
- Report the branch, PR URL, and ADR decision. Then continue directly into the Review
  stage for the PR you just opened — run the `/solomon-review` flow for it now, in this
  same run, without waiting for a new command. The review is part of the workflow, not a
  separate manual step; only the merge remains a human gate. A blocker verdict halts the
  chain and returns to the human — never fix and re-review inside the same run (ADR-0019).
  (Headless `dev start` chains identically: it builds its prompt from the same
  `the canonical `solomon-start` workflow`.)
