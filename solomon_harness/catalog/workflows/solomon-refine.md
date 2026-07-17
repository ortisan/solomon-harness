---
description: Refine a backlog issue to Ready — sharpen acceptance criteria, slice, add DoR, estimate, and RAID
argument-hint: [issue-number] (optional refinement notes)
---

Read `docs/solomon-workflow.md` and follow it exactly. This is the refinement
stage: drive it as the **product_owner** (acceptance criteria, slicing, scope,
Definition of Ready) with the **scrum_master** (estimate, RAID, board, handoff).
Delegate the heavy authoring to the `product_owner` and `scrum_master` subagents
through the host's native specialist-delegation mechanism; load their skills first.

Input: `{{arguments}}` = the issue number, plus any optional refinement notes.

Steps:

1. Resume context: call `project-memory get_latest_activity` and
   `gh issue view <n> --comments` to read the current issue, labels, and milestone.
   Read the latest incoming handoff contract it returns (its `contract_path`) first
   and treat it as the bounded input — open the artifacts it points to (the issue,
   any prior contract) only when needed, instead of re-deriving prior context.
   Confirm it is in `Backlog`; if it is already `Ready` or further, stop and report.

1b. **Capability Check** (see "Capability check" in `docs/solomon-workflow.md`):
    Before starting refinement, verify the project has the capability (agent +
    skills) this issue needs. The deterministic router core builds the verdict
    (ADR-0008); you supply the match judgment as data — never build inline
    Python over issue text.
    - Write your demand and match judgment to `.agents/solomon/state/broker/route-<issue_number>.json`
      with the host's file-write mechanism (so issue-derived text never touches a shell string):
      `{"demand": "<one-line capability demand>", "match": {"agent": <name or null>, "rationale": "<why>", "alternatives": [], "missing_capability": <text or null>, "nearest_agent": <name or null>}}`
    - Run `uv run python -I -m solomon_harness.cli broker route --file .agents/solomon/state/broker/route-<issue_number>.json`
      and read the verdict JSON. The core validates the match against the
      catalog and fails closed (exit 3) on an empty catalog or a
      matcher-contract violation.
    - Route verdict: note the routed agent and continue the refinement.
    - Gap verdict, interactive session: present the choice through the host's native enumerable input mechanism:
      1. Acquire the capability via the broker (recommended) — adapt the named
         skill into the nearest agent, or create the suggested agent.
      2. Proceed without acquiring (the gap stays recorded).
      3. Other.
      On option 1, write the proposal to `.agents/solomon/state/broker/proposal-<issue_number>.json`
      (`{"kind": "adapt_skill", "source_name": "...", "skill_name": "...", "agent_name": "...", "issue": "<issue_number>"}` or
      `{"kind": "create_agent", "agent_name": "...", "title": "...", "description": "...", "duties": ["..."], "issue": "<issue_number>"}`),
      then run `uv run python -I -m solomon_harness.cli broker apply --file .agents/solomon/state/broker/proposal-<issue_number>.json`.
      Read the result JSON and stop execution (do not proceed to Step 2):
      - `adapt_skill` returns `mode: reviewed_pr`; report its `pr_url`.
      - `create_agent` returns `mode: direct_registration`; report its `agent_path`,
        confirm that native adapters were compiled, and tell the user that
        `restart_required: true` means a new session is needed to load the agent.
    - Gap verdict, non-interactive/headless run: acquisition is human-gated and
      `broker apply` refuses it (exit 3) — do not attempt it. Record the gap
      verdict in the run report and continue the refinement without acquiring.

2. Strengthen the issue body (product_owner). Rewrite to the feature template in
   the workflow doc: context, user story (`As a … I want … so that …`),
   and acceptance criteria as **Given/When/Then** covering happy, boundary, and
   failure paths. Pull in any non-functional constraints with concrete numbers and
   attribute them to the owning specialist.

