# Plan - SurrealDB Spectron Memory Integration and Interactive Agent Loop

This plan details the implementation of Task 3, which integrates the interactive agent execution loop, updates the SQLite/SurrealDB database client query support, updates evaluation tests, and compiles the templates across all agents.

## Objectives
1. Update `templates/harness/tools/database_client.py` to support querying open issues and retrieving the latest session or handoff.
2. Update `templates/harness/main.py` to:
   - Initialize the database client on startup.
   - Show startup logs: the last active session/handoff status and the list of currently open issues.
   - Run an interactive execution loop enabling selection or creation of issues, simulation of agent execution steps, recording session state, updating issue status to closed, and repeating.
   - Exclude emojis and use direct, professional human-like language.
   - Use PEP 484 type annotations and robust error handling.
3. Update `templates/harness/tests/agent_evals.py` to:
   - Add unit tests for `sessions` and `handoffs` tables in `DatabaseClient`.
   - Add unit tests for `main.py` entry points and command parser.
   - Use isolated/mocked/temporary database configurations.
4. Compile and distribute updated templates to all subagents using the compilation script.
5. Verification of all tests.

## TDD Lifecycle (Red, Green, Refactor)
1. **Red Phase**: Edit `templates/harness/tests/agent_evals.py` to define tests for the new database operations and interactive command runner inputs. Run tests to verify they fail as expected.
2. **Green Phase**: Implement the database query methods in `templates/harness/tools/database_client.py` and the interactive CLI structure in `templates/harness/main.py`. Ensure all tests pass.
3. **Refactor Phase**: Clean up any code redundancies, ensure type hints satisfy static analysis, and verify correct program execution.

## Verification Criteria
- All tests in `templates/harness/tests/agent_evals.py` and root project level tests must execute and pass.
- No emojis are present in outputs, logs, or commit messages.
- Clean exit code (0) on successful program runs.
