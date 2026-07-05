# PLAN.md: refactor(workflow): update command descriptions and synchronize global install

Problem statement: 
The user wants `/solomon-workflow` to be clearly defined as the command that runs a task end-to-end or continues from a previous execution, and `/solomon-loop` to be defined as the parallel autonomous loop (the current `/solomon-loop-auto`). In the codebase, these commands are already renamed, but the user's local workspace and IDE settings are still showing stale names (`solomon-loop` as the orchestrator and `solomon-loop-auto` as the parallel loop) and the generated global command files are corrupt or outdated.

We need to:
1. Update descriptions for `solomon-workflow` in `.claude/commands/solomon-workflow.md`, `solomon_harness/cli.py`, `README.md`, `docs/solomon-workflow.md`, and `docs/wiki/Commands-Reference.md` to indicate it runs a task end-to-end or continues from a previous execution.
2. Synchronize directories in `solomon_harness/install_global.py` so that old/stale commands (like `solomon-loop-auto.toml`) are deleted from the global directories.
3. Clean up the stale `solomon-loop-auto` directory from the user's `~/.gemini/config/plugins/solomon/skills/` during global installation.
4. Fix the test suite `tests/test_install_global.py` so it does not overwrite the real user's `~/.gemini` folder during test execution.

## Proposed changes

- In `.claude/commands/solomon-workflow.md`:
  - Change description frontmatter to "Run a task end-to-end, or continue from a previous execution".
- In `solomon_harness/cli.py`:
  - Update `"/solomon-workflow"` description to "run a task end-to-end, or continue from a previous execution".
- In `README.md`:
  - Update `/solomon-workflow` description to "run a task end-to-end or continue".
- In `docs/solomon-workflow.md`:
  - Update `/solomon-workflow` table row to "runs a task end-to-end or continues".
- In `docs/wiki/Commands-Reference.md`:
  - Update `/solomon-workflow` heading to `### \`/solomon-workflow\` (End-to-End Orchestrator)` and description.
- In `solomon_harness/install_global.py`:
  - In `_copy_dir_contents`, add logic to delete files in `dest` with the matching suffixes that are not present in `src`.
  - In `install_global`, add cleanup for stale skills in `~/.gemini/config/plugins/solomon/skills/` that do not match the current commands in the source repository.
- In `tests/test_install_global.py`:
  - In tests that call `install_global` with `default_gemini`, patch `os.path.expanduser` so that `"~/.gemini"` points to `self.gemini` instead of the user's real home folder.
  - Update assertions to verify that stale commands in the destination directory are deleted.

## Target files
- `.claude/commands/solomon-workflow.md`
- `solomon_harness/cli.py`
- `solomon_harness/install_global.py`
- `tests/test_install_global.py`
- `README.md`
- `docs/solomon-workflow.md`
- `docs/wiki/Commands-Reference.md`

## Edge cases
- Stale folders in `~/.gemini/config/plugins/solomon/skills/` not being deleted. We handle this explicitly in the `install_global` logic.
- Permissions to read/write/delete files in `~/.gemini/`. We will run standard file operations under defensive try-except blocks.

## TDD breakdown
1. **Red**: Update `tests/test_install_global.py` to assert that stale command files in the destination directories are successfully deleted during installation.
2. **Green**: Implement file deletion in `_copy_dir_contents` in `solomon_harness/install_global.py`.
3. **Red**: Update `tests/test_install_global.py` to verify that stale skills directories are cleaned up when `is_default_gemini` is true.
4. **Green**: Implement the stale skills clean-up in `install_global` in `solomon_harness/install_global.py`.
5. Update command descriptions in target files and regenerate Gemini commands.

## Verification criteria
- Run `uv run pytest` to verify all tests pass.
- Run `solomon-harness compile` and `solomon-harness install-global` to verify that global files are updated and stale commands are removed.
