---
description: Create a feature/story issue (INVEST + Given/When/Then) and place it on the board Backlog
argument-hint: <short feature description, or a path/link to context>
allowed-tools: Bash(gh:*), Bash(git:*), Bash(uv run:*), Task, Read, Write, Edit, mcp__solomon-memory__log_issue, mcp__solomon-memory__save_decision, mcp__solomon-memory__log_handoff, mcp__solomon-memory__save_session, mcp__solomon-memory__link_session_handoff
---

Read `docs/solomon-workflow.md` and follow it exactly: this is the "Create a
feature/story" stage, board move `→ Backlog`. Adopt the **product_owner** agent;
for non-trivial shaping delegate to the product_owner subagent via the Task tool
(roadmapping, requirements_traceability, acceptance_criteria_given_when_then).
Read its skills under `agents/product_owner/skills/` before writing.

Feature request from the user: $ARGUMENTS

Steps:

1. Resume context. Call `mcp__solomon-memory__get_latest_activity` and
   `gh issue list --state open` to avoid duplicating an existing story. If this
   request duplicates one, stop and point the user to it.

2. Elicitation gate (see "Elicitation gate" in `docs/solomon-workflow.md` and
   the product_owner `socratic_elicitation` skill). Evaluate the demand against
   the six readiness criteria — the explicit doubt-detection checklist:
   **Problem** (the pain and why now), **Persona** (a real user type, never
   "the user"), **Outcome** (the observable change that means success),
   **Boundary** (at least one scope limit or constraint), **Single reading**
   (no two conflicting interpretations of comparable plausibility), and
   **Job behind the solution** (a solution-phrased demand also states the
   underlying need). Then:
   - All six hold: skip questioning entirely and carry the line
     `Elicitation: skipped — all 6 readiness criteria met` in the issue body.
   - Any criterion fails: enter Socratic mode. Ask via AskUserQuestion,
     at most 4 questions per round, one per failed criterion and
     only for failed criteria — never re-ask one already satisfied — for
     at most 3 rounds, then proceed to shaping. An empty demand starts from
     the job-to-be-done question. Record which criteria failed in the issue
     body's elicitation line.
   - The user declines (an "Other" answer such as "just file it"): stop
     eliciting immediately and record each unanswered criterion under an
     `Assumptions (unelicited)` heading in the issue body.
   - Non-interactive/headless runs never block: ask nothing, print
     `Elicitation: skipped (non-interactive)`, and record unmet criteria as
     assumptions exactly as in the decline path.
   Fold every elicited answer into the context and user story below.
   The gate changes only how the demand is understood; the confirm-before-create
   step below is untouched.

3. Shape the issue body (use the Feature/story template in the conventions doc).
   Produce, in this order:
   - **Context** — the user need and why it matters. No solutioning.
   - **User story** — `As a <real persona>, I want <capability> so that <outcome>`,
     passing INVEST (vertical slice, one sprint, estimable, testable).
   - **Acceptance criteria** — Gherkin `Scenario / Given / When / Then`, covering
     the happy path, boundary values, and at least one failure path. Every `Then`
     observable and specific (exact counts, limits, timeouts, error codes).
   - **Scope** and **Out of scope** — an explicit out-of-scope list.
   - **Definition of Ready** — INVEST met, AC present, dependencies/assumptions
     with owners, non-functional constraints stated with numbers, sized by eng.
   - **Definition of Done** — the conditions that close the story: every acceptance
     criterion demonstrably met with covering tests, code reviewed and merged with CI
     green, and docs updated. `/solomon-review` and `/solomon-release` enforce it as
     the close gate.

4. Choose labels: `type:feature` plus a priority (`priority:p0|p1|p2`, justified
   with a named method — MoSCoW or RICE, show the inputs) and an `area:<domain>`.

5. Confirm before creating. Show the user the rendered body, labels, and title
   (conventional, concise). Proceed only on explicit approval — issue creation is
   an outward-facing action.

6. Create the issue:
   - Ensure the standard labels exist first: `uv run python -m solomon_harness.github ensure-labels`.
     If you use a new `area:<domain>`, create it: `gh label create "area:<domain>" --color BFD4F2 --force`.
   - `gh issue create --title "<title>" --body "<body>" --label type:feature --label priority:pN --label area:<domain>`.
   Capture the returned issue number and URL.

7. Place it on the board Backlog:
   - `uv run python -m solomon_harness.github ensure-board`
   - `uv run python -m solomon_harness.github set-status --issue <n> --status "Backlog"`

8. Generate the spec document (#221 S1; see "Spec generation" in
   `docs/solomon-workflow.md`). Copy `docs/specs/0000-spec-template.md` to
   `docs/specs/<N>-<slug>.md` with the Write tool — `<N>` = the created issue
   number with no leading zeros, `<slug>` = the kebab-case title reduced to
   ASCII lowercase `[a-z0-9]` and single hyphens, everything else stripped.
   Pre-fill from the shaped body: the elicitation trace into the spec's Context, the
   issue's Context section (the need and why) into the spec's Problem, the scope into Requirements, the Gherkin
   into Acceptance Criteria, the house rules that bound the solution
   (architecture style, security posture, conventions) into
   Design Constraints, the out-of-scope list into Out of Scope, and
   Traceability citing issue `#<N>` and any related ADR. Any section without content
   carries the explicit placeholder `TBD (refine)`. Run
   `uv run python scripts/spec-lint.py docs/specs/<N>-<slug>.md` and fix until
   it exits 0. The spec ships with the issue's first implementation PR —
   never pushed to a protected branch directly.

9. Persist to memory per the handoff contract:
   - `mcp__solomon-memory__log_issue` (github_id=<n>, title, type_="feature",
     status="Backlog", milestone_id if known).
   - `mcp__solomon-memory__save_decision` — record the product decision (title,
     rationale = the problem and prioritization inputs, outcome = "story created
     and backlogged", author="product_owner").
   - Write the handoff contract to `.solomon/handoffs/issue-<n>-issue-to-refine.md`
     using the contract template in the conventions doc (`.solomon/` is gitignored
     local state).
   - `mcp__solomon-memory__log_handoff` — product_owner → scrum_master, contract
     "feature-story", contract_path = that handoff file, status="open";
     keep the returned handoff id.
   - `mcp__solomon-memory__save_session` (session_id="issue-<n>",
     agent_name="product_owner", task="Filed #<n>", messages=[], issues=[<n>]) to
     checkpoint with the worked_on edge, then
     `mcp__solomon-memory__link_session_handoff(session_id="issue-<n>", handoff_id=<the returned handoff id>)`
     to record the produced edge (ADR-0018).

10. Output the issue URL and a one-line summary (number, title, priority, area).
    Note that the next stage is `/solomon-refine` to move it `Backlog → Ready`.

Present every decision, confirmation, and next-step choice to the user as enumerated options (AskUserQuestion in Claude Code; a numbered list ending in "Other" in the Gemini CLI) — never an open prose question or a command to copy. This is the non-negotiable Enumerable decisions rule in `agents/AGENTS.md`.
