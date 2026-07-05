# PLAN.md: feat(memory): living project memory — scan structure/architecture at loop start, refresh on handoff and delivery

Problem statement:
The harness lacks a continuously updated "living" project memory. The current codebase index only stores raw file content, and the code overview is just a file-type histogram. These snapshots are only refreshed on `init` and `/solomon-release`, rather than dynamically when a session starts, when the loop starts, or when a stage handoff occurs. Consequently, agents and the loop reason from outdated project structures. We need to implement dynamic codebase scanning/indexing, idempotent skips when the codebase is unchanged, incremental updates, handoff-triggered refreshes, delivery evolution logging, and loop proposal integration.

Proposed changes:
1. **Project structure scanner**: Implement `scan_project_structure(workspace_root, db)` in `solomon_harness/bootstrap.py`. It will serialize top-level layout, stack/frameworks, entry points, modules and local dependencies, test layout, and patterns (ADRs, agents, commands). It will save this under `__project_structure__` in category `project_model` along with `manifest_signature` and a UTC timestamp.
2. **Idempotent skip & Incremental delta**: Check if `manifest_signature` (SHA256 of `__code_index_manifest__` content) matches the saved record. If yes, skip the scan. If no, scan and update.
3. **Session start trigger**: Call `scan_project_structure` inside `handle_run` in `solomon_harness/cli.py` on session start.
4. **Loop/Stage start trigger**: Call `scan_project_structure` inside `run_stage` in `solomon_harness/workflows.py` before running stages.
5. **Handoff trigger**: In `log_handoff` inside `solomon_harness/tools/database_client.py`, run `index_codebase` followed by `scan_project_structure`.
6. **Delivery evolution & refresh**: In `save_release` inside `solomon_harness/tools/database_client.py`, append an evolution entry (issue number, title, version, date) under key `__project_evolution__` and refresh the project structure record.
7. **Loop proposal integration**: Update `.claude/commands/solomon-workflow.md` and `.claude/commands/solomon-loop.md` to request/read `__project_structure__` and `__project_evolution__` from memory and factor it into the proposed next-step rationale. Flag discrepancies if the model is stale vs. the code.
8. **Failure path safety**: Wrap all triggers and the scanner in try-except blocks so any backend/scan failure logs a single warning and never blocks the execution.

Target files:
- `solomon_harness/bootstrap.py`
- `solomon_harness/cli.py`
- `solomon_harness/workflows.py`
- `solomon_harness/tools/database_client.py`
- `.claude/commands/solomon-workflow.md`
- `.claude/commands/solomon-loop.md`

Edge cases:
- Missing database or network failure during scan: wrapped in try-except, fails safe with a single warning and does not write partial/corrupt state.
- Empty manifest: will trigger initial `index_codebase` to build the manifest before scanning.
- Import cycles: keep import statements inside functions rather than at the top of database_client.py.

TDD breakdown:
1. **Red**: Write a unit test `tests/test_project_structure.py` verifying that `scan_project_structure` saves a valid JSON project structure with timestamp and manifest signature under `__project_structure__` and skips scanning when the manifest matches.
2. **Green**: Implement `scan_project_structure` in `solomon_harness/bootstrap.py`.
3. **Red**: Add test assertions verifying incremental update on file change and failure safety (best-effort, non-blocking on database/file errors).
4. **Green**: Implement incremental updates and error boundaries in the scanner.
5. **Red**: Write unit tests verifying that calling `log_handoff` and `save_release` trigger a project structure scan and that `save_release` writes to `__project_evolution__`.
6. **Green**: Implement the triggers in `log_handoff` and `save_release` inside `solomon_harness/tools/database_client.py`.
7. **Refactor & Integration**: Update triggers in `cli.py` and `workflows.py`, update prompt command files, verify that all test suites pass.

STRIDE notes:
- Input validation: the keys and paths are verified to be inside the repository root.
- Information disclosure: error messages on failed database writes or scans are logged by exception type to prevent leaking internal database schemas or system configurations.

Verification criteria:
- Run `uv run pytest tests/test_project_structure.py` to verify functionality.
- Run `uv run pytest` to ensure no regressions in existing tests.
