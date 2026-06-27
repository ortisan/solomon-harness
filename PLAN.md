# Plan - Solomon Harness Task 1: SurrealDB Spectron Memory Integration Template Update

This plan outlines the design, implementation, and verification steps for Task 1 of the Solomon Harness: SurrealDB Spectron Memory Integration plan.

## Requirements

1. **Modify `templates/harness/.agent/config.json`**:
   - Add SurrealDB database connection parameters:
     ```json
     "database": {
       "provider": "surrealdb",
       "url": "ws://localhost:8000/rpc",
       "namespace": "solomon",
       "database": "harness",
       "username": "root",
       "password": "root"
     }
     ```
2. **JSON and Language Quality**:
   - Ensure the template remains valid JSON.
   - Maintain clean English with no emojis or AI clichés in any comments, docs, or commit messages.

## TDD Development Cycle

### 1. Red Phase
- Add a new unit test to `tests/test_harness_init.py` (e.g., `test_template_config_json_database`) that:
  - Reads `templates/harness/.agent/config.json`.
  - Asserts that it contains the `"database"` key, with all the correct nested keys and values (`provider`, `url`, `namespace`, `database`, `username`, `password`).
- Run the test suite and confirm that the new test fails.

### 2. Green Phase
- Edit `templates/harness/.agent/config.json` to add the SurrealDB connection parameters.
- Run the test suite and confirm that the new test passes.

### 3. Refactor Phase
- Check the JSON formatting of `templates/harness/.agent/config.json` to ensure it is clean and pretty-printed.
- Verify that all unit tests pass successfully.
- Sync the project wiki using the `scripts/wiki-sync.sh` script if applicable.
