---
description: Refine a backlog issue to Ready — sharpen acceptance criteria, slice, add DoR, estimate, and RAID
argument-hint: [issue-number] (optional refinement notes)
allowed-tools: Bash(gh:*), Bash(git:*), Bash(uv run:*), Task, Read, Edit, Write, mcp__solomon-memory__log_issue, mcp__solomon-memory__save_decision, mcp__solomon-memory__log_handoff, mcp__solomon-memory__save_session, mcp__solomon-memory__get_latest_activity
---

Read `docs/solomon-workflow.md` and follow it exactly. This is the refinement
stage: drive it as the **product_owner** (acceptance criteria, slicing, scope,
Definition of Ready) with the **scrum_master** (estimate, RAID, board, handoff).
Delegate the heavy authoring to the `product_owner` and `scrum_master` subagents
via the Task tool; load their skills first.

Input: `$ARGUMENTS` = the issue number, plus any optional refinement notes.

Steps:

1. Resume context: call `mcp__solomon-memory__get_latest_activity` and
   `gh issue view <n> --comments` to read the current issue, labels, and milestone.
   Read the latest incoming handoff contract it returns (its `contract_path`) first
   and treat it as the bounded input — open the artifacts it points to (the issue,
   any prior contract) only when needed, instead of re-deriving prior context.
   Confirm it is in `Backlog`; if it is already `Ready` or further, stop and report.

2. Strengthen the issue body (product_owner). Rewrite to the feature template in
   the workflow doc: problem statement, user story (`As a … I want … so that …`),
   and acceptance criteria as **Given/When/Then** covering happy, boundary, and
   failure paths. Pull in any non-functional constraints with concrete numbers and
   attribute them to the owning specialist.

3. Slice into thin vertical increments (product_owner). If the issue is too large
   to finish in one sprint, propose child issues — each independently shippable and
   testable. List the proposed split and **confirm with the user before creating**
   any sub-issues. On approval, `gh issue create` each child with `type:feature`,
   the matching `priority:*` / `area:*` labels, the same milestone, and a
   `Parent: #<n>` line; track sub-issues back in the parent body.

4. Add a Definition of Ready checklist and a rough estimate (scrum_master): INVEST
   check, testable acceptance criteria, dependencies/assumptions with owners,
   non-functional numbers stated, and an engineering size (story points or t-shirt).

5. Map dependencies and risks as a RAID block (scrum_master): Risks (5x5
   probability×impact with response + owner), Assumptions (validation owner +
   check-by date), Issues (blockers now), Dependencies (direction + FS/SS/FF/SF,
   flag cross-team/external). For each medium-or-higher risk and each external
   dependency, `mcp__solomon-memory__log_issue` a tracked entry labelled
   `risk` / `dependency` so `get_open_issues` mirrors the RAID.

6. Apply the update: `gh issue edit <n> --body-file <tmp>` (write the refined body
   to the scratchpad first, do not paste a giant inline string). Re-confirm labels
   and milestone are correct.

7. Move the board card `Backlog` → `Ready`:
   - `uv run python -m solomon_harness.github ensure-board`
   - `uv run python -m solomon_harness.github set-status --issue <n> --status "Ready"`

8. Persist the handoff contract:
   - `mcp__solomon-memory__log_issue` to update the refined issue's status.
   - `mcp__solomon-memory__save_decision` recording the refinement outcome
     (slicing decision, estimate, accepted risks) with rationale and author
     `product_owner`.
   - Write the compact handoff contract to
     `.solomon/handoffs/issue-<n>-refine-to-start.md` using the template in
     `docs/solomon-workflow.md`, then `mcp__solomon-memory__log_handoff` sender
     `product_owner` recipient `software_engineer` (engineering), `contract_type`
     `prd`, `contract_path` set to that file, `status` `pending` (gate: every story
     has testable acceptance criteria, an estimate, and DoR met).
   - `mcp__solomon-memory__save_session` to checkpoint under `<feat>/refine`.

Report the refined issue link, any sub-issues created, the estimate, the RAID
summary, and the new board status. Do not run outward-facing `gh` writes or push
without the user's go-ahead; never touch a protected branch.
