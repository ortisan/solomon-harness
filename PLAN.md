# Plan: add pytest to dev extras so uv run pytest works

Refs #31 #41

## Problem statement

Running `uv run pytest` is currently not supported because `pytest` is declared in `optional-dependencies.dev` instead of the default development groups, and also lacks a configured `pythonpath` for module collection, resulting in a `ModuleNotFoundError` during imports.

## Proposed changes

1. **Update `pyproject.toml` dependencies**:
   - Move or add `ruff`, `mypy`, and `pytest` to `[tool.uv.dev-dependencies]`.
   - Add `[tool.pytest.ini_options]` with `pythonpath = ["."]` to the root of `pyproject.toml`.
2. **Sync dependencies**:
   - Run `uv sync` to update the virtual environment.
3. **Verify collection and execution**:
   - Execute `uv run pytest` to ensure tests are collected and pass without path/import errors.

## Target files

- `pyproject.toml`

## Edge cases as observable outcomes

- **Missing pythonpath**: If `pythonpath = ["."]` is absent, running `uv run pytest` will fail during collection with `ModuleNotFoundError: No module named 'solomon_harness'`.
- **Missing dev extra sync**: If dependencies remain under optional dev extras without syncing them as default dev dependencies, running `uv run pytest` will report "Failed to spawn: pytest".

## TDD breakdown

### Step 1: Add pytest configuration to `pyproject.toml`
- **Goal**: Configure pytest pythonpath.
- **Action**: Add `[tool.pytest.ini_options] pythonpath = ["."]` to `pyproject.toml`.
- **Commit**: `chore(testing): configure pytest pythonpath`

### Step 2: Transition dev dependencies to default dev-dependencies
- **Goal**: Make pytest available by default.
- **Action**: Add `ruff`, `mypy`, and `pytest` to `[tool.uv.dev-dependencies]` block and update optional dev dependencies.
- **Commit**: `chore(testing): add pytest to default dev-dependencies`

### Step 3: Run uv sync and verify pytest runs
- **Goal**: Confirm all tests pass under pytest.
- **Action**: Execute `uv sync` followed by `uv run pytest`.
- **Commit**: `test(testing): verify test suite runs successfully under pytest`

## STRIDE notes

- **Security Boundary**: No network or external input boundaries are modified by this chore. STRIDE threat model is not impacted.

## Verification criteria

1. Running `uv run pytest` collects all tests and exits 0.
2. No `PYTHONPATH=.` environment prefix is required to invoke pytest.
3. `uv run python scripts/validate-agents.py` exits 0.
