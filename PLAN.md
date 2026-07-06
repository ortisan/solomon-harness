# PLAN.md: feat(agents): wire broker into refine/start with the propose/approve/apply loop

Problem statement:
Issue #50 requires wiring the routing core (capability broker) into the delivery lifecycle. Gap detection and acquisition must be folded into `/solomon-refine` and `/solomon-start`, and the loop must surface the gap as the next proposed step. When the broker is applied (via #20's reviewed-PR path), it must record the design decision using `save_decision` and a `log_handoff` contract when memory is available. The "propose" step runs only when invoked (no unattended/autonomous cadence), and verdicts must be presented as enumerated choices (with "Other" option).

## Proposed changes

1. **Broker Memory Integration (`solomon_harness/curator.py`)**:
   - Update `broker_skill` and `broker_agent` signatures to accept an optional `issue_id: Optional[str] = None` argument.
   - Update `Proposal` mapping to set `decision_id = issue_id` (so it flows to git commits and PR descriptions).
   - In `apply_proposal`, after a draft PR is successfully created:
     - Instantiate `DatabaseClient` using the workspace root.
     - Call `db.log_decision` to record the broker decision.
     - If `proposal.decision_id` (the issue ID) is present, write a handoff contract file `.solomon/handoffs/issue-<issue_id>-start-to-review.md` and call `db.log_handoff` to create a `pull_request` handoff.

2. **Workflow Prompt Integration**:
   - **`.claude/commands/solomon-refine.md`** & **`.gemini/commands/solomon-refine.toml`**:
     - Instruct the agent to run a capability check against the discovered agents.
     - If the issue requires a missing capability, run the capability router, present the route/gap verdict as enumerated choices (e.g. 1. Invoke broker to adapt skill, 2. Other).
     - If selected, execute the broker via python command (passing workspace root and issue number), and stop refinement.
   - **`.claude/commands/solomon-start.md`** & **`.gemini/commands/solomon-start.toml`**:
     - Check if the target agent/capability is missing. If so, present route/gap verdict as enumerated choices.
     - If confirmed, execute the broker via python, log the decision/handoff, and stop development.
   - **`.claude/commands/solomon-workflow.md`** & **`.gemini/commands/solomon-workflow.toml`**:
     - Under "Decide the next step", add a rule: if an issue has a capability gap or pending broker proposal, recommend `/solomon-start <issue>` or `/solomon-refine <issue>` (which will run the broker).

3. **Acquisition / Verification Tests (`tests/test_curator.py`)**:
   - Add a test checking that `broker_skill` and `broker_agent` record decisions and handoffs correctly in memory.

## Target files
- `solomon_harness/curator.py`
- `.claude/commands/solomon-refine.md`
- `.claude/commands/solomon-start.md`
- `.claude/commands/solomon-workflow.md`
- `.gemini/commands/solomon-refine.toml`
- `.gemini/commands/solomon-start.toml`
- `.gemini/commands/solomon-workflow.toml`
- `tests/test_curator.py`

## STRIDE Security Considerations
- **Information Disclosure**: Handoff contracts and PRs must not contain PII or secrets. PII is minimized by using normalized person keys.
- **Elevation of Privilege**: Fetches must use allowed sources from `skill-sources.json`, and the quarantine logic blocks scripts/executables.
- **Tampering**: The single-driver lock protects database operations, and all acquisitions land as draft PRs reviewed by humans.

## Edge cases
- Database/memory service is offline or not configured: wrapped inside try-except blocks so failures to write memory do not block delivery.
- Empty or invalid `issue_id`: handle gracefully (do not write handoff files).

## TDD breakdown
1. **Red**: Add tests in `tests/test_curator.py` verifying that broker calls with an `issue_id` write a handoff contract file and record the decision and handoff in memory.
2. **Green**: Implement database logging and handoff contract file writing in `apply_proposal` in `solomon_harness/curator.py`.
3. **Refactor**: Verify all existing tests pass and refine database client usage.
4. **Integration**: Update workflow/command markdown and toml templates.

## Verification criteria
- Run `uv run pytest` to ensure all tests pass (including the new TDD tests).
- Validate the new command file formatting.
