# Plan - Code Quality Review and Refactoring for Task 2

Review and improve the robustness, portability, and safety of `scripts/bootstrap-agent.sh` and `tests/test_bootstrap.py`.

## Scope

- In:
  - `scripts/bootstrap-agent.sh`
  - `tests/test_bootstrap.py`
- Out:
  - Any other scripts or test files.

## Action Items

### 1. Identify Code Quality Issues
- [x] Hardcoded workspace directory `/Users/marcelo/Documents/Projects/solomon-harness` in `tests/test_bootstrap.py`.
- [x] Shell scripting safety: Inline Python string expansions `$template_path` and `$dest_path` inside `scripts/bootstrap-agent.sh` are not environment-variable-safe and can cause escaping issues.
- [x] Test side effects: Running the test suite currently overwrites workspace files (`CLAUDE.md`, `agents/AGENTS.md`, Git hooks, `.claude/settings.json`, and `.agents/skills.json`).

### 2. Refactor `scripts/bootstrap-agent.sh`
- [ ] Pass `template_path` and `dest_path` to the Python interpreter via environment variables (`TEMPLATE_PATH` and `DEST_PATH`) rather than direct inline bash expansion inside the Python string.

### 3. Refactor `tests/test_bootstrap.py`
- [ ] Replace hardcoded workspace directory with dynamic path resolution based on `__file__`.
- [ ] Use Python's `tempfile.TemporaryDirectory` to run the bootstrap script in a completely isolated sandboxed environment, preventing any side effects on the actual workspace files.
- [ ] Copy the necessary templates, scripts, and agent files to the temporary directory.
- [ ] Initialize a dummy git repository in the temporary directory to satisfy the git commands in `bootstrap-agent.sh`.
- [ ] Assert the outcomes against the files in the sandboxed directory.

### 4. Verification
- [ ] Run the test suite and verify all tests pass.
- [ ] Run `ruff check` and `ruff format` to ensure coding standard compliance.
