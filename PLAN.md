# Plan - Solomon Harness Task 1: Agent Harness Refactoring

This plan outlines the design, implementation, and verification steps for Task 1 of the Solomon Harness refactoring.

## Requirements

1. **LLM Configuration Template**:
   - Write templates/harness/.agent/config.json.
   
2. **Encrypted Vault Mock**:
   - Write templates/harness/.agent/secure_vault.enc containing base64 mock vault.

3. **Git Operations Instructions**:
   - Write templates/harness/skills/git_operations.md containing instructions for Conventional Commits and Git Flow. Clean English, no emojis/icons, no AI clichés.

4. **Test Runner Command Configuration**:
   - Write templates/harness/skills/test_runner.yaml mapping test commands.

5. **Documentation Formatting Rules**:
   - Write templates/harness/skills/doc_generator.json specifying formatting rules.

6. **Browser client**:
   - Write templates/harness/tools/browser.py with BrowserClient, navigate and search methods.

7. **Database Client**:
   - Write templates/harness/tools/database_client.py. Connects to memory/long_term/harness.db.
   - Detects database directory dynamically.
   - Creates tables (decisions, memory, milestones, issues, backtest_runs) if they do not exist.
   - Implements helper methods for insert/query.

8. **Evaluation Test Suite**:
   - Write templates/harness/tests/agent_evals.py, checking config, database, and persona.

9. **Main Entry CLI**:
   - Write templates/harness/main.py with db-init, eval, and run subcommands.

10. **Git Ignore Configuration**:
    - Update the root .gitignore to ignore the SQLite db and short-term memory files.

## TDD and Verification Steps

1. Write templates/harness/tests/agent_evals.py first. It should fail to run or fail to find other files since they are not created yet (Red phase).
2. Create config.json, secure_vault.enc, git_operations.md, test_runner.yaml, doc_generator.json, and the persona file if expected by tests.
3. Implement tools/browser.py.
4. Implement tools/database_client.py.
5. Implement main.py.
6. Verify all tests in templates/harness/tests/agent_evals.py pass successfully (Green phase).
7. Refactor the code if needed, keeping tests green (Refactor phase).
8. Sync the project wiki.
9. Stage and commit changes.

## Execution Checklist

- [ ] Write the detailed plan in PLAN.md
- [ ] Write templates/harness/tests/agent_evals.py
- [ ] Run the tests and confirm failures (Red phase)
- [ ] Create templates/harness/.agent/config.json
- [ ] Create templates/harness/.agent/secure_vault.enc
- [ ] Create templates/harness/skills/git_operations.md
- [ ] Create templates/harness/skills/test_runner.yaml
- [ ] Create templates/harness/skills/doc_generator.json
- [ ] Create templates/harness/tools/browser.py
- [ ] Create templates/harness/tools/database_client.py
- [ ] Create templates/harness/main.py
- [ ] Run templates/harness/tests/agent_evals.py and verify passes (Green phase)
- [ ] Update root .gitignore
- [ ] Run wiki-sync.sh script to sync project wiki
- [ ] Stage and commit changes
