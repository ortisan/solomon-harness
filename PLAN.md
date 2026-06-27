# Plan - Isolate Evaluation Tests and Recompile Agent Harnesses

This plan outlines the steps to isolate evaluation tests, clean up `.gitignore`, and recompile the agent harnesses.

## Objectives
1. Ensure `templates/harness/tests/agent_evals.py` initializes `DatabaseClient` with an isolated temporary database path.
2. Clean up old/obsolete database ignores in the root `.gitignore`.
3. Recompile the updated database client and test configurations across all 14 agent harnesses using `./scripts/bootstrap-agent.sh`.
4. Verify all tests pass cleanly using `python3 -m unittest discover -s tests`.
5. Sync the project wiki using `./scripts/wiki-sync.sh`.
6. Commit changes to Git with the exact message: `chore: isolate evaluation tests and recompile agent harnesses`.

## Verification Steps
- Verify `.gitignore` changes.
- Verify `templates/harness/tests/agent_evals.py` uses temporary directory paths for all test database clients.
- Verify agent harness recompilation output.
- Run all python unit tests.
