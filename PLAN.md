# PLAN.md: fix(testing): test suite passes inside a git worktree (test_home tenant, test_bootstrap kanban)

Problem statement (Refs #30):
Two tests fail inside a git worktree but pass in the main checkout:
- `test_home.test_real_git_repo_resolves_remote`: a temp repo's tenant resolves to the enclosing repo's remote (`ortisan-solomon-harness`) instead of its own (`acme-widget`).
- `test_bootstrap`: the kanban fallback check resolves to the enclosing repository's remote, which has Projects/Wiki enabled, and skips local `KANBAN.md` / wiki creation, causing test assertions to fail.

Both issues are caused by `git` and `gh` subprocess calls inheriting the parent process's `GIT_*` environment variables (such as `GIT_DIR` and `GIT_WORK_TREE` set by git when running inside a worktree). Even when a test initializes a repo in a temporary directory, git commands run in that temporary directory are redirected back to the enclosing repository.

## Proposed Change
We will ensure that all `git` and `gh` subprocesses spawned by the test setup, test cases, and the bootstrap/wiki code run with a cleaned environment where all `GIT_*` variables are stripped. This is done by passing `env=clean_git_env()` to the subprocess calls.

Specifically:
1. In `tests/test_bootstrap.py`:
   - Import `clean_git_env` from `solomon_harness.subprocess_env`.
   - Update all `subprocess.run` calls (in `setUp` and individual tests) to include `env=clean_git_env()`.
2. In `tests/test_home.py`:
   - Import `clean_git_env` from `solomon_harness.subprocess_env`.
   - Update `test_real_git_repo_resolves_remote` to use `clean_git_env()` instead of manual dict filtering.
3. In `solomon_harness/bootstrap.py`:
   - Update the `gh repo view` calls in `has_github_project_and_wiki` and `github_wiki_enabled` to use `env=clean_git_env()`.
   - Update the `git ls-remote` call for checking wiki initialization to use `env=clean_git_env()`.
   - Update the `git rev-parse` hook directory lookup to use `env=clean_git_env()`.
4. In `solomon_harness/wiki_bootstrap.py`:
   - Import `clean_git_env` from `solomon_harness.subprocess_env`.
   - Update `wiki_refs_present` to pass `env=clean_git_env()` to the subprocess runner.

## Target Files
- [solomon_harness/bootstrap.py](file:///Users/marcelo/.gemini/antigravity-cli/scratch/solomon-harness-review-worktrees/bugfix-test-suite-passes-inside-git-worktree/solomon_harness/bootstrap.py)
- [solomon_harness/wiki_bootstrap.py](file:///Users/marcelo/.gemini/antigravity-cli/scratch/solomon-harness-review-worktrees/bugfix-test-suite-passes-inside-git-worktree/solomon_harness/wiki_bootstrap.py)
- [tests/test_bootstrap.py](file:///Users/marcelo/.gemini/antigravity-cli/scratch/solomon-harness-review-worktrees/bugfix-test-suite-passes-inside-git-worktree/tests/test_bootstrap.py)
- [tests/test_home.py](file:///Users/marcelo/.gemini/antigravity-cli/scratch/solomon-harness-review-worktrees/bugfix-test-suite-passes-inside-git-worktree/tests/test_home.py)

## Edge Cases
- Test environments might mock `subprocess.run` or `subprocess.check_output` (e.g. `wiki_refs_present` accepts a `runner` parameter). The mock runners must handle the `env` keyword argument correctly without raising `TypeError`. (Verified that `TestWikiRefsPresent` uses mock runners that accept `**kwargs` and will not raise).

## TDD Breakdown
1. **Red**: Modify `tests/test_bootstrap.py` to run the setup/test commands with a simulated worktree environment containing dummy `GIT_DIR` / `GIT_WORK_TREE` values. Confirm that `test_bootstrap_creates_fallback_kanban_and_wiki_when_no_github` fails due to git command leakage.
2. **Green**: Clean environment variables for `git` and `gh` subprocess calls in `solomon_harness/bootstrap.py`, `solomon_harness/wiki_bootstrap.py`, and `tests/test_bootstrap.py`. Verify that `test_bootstrap` tests now pass under the simulated worktree environment.
3. **Red**: Update `tests/test_home.py` to run `test_real_git_repo_resolves_remote` under a simulated `GIT_DIR` environment without manual env filtering, and verify it fails.
4. **Green**: Update `tests/test_home.py` to use `clean_git_env()` and verify it passes.

## STRIDE Notes
- **Information Disclosure**: Subprocesses executing git commands could potentially leak path structures or repository metadata if environment variables are not sanitized. Sanitizing the environment limits the command scope strictly to the target repository directory.

## Verification Criteria
- Run `uv run pytest` in the worktree and verify all tests pass.
- Verify that `test_bootstrap` and `test_home` run successfully and isolate their git contexts.
