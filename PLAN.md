# Plan - Refactor Unified Agent Memory Database Client Path Resolution

This plan outlines the refactoring of templates/harness/tools/database_client.py to resolve the unified project root directory and update tests to cover this behavior.

## Objectives
1. Implement directory traversal in DatabaseClient.__init__ to locate the repository root by finding the '.git' directory.
2. Load configuration from project_root/.agent/config.json.
3. Default SQLite database path to project_root/memory/long_term/harness.db.
4. Fall back to templates/harness parent directory if no '.git' directory is found.
5. Follow the TDD development cycle: write tests validating the resolution and fallback (Red phase), modify the source code (Green phase), and clean up code/types (Refactor phase).
6. Commit changes with the exact commit message: "refactor: resolve unified project root database path in client template"

## TDD Lifecycle (Red, Green, Refactor)
- Red Phase: Add test cases to tests/test_database_client.py that mock/simulate finding or not finding the '.git' directory, verifying that config path and db path are correctly computed. Verify that these new tests fail.
- Green Phase: Implement the directory traversal and fallback logic in templates/harness/tools/database_client.py. Run the tests to verify that they pass.
- Refactor Phase: Ensure full PEP 484 type annotations are preserved and run static analysis checks.

## Verification Criteria
- New unit tests successfully execute and verify project root resolution.
- All unit tests pass cleanly.
- Git status is ready for commit.

## Code Quality Review & Cleanup
1. Fix E402 lint (Module level import not at top of file) in tests/test_database_client.py by adding # noqa: E402.
2. Fix F841 lints (Unused local variables mock_makedirs and mock_connect) in tests/test_database_client.py by removing the 'as' bindings in the patch calls.
3. Validate type checking with mypy and linting with ruff.
4. Execute tests to verify correctness.

