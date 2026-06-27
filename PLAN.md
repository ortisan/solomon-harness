# Plan - Compile, Validate, and Verify All Agents

This plan details the implementation of Task 4, which compiles the final templates, runs the full unit test suite, runs all local validators, verifies agent spawning, synchronizes documentation to the project wiki, and commits the finalized states.

## Objectives
1. Run `./scripts/bootstrap-agent.sh` to compile the final templates to all 14 agents.
2. Execute the entire unit test suite:
   - Run `python3 -m unittest discover -s tests` to verify all 10+ unit tests across the codebase are fully green.
3. Run all local validators:
   - Run `python3 scripts/validate-agents.py`
   - Run `python3 scripts/validate-templates.py`
   - Run `python3 scripts/validate-workflows.py`
   - Run `./scripts/test-spawn-agent.sh`
4. Execute `scripts/wiki-sync.sh` to synchronize any final documentation updates.
5. Stage all files and commit to Git with the exact message: `test: compile and verify all 14 agents with SurrealDB memory integration`.

## TDD Lifecycle (Red, Green, Refactor)
- **Red Phase**: Not applicable as there are no direct feature implementations or functional changes in this task.
- **Green Phase**: Ensure compilation succeeds and all tests/validators pass cleanly.
- **Refactor Phase**: Resolve any validation warnings, type check errors, or formatting anomalies that arise.

## Verification Criteria
- All 14 agents are successfully compiled from the templates.
- All unit tests pass cleanly.
- All validators exit with code 0.
- Documentation is synced with the wiki script.
- Git status is clean post-commit.
