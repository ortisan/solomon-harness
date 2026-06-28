# Plan - Modular & Packaging Refactoring of solomon-harness

Refactor the repository structure and packaging to turn the harness into a standardized, self-contained Python CLI tool (`solomon-harness`). All templates and script logic will be encapsulated inside the `solomon_harness` package. This allows it to be installed globally or per-project, dynamically extract target project metadata/structure, and compile agent harnesses out-of-the-box while remaining fully customizable.

## Target Architecture

- **`solomon_harness/`**: Main package distributed via pip/uv.
  - **`templates/`**: Bundled templates (`harness/`, `patterns/`) moved from the repository root.
  - **`cli.py`**: Command parser and dispatcher for `solomon-harness` subcommands (`init`, `compile`, `skills`, `agents`, `db-init`, `run`, `eval`).
  - **`bootstrap.py`**: Python implementation of project initialization and agent metadata extraction.
  - **`compiler.py`**: Python implementation of agent harness compilation.
  - **`skills.py`**: Python implementation of external skill fetching and management.
- **`scripts/`**: Retained as thin shell/python wrappers delegating to the installed or local package for backward compatibility and test stability.
- **Root Cleanup**: Remove unused empty root folders `skills/` and `tools/`.

---

## Action Items

### 1. File Relocation & Clean-up
- [ ] Move `templates/` folder to `solomon_harness/templates/`.
- [ ] Delete root `skills/` and `tools/` directories.
- [ ] Update `tests/test_harness_init.py` to remove assertions for root `skills/` and `tools/` directories.

### 2. Implement Python Business Logic in `solomon_harness`
- [ ] Create `solomon_harness/bootstrap.py`:
  - Python-based dynamic extraction of project metadata (Project Name, Git origin, tech stack).
  - Writing `.agent/config.json` with software patterns configuration.
  - Generating `.claude/settings.json`.
  - Generating `CLAUDE.md` and `agents/AGENTS.md` by interpolating templates.
- [ ] Create `solomon_harness/compiler.py`:
  - Port compilation logic from `scripts/compile-harnesses.py`.
  - Resolve templates relative to package location, or fall back to user's root templates if customized.
  - Discover agents from target project's `agents/` folder.
- [ ] Create `solomon_harness/skills.py`:
  - Implement external skill fetching and management, exposed via `solomon-harness skills`.
- [ ] Update `solomon_harness/cli.py` to support all subcommands:
  - `init`: Calls `bootstrap` logic.
  - `compile`: Calls `compiler` logic.
  - `skills`: Calls `skills` logic.
  - `agents`: Lists and shows subagent definitions.

### 3. Simplify Root Scripts to Thin Wrappers
- [ ] Refactor `scripts/bootstrap-agent.sh` to call `python3 -m solomon_harness.cli init "$@"`.
- [ ] Refactor `scripts/compile-harnesses.py` to call `solomon_harness.compiler.compile_harnesses`.
- [ ] Expose external skill management through `solomon-harness skills` (the standalone `scripts/fetch-skills.py` wrapper was later removed).
- [ ] Refactor `scripts/spawn-agent.sh` to call `python3 -m solomon_harness.cli agents "$@"`.

### 4. Setup Python Entrypoints & Verification
- [ ] Expose `solomon-harness` script entrypoint in `pyproject.toml`.
- [ ] Update `tests/test_bootstrap.py` and `tests/test_compile_harnesses.py` to copy `solomon_harness` package to temp workspaces for sandbox execution.
- [ ] Run test suite with `uv run python -m unittest discover -s tests`.

---

## Verification Criteria

1. **Test Suite**: `uv run python -m unittest discover -s tests` runs all tests and reports 100% success.
2. **Ruff / MyPy**: No static analysis or type errors.
3. **No Unused Directories**: Root `skills/` and `tools/` are removed from git tracking and disk.
4. **Customizability**: Standard agent harness works with bundled templates but dynamically supports custom user templates when overriding in `templates/` folder.
