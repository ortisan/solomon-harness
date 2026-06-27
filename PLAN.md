# Plan - Solomon Harness Task 2: Agent Harness Refactoring

This plan outlines the design, implementation, and verification steps for Task 2 of the Solomon Harness refactoring.

## Requirements

1. **Compiler Script `scripts/compile-harnesses.py`**:
   - Must be a Python 3 script.
   - Scans the `agents/` root directory for all `.md` files, excluding `AGENTS.md` and any subdirectories.
   - For each discovered agent `.md` file (e.g., `agents/product_owner.md`):
     - Extracts the agent name (e.g., `product_owner`).
     - Creates the target agent directory structure `agents/<agent_name>/`.
     - Recursively copies all directories and files from `templates/harness/` to `agents/<agent_name>/`.
     - Replaces the placeholder `{{AGENT_NAME}}` in `agents/<agent_name>/.agent/config.json` with the actual agent name.
     - Creates `agents/<agent_name>/agents/` if it does not exist.
     - Copies the global rules template `agents/AGENTS.md` to `agents/<agent_name>/agents/AGENTS.md`.
     - Copies the specific agent markdown file to `agents/<agent_name>/agents/<agent_name>.md`.
   - Must implement proper logging, error handling, clean code structure, and avoid emojis in output logs.

2. **Bootstrap Script Update `scripts/bootstrap-agent.sh`**:
   - Update it to first run `python3 scripts/compile-harnesses.py` to compile the agent harnesses.
   - Update it to link or copy the final generated files to the `.agents/` directory to stay in sync:
     - Symlink/copy `agents/AGENTS.md` to `.agents/AGENTS.md`.
     - Symlink/copy `agents/<agent_name>/agents/<agent_name>.md` to `.agents/agents/<agent_name>.md` for each compiled agent.
   - Ensure the bootstrap script exits with `0` on success and non-zero on failure.

3. **Git Commit**:
   - Message: `feat: implement compiler script to distribute harness structure across specialists`
   - Strictly follow conventional commits, direct professional English, and zero emojis/icons.

4. **Wiki Synchronization**:
   - Execute `scripts/wiki-sync.sh` on completion.

## TDD and Verification Steps

1. **Write failing unit tests (Red Phase)**:
   - Create `tests/test_compile_harnesses.py` containing tests that verify the behavior of `scripts/compile-harnesses.py`.
   - Verify that the tests fail when the script is missing or incomplete.
2. **Implement compiler script (Green Phase)**:
   - Implement `scripts/compile-harnesses.py` adhering to all requirements.
   - Run unit tests and verify they pass.
3. **Update and verify bootstrap script**:
   - Modify `scripts/bootstrap-agent.sh` to run the compiler and perform the sync steps.
   - Verify the bootstrap script runs successfully, creates the required files/links, and exits with 0.
4. **Refactor (Refactor Phase)**:
   - Refactor Python and Bash code to improve design, readability, and performance, ensuring tests remain green.

## Execution Checklist

- [ ] Write the detailed plan in PLAN.md
- [ ] Create failing unit tests in `tests/test_compile_harnesses.py`
- [ ] Run tests and verify failure (Red Phase)
- [ ] Create and implement `scripts/compile-harnesses.py`
- [ ] Run unit tests and verify success (Green Phase)
- [ ] Update `scripts/bootstrap-agent.sh`
- [ ] Test the bootstrap script locally and verify outputs
- [ ] Refactor scripts and tests if necessary (Refactor Phase)
- [ ] Run `scripts/wiki-sync.sh` to synchronize the wiki
- [ ] Stage and commit changes to Git