2b. Make the spec implementation-ready (software_engineer + software_architect;
    see "Spec generation" in `docs/solomon-workflow.md`). Refinement is the gate
    where the spec stops being a product sketch and becomes something a model can
    implement without asking. Open the issue's spec `docs/specs/<n>-<slug>.md`
    (created at `/solomon-issue`) and resolve **every** `TBD (refine)`:
    - **Implementation Pointers** — read the code and state the exact `file:line`
      targets the change touches, the current behavior versus the expected
      behavior at each, and the concrete approach. No guessing left for the
      implementer.
    - **Verification** — the exact command(s) that prove the change works (the
      test invocation, a manual repro, the check to eyeball).
    - Fill any other section still on a placeholder, then flip the header to
      `Status: ready`.
    - Run `uv run python -I scripts/spec-lint.py docs/specs/<n>-<slug>.md` and fix
      until it exits 0. Once `Status: ready`, the linter rejects any remaining
      `TBD (refine)` line — this is the mechanical Ready gate; do not move the
      board card to Ready while it fails.
    - If no spec exists (an issue filed before the spec system, or a bug — bugs
      carry the same detail in their issue body via `/solomon-bug`), enforce the
      same bar in the issue body: suspected `file:line`, current vs expected, and
      the verification command.

3. Slice into thin vertical increments (product_owner). If the issue is too large
   to finish in one sprint, propose child issues — each independently shippable and
   testable. List the proposed split and **confirm with the user before creating**
   any sub-issues. On approval, `gh issue create` each child with `type:feature`,
   the matching `priority:*` / `area:*` labels, the same milestone, and a
   `Parent: #<n>` line; track sub-issues back in the parent body.

4. Add a Definition of Ready checklist and a rough estimate (scrum_master): INVEST
   check, testable acceptance criteria, the spec is implementation-ready
   (Implementation Pointers resolved to real `file:line`, Verification command
   stated, `Status: ready`, `spec-lint.py` green), dependencies/assumptions with
   owners, non-functional numbers stated, and an engineering size (story points
   or t-shirt).
   Also state the issue's **Definition of Done** — the conditions that close it
   (every acceptance criterion met with covering tests, reviewed and merged with CI
   green, docs updated) — which `/solomon-review` and `/solomon-release` enforce as
   the close gate.

5. Map dependencies and risks as a RAID block (scrum_master): Risks (5x5
   probability×impact with response + owner), Assumptions (validation owner +
   check-by date), Issues (blockers now), Dependencies (direction + FS/SS/FF/SF,
   flag cross-team/external). For each medium-or-higher risk and each external
   dependency, `project-memory log_issue` a tracked entry labelled
   `risk` / `dependency` so `get_open_issues` mirrors the RAID.

6. Apply the update: `gh issue edit <n> --body-file <tmp>` (write the refined body
   to the scratchpad first, do not paste a giant inline string). Re-confirm labels
   and milestone are correct.

7. Move the board card `Backlog` → `Ready`:
   - `uv run python -I -m solomon_harness.github ensure-board`
   - `uv run python -I -m solomon_harness.github set-status --issue <n> --status "Ready"`

8. Persist the handoff contract:
   - `project-memory log_issue` to update the refined issue's status.
   - `project-memory save_decision` recording the refinement outcome
     (slicing decision, estimate, accepted risks) with rationale and author
     `product_owner`.
   - Write the compact handoff contract to
     `.agents/solomon/state/handoffs/issue-<n>-refine-to-start.md` using the template in
     `docs/solomon-workflow.md`, then `project-memory log_handoff` sender
     `product_owner` recipient `software_engineer` (engineering), `contract_type`
     `prd`, `contract_path` set to that file, `status` `pending` (gate: every story
     has testable acceptance criteria, an estimate, and DoR met).
   - `project-memory save_session` to checkpoint under `<feat>/refine`.

Report the refined issue link, any sub-issues created, the estimate, the RAID
summary, and the new board status. Do not run outward-facing `gh` writes or push
without the user's go-ahead; never touch a protected branch.

Present every decision, confirmation, and next-step choice through the host's native enumerable input mechanism, or as a numbered list ending in "Other" when structured input is unavailable — never as an open prose question or a command to copy. This is the non-negotiable Enumerable decisions rule in `agents/AGENTS.md`.
