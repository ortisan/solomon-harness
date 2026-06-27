# Plan - Clean Up Duplicate SQLite Database Files from Subagent Directories

This plan outlines the steps to remove duplicate SQLite database files and ensure only the unified root database is active.

## Objectives
1. Scan all agent subdirectories under agents/ to ensure no duplicate SQLite database files (harness.db) exist under agents/*/memory/long_term/harness.db or agents/*/memory/.
2. Remove any duplicate database files found in the subagent directories.
3. Update templates/harness/tools/database_client.py to ensure that the project root is correctly resolved to the workspace root when database client is initialized inside subagent directories, preventing duplicate database creation.
4. Add a unit test to tests/test_database_client.py verifying that the project root resolves to the repository root directory when initialized inside an agent subdirectory.
5. Recompile all agent harnesses using compile-harnesses.py.
6. Verify that all tests pass cleanly using python3 -m unittest discover -s tests.
7. Sync the project wiki using scripts/wiki-sync.sh.
8. Commit changes to Git with the exact message: chore: clean up duplicate SQLite database files from subagent directories.

## Verification Steps
- Verify no duplicate harness.db files remain in the agents/ directory.
- Verify templates/harness/tools/database_client.py resolves the project root correctly when run within an agent subdirectory.
- Run all python unit tests.
