# PLAN.md: chore(agents): capability-router hardening follow-ups

Problem statement: Harden the capability-router module by implementing safety caps, path confinement/symlink rejection, import-graph/no-write fitness checks, distinct matcher contract error type, and order assertions (#85).

## Proposed changes
- Introduce `MatcherContractError` in `solomon_harness/capability_router.py`.
- Update `_role_description` to prevent unbounded memory read by reading at most 8192 bytes per readline call and handling line continuation.
- Update `load_catalog` to resolve realpaths, ensure paths are confined within the `agents` folder, and reject symlink files/directories.
- Raise `MatcherContractError` (instead of `CatalogError`) when the matcher returns an agent not in the catalog.
- Write unit tests covering read-capping, path confinement, symlink rejection, the new error type, alternatives ordering, and module isolation/no-write fitness check.

## Target files
- `solomon_harness/capability_router.py`
- `tests/test_capability_router.py`

## Edge cases
- Giant single-line role file (memory safety).
- Directory traversal using symlink.
- Matcher returning an agent not present in the catalog.
- Alternatives containing invalid/valid agents in specific order.
- Module attempting to import blacklisted libraries (e.g. requests, urllib, torch).

## TDD breakdown
1. **Red**: Write a test in `tests/test_capability_router.py` for giant single-line files and read capping.
   **Green**: Update `_role_description` to read in chunks of 8192 bytes and handle line continuation.
   *Commit: test: add read cap tests and implement readline capping*
2. **Red**: Write a test for symlink rejection and path confinement.
   **Green**: Update `load_catalog` to verify realpaths and reject symlinks using `os.path.islink`.
   *Commit: test: add confinement/symlink tests and implement catalog protection*
3. **Red**: Write a test asserting that `MatcherContractError` is raised when the matcher returns an invalid agent.
   **Green**: Define `MatcherContractError` and raise it in `route`.
   *Commit: test: add matcher contract error test and implement error type*
4. **Red**: Write a test asserting that alternatives ordering is preserved.
   **Green**: Verify alternatives tuple is constructed preserving order.
   *Commit: test: add alternatives order assertion test*
5. **Red**: Write a test parsing `solomon_harness/capability_router.py` AST to check imports (fitness check) and ensuring no write operations.
   **Green**: Ensure AST validation test passes.
   *Commit: test: add CI fitness check for module isolation*

## Verification criteria
- `PYTHONPATH=. uv run pytest tests/test_capability_router.py` passes.
- All 387 tests pass.
