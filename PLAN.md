# Plan: feat(agents): practice_curator — fleet sweep emitting one bounded proposal per agent

- Issue: #19 https://github.com/ortisan/solomon-harness/issues/19
- Branch: feature/practice-curator-fleet-sweep

## Problem Statement
Implement a fleet-sweep mechanism for the `practice_curator` agent. It must compare the best-practice baseline (e.g. from its `sourcing_the_state_of_the_art.md` skill) against all existing agents in the fleet and identify/report any drift in their skills or profiles, without making any file changes directly. It must emit exactly one bounded proposal per affected agent, backed by at least 2 dated and credible sources.

## Proposed Change
1. Implement a `sweep_fleet` or `sweep` method in the `practice_curator` agent or code.
   Since `capability_router.py` exists in `solomon_harness/` for Slice A of curator capability-broker, we will put the sweep logic in `solomon_harness/curator.py`.
2. The sweep logic:
   - Iterate over all agents in the fleet (using `discover_agents`).
   - For each agent, analyze their skills or profile against the best-practice baseline.
   - The analysis itself is a match process. To keep the core testable and deterministic (similar to `capability_router.py`), we will inject a `sweep_analyzer` port (Matcher/Callable). In production, this is driven by the host LLM; in tests, by a deterministic stub.
   - For each affected agent with drift:
     - Generate a proposal carrying >= 2 dated, credible sources.
     - Record the proposal with `db.log_decision` in project memory.
     - Emit the proposal (or file it as a `/solomon-issue` or print it).
     - If the drift is backed by fewer than 2 dated sources, do not emit it as a proposal, but list it under "needs evidence" in the sweep summary.
   - The sweep process must remain strictly read-only: no files under any `agents/<name>/` directory can be modified.
   - Each proposal must target exactly one agent.

## Target Files
- `solomon_harness/curator.py`
- `tests/test_curator.py`
- `agents/practice_curator/skills/auditing_delivered_work.md` (check/deepen safety guidance if needed)
- `agents/practice_curator/skills/sourcing_the_state_of_the_art.md` (check/deepen safety guidance if needed)

## Edge Cases & STRIDE
- Banned edit: Verify that the sweep modifies no agent files.
- Insufficient sources: If a drift has < 2 sources, it is not filed but listed as "needs evidence".
- Single agent target: Ensure each proposal only targets a single agent.
- STRIDE: No input validation required since it is a local tool, but we must protect against writing to arbitrary file paths or executing untrusted scripts.

## TDD Loop Breakdown
1. **Step 1 (Red)**: Write unit tests in `tests/test_curator.py` asserting that the sweep iterates all agents, identifies drift, rejects drifts with < 2 sources (listing them under "needs evidence"), and emits exactly one proposal per affected agent, recording each with `save_decision`.
2. **Step 2 (Green)**: Implement the sweep core in `solomon_harness/curator.py` to make the tests pass.
3. **Step 3 (Refactor)**: Clean up `solomon_harness/curator.py` and ensure the code is modular and clean.
4. **Step 4 (Red)**: Write a test asserting that the sweep never modifies any files in the workspace.
5. **Step 5 (Green)**: Ensure the sweep only reads and performs no writes on files.
6. **Step 6 (Verify)**: Run the full test suite and verify that the `practice_curator` tests pass.

## Verification Criteria
- `uv run python -m unittest discover -s tests` passes.
- All new tests in `tests/test_curator.py` pass.
