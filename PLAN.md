# Plan - Solomon Harness Task 3: Reorganize and Clean Up Agent Files

This plan outlines the design, implementation, and verification steps for Task 3: Reorganizing the agent files into their compiled directories and cleaning up duplicates.

## Requirements

1. **Reorganize files via Compiler**:
   - Update `scripts/compile-harnesses.py` to support agent discovery from both flat markdown files (e.g., `agents/<agent_name>.md`) and already nested/compiled files (e.g., `agents/<agent_name>/agents/<agent_name>.md`).
   - If the flat markdown file is missing but the nested markdown file exists, the compiler must treat the nested file as the source of truth, preserve its content, copy the updated harness template, and restore the nested markdown file.
   - Maintain proper logging without emojis.

2. **Clean up Duplicate files**:
   - Remove the 14 flat markdown files from `agents/` in Git:
     - `product_owner.md`
     - `scrum_master.md`
     - `software_architect.md`
     - `software_engineer.md`
     - `ml_engineer.md`
     - `quant_trader.md`
     - `qa.md`
     - `documenter.md`
     - `observability.md`
     - `security.md`
     - `flutter.md`
     - `frontend.md`
     - `sre.md`
     - `seo.md`
   - Keep `agents/AGENTS.md` and the compiled directories.

3. **Validation and Tests**:
   - Update `scripts/validate-agents.py` to validate the files in their new nested directories (`agents/<agent_name>/agents/<agent_name>.md`).
   - Update `tests/test_compile_harnesses.py` with unit tests for compiling from nested locations when flat files are missing.
   - Verify that all unit tests and script validations pass successfully.

4. **Re-run Bootstrap and Sync**:
   - Run `./scripts/bootstrap-agent.sh` to ensure all 14 directories are cleanly compiled/recompiled and symlinked into `.agents/`.
   - Run `./scripts/test-spawn-agent.sh` and `python3 scripts/validate-agents.py` to verify the setup.

5. **Wiki Sync and Git Commit**:
   - Run `./scripts/wiki-sync.sh` to synchronize the wiki.
   - Stage all changes and commit with the exact message: `feat: compile self-contained harnesses for all 14 specialized agents`.

## TDD and Verification Steps

1. **Red Phase**:
   - Update `tests/test_compile_harnesses.py` to add a test case where a flat file is absent but a nested agent markdown file exists.
   - Run the unit tests to confirm the new test fails.
2. **Green Phase**:
   - Implement the new discovery and compilation logic in `scripts/compile-harnesses.py`.
   - Update `scripts/validate-agents.py` to point to the nested locations.
   - Run unit tests to confirm they pass.
3. **Refactor Phase**:
   - Clean up code structure, ensuring no emojis, cliches, or styling violations.
