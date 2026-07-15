---
description: Capture a product idea as a discovery item — JTBD, opportunity, riskiest assumption — and file it in the Ideas column
argument-hint: <short description of the idea>
---

You are running `/solomon-idea`, the discovery-intake stage. This captures an
idea lightly: no build commitment, no implementation plan. The driving specialist
is **product_owner**.

First, read `docs/solomon-workflow.md` and follow its conventions exactly
(board columns, labels, the memory handoff contract). Then adopt the
product_owner agent and apply the `product_discovery_and_jtbd` skill — delegate
the shaping to the `product_owner` subagent through the host's native specialist-delegation mechanism.

Raw idea from the user: `{{arguments}}`

If `{{arguments}}` is empty, ask the user for the idea in one line and stop.

## Steps

1. **Shape the idea** (product_owner, discovery track — solution-free). Produce:
   - **Job-to-be-Done**: "When <situation>, I want to <motivation>, so I can
     <expected outcome>." Identify the core functional job. No solution language.
   - **Opportunity**: the unmet need/pain in the customer's words, plus the one
     measurable target outcome it would move (baseline + target window if known).
   - **Riskiest assumption**: the one to three leap-of-faith assumptions, each
     classified (desirability / viability / feasibility / usability / ethical).
   - **Evidence to promote**: the cheapest test (RAT) that would justify moving
     this to the backlog — the metric, the pass/fail threshold, and a decision date.
   Do not design a solution and do not plan implementation. This stays in discovery.

2. **Show the shaped idea to the user and confirm** before creating anything.
   Creating a GitHub issue is outward-facing; get an explicit go-ahead. On request,
   refine and re-show.

3. **Create the issue** using the Idea body template from the workflow doc. Ensure the
   standard labels exist first with `uv run python -m solomon_harness.github ensure-labels`:
   ```bash
   gh issue create --title "Idea: <concise title>" --label "type:idea" \
     --body "<JTBD / Opportunity / Riskiest assumption / Evidence to promote>"
   ```
   Capture the returned issue URL and number.

4. **Place it on the board** in the Ideas column:
   ```bash
   uv run python -m solomon_harness.github ensure-board
   uv run python -m solomon_harness.github set-status --issue <n> --status "Ideas"
   ```

5. **Persist to memory** per the handoff contract:
   - `log_issue(github_id=<n>, title="<title>", type_="idea", status="Ideas",
     milestone_id=null)`.
   - `save_decision(...)` only if a notable framing call was made (e.g. the chosen
     core job or the named riskiest assumption); otherwise skip.
   - **Hand off to refine.** Write the compact handoff contract to
     `.agents/solomon/state/handoffs/issue-<n>-idea-to-refine.md` using the template in
     `docs/solomon-workflow.md`, then call `log_handoff(sender="product_owner",
     recipient="refine", contract_type="idea",
     contract_path=".agents/solomon/state/handoffs/issue-<n>-idea-to-refine.md", status="open")`.

6. **Output the issue URL** and a one-line recap (JTBD + riskiest assumption).
   State explicitly that no implementation was planned and that promotion to the
   backlog requires the evidence defined in step 1 (via `/solomon-issue`). An idea is
   a pre-Definition-of-Ready discovery item by design: it carries no Acceptance
   Criteria, Definition of Ready, or Definition of Done yet, and only graduates to a
   Definition of Ready and a Definition of Done at refinement (`/solomon-refine`) once
   it is promoted to the backlog. Do not force a Definition of Ready onto a raw idea.

Present every decision, confirmation, and next-step choice through the host's native enumerable input mechanism, or as a numbered list ending in "Other" when structured input is unavailable — never as an open prose question or a command to copy. This is the non-negotiable Enumerable decisions rule in `agents/AGENTS.md`.
