---
description: Create a feature/story issue (INVEST + Given/When/Then) and place it on the board Backlog
argument-hint: <short feature description, or a path/link to context>
allowed-tools: Bash(gh:*), Bash(git:*), Bash(uv run:*), Task, Read, Write, Edit, mcp__solomon-memory__log_issue, mcp__solomon-memory__save_decision, mcp__solomon-memory__log_handoff
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

2. Shape the issue body (use the Feature/story template in the conventions doc).
   Produce, in this order:
   - **Problem statement** — the user need and why it matters. No solutioning.
   - **User story** — `As a <real persona>, I want <capability> so that <outcome>`,
     passing INVEST (vertical slice, one sprint, estimable, testable).
   - **Acceptance criteria** — Gherkin `Scenario / Given / When / Then`, covering
     the happy path, boundary values, and at least one failure path. Every `Then`
     observable and specific (exact counts, limits, timeouts, error codes).
   - **Scope** and **Out of scope** — an explicit out-of-scope list.
   - **Definition of Ready** — INVEST met, AC present, dependencies/assumptions
     with owners, non-functional constraints stated with numbers, sized by eng.

3. Choose labels: `type:feature` plus a priority (`priority:p0|p1|p2`, justified
   with a named method — MoSCoW or RICE, show the inputs) and an `area:<domain>`.

4. Confirm before creating. Show the user the rendered body, labels, and title
   (conventional, concise). Proceed only on explicit approval — issue creation is
   an outward-facing action.

5. Create the issue:
   - Ensure the standard labels exist first: `uv run python -m solomon_harness.github ensure-labels`.
     If you use a new `area:<domain>`, create it: `gh label create "area:<domain>" --color BFD4F2 --force`.
   - `gh issue create --title "<title>" --body "<body>" --label type:feature --label priority:pN --label area:<domain>`.
   Capture the returned issue number and URL.

6. Place it on the board Backlog:
   - `uv run python -m solomon_harness.github ensure-board`
   - `uv run python -m solomon_harness.github set-status --issue <n> --status "Backlog"`

7. Persist to memory per the handoff contract:
   - `mcp__solomon-memory__log_issue` (github_id=<n>, title, type_="feature",
     status="Backlog", milestone_id if known).
   - `mcp__solomon-memory__save_decision` — record the product decision (title,
     rationale = the problem and prioritization inputs, outcome = "story created
     and backlogged", author="product_owner").
   - Write the handoff contract to `.solomon/handoffs/issue-<n>-issue-to-refine.md`
     using the contract template in the conventions doc (`.solomon/` is gitignored
     local state).
   - `mcp__solomon-memory__log_handoff` — product_owner → scrum_master, contract
     "feature-story", contract_path = that handoff file, status="ready_for_refinement".

8. Output the issue URL and a one-line summary (number, title, priority, area).
   Note that the next stage is `/solomon-refine` to move it `Backlog → Ready`.
