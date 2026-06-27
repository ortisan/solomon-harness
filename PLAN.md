# Plan - Solomon Harness Task 2: SurrealDB Spectron Memory Integration Database Client

This plan outlines the design, implementation, and verification steps for Task 2 of the Solomon Harness: SurrealDB Spectron Memory Integration plan.

## Requirements

1. **Refactor `templates/harness/tools/database_client.py`**:
   - Dynamic backend selection:
     - Attempt to import `surrealdb` (`from surrealdb import Surreal`).
     - Load `.agent/config.json` relative to the client's file location.
     - If the configuration provider is `"surrealdb"` and `surrealdb` was successfully imported:
       - Connect to the SurrealDB server using `Surreal(url)`.
       - Authenticate using `db.signin({"user": username, "pass": password})`.
       - Select namespace and database using `db.use(namespace, database)`.
       - Run initialization queries wrapped in try-except:
         `DEFINE TABLE decisions SCHEMALESS; DEFINE TABLE memory SCHEMALESS; DEFINE TABLE milestones SCHEMALESS; DEFINE TABLE issues SCHEMALESS; DEFINE TABLE backtest_runs SCHEMALESS;`
       - Handle any connection errors or server unavailable cases by printing/logging a warning and falling back to the SQLite backend.
     - Fall back to the SQLite backend if:
       - Configured provider is not `"surrealdb"`.
       - `surrealdb` package is not available.
       - Connection or query execution on SurrealDB fails.
     - Fallback behavior:
       - Log/print: "SurrealDB library or server unavailable. Falling back to SQLite backend."
       - Initialize SQLite connection to `memory/long_term/harness.db`.
       - Create required SQLite tables.

2. **Implement Uniform API**:
   - `log_decision(self, title, rationale, outcome, author, branch, commit_sha)`
   - `save_memory(self, key, value, category)`
   - `get_memory(self, key)`
   - `create_milestone(self, title, description, due_date, state)`
   - `log_issue(self, github_id, title, type_, status, milestone_id)`
   - `save_backtest(self, strategy_name, sharpe_ratio, max_drawdown, profit_factor, parameters, dataset, commit_sha)`
   - (Optional but recommended for compatibility) Maintain query/get methods like `get_decision`, `get_milestone`, `get_issue`, `get_backtest`.

3. **SurrealDB Backend Queries**:
   - Use standard SurrealQL commands (e.g. `INSERT INTO decisions { ... }` or `CREATE decisions CONTENT { ... }`).
   - Support closing the connection on client close or supporting context managers.

4. **Code Quality and Constraints**:
   - No emojis or icons.
   - Clean, professional English following PEP 8.

## TDD Development Cycle

### 1. Red Phase
- Implement a new test suite in `tests/test_database_client.py` verifying:
  - SQLite backend initialization and methods when configured as SQLite.
  - SurrealDB backend connection attempt and fallback behavior if the library is not installed or connection fails.
  - SurrealDB backend working correctly using a mock implementation of the `surrealdb` module.
- Run the test suite and verify that the tests either fail or show missing implementations (Red state).

### 2. Green Phase
- Modify `templates/harness/tools/database_client.py` with the complete dynamic backend selection and uniform API.
- Run the test suite and ensure all tests pass.

### 3. Refactor Phase
- Format and clean the implementation files.
- Verify PEP 8 compliance.
- Run the wiki sync using `scripts/wiki-sync.sh`.
- Stage and commit changes.
