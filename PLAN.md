# Plan - loop_policy human-gate merge/release enforcement (#183)

## Problem Statement
The default unconfigured `human` autonomy level allows the permanently human-gated `release` stage (and potentially other future gated stages) to execute. The policy layer should enforce that permanently human-gated stages (e.g., `release`) are always blocked, regardless of the configured autonomy level.
Refs #183.

## Proposed Change and Boundary
- In `solomon_harness/loop_policy.py`, reorder the checks inside `LoopPolicy.decide_stage` to run the `stage in HUMAN_GATED_STAGES` check before checking if `self.level == "human"`.
- This ensures that human-gated stages are checked and rejected first, before allowing unrestricted actions under the `"human"` autonomy level.
- Non-gated stages (like `review` or `start`) must remain unaffected and allowed under the `"human"` level.

## Target Files
- `solomon_harness/loop_policy.py`

## Edge Cases as Observable Outcomes
1. Stage `release` (in `HUMAN_GATED_STAGES`) is called when autonomy is `human`. Result: Rejected with explanation.
2. Stage `review` (not in `HUMAN_GATED_STAGES`) is called when autonomy is `human`. Result: Allowed.
3. Stage `release` is called when autonomy is `L1`/`L2`/`L3`. Result: Rejected.
4. Stage `review` is called when autonomy is `L2`/`L3`. Result: Allowed.

## TDD Step Breakdown

### Step 1: Red (failing tests for the bug)
Modify `tests/test_loop_policy.py` to assert that:
- `release` is blocked under autonomy level `"human"`.
- `review` is allowed under autonomy level `"human"`.
This step should fail because today `release` is allowed under `"human"`.
Commit message: `test(workflow): add failing regression tests for human-level release gate`

### Step 2: Green (fix the bug)
Reorder checks in `solomon_harness/loop_policy.py` so `HUMAN_GATED_STAGES` is checked before `self.level == "human"`.
Verify tests pass.
Commit message: `fix(workflow): check permanently human-gated stages before human autonomy early-return`

### Step 3: Refactor (clean up/polish)
Ensure code is well-formatted and docstrings are accurate. No logical changes.
Commit message: `refactor(workflow): clean up decide_stage comments and formatting`

## STRIDE Threat Notes
- **Elevation of Privilege**: This fix mitigates potential elevation of privilege where a client running unattended loop commands at the default `human` level could inadvertently run a release stage. By locking this down in python-enforced policy, we avoid privilege escalation.
- **T/I/D/E**: No direct input validation or data serialization changes.

## Verification Criteria
- Run `uv run pytest tests/test_loop_policy.py` and ensure all tests pass.
- Run `uv run python -m solomon_harness.cli loop-policy` to view status.
