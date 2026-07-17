# Spec 312: isolate planning-artifact untracking from ambient Git state

- Issue: #312 · Status: implemented
- Date: 2026-07-16 · Author: product_owner

## Context

PR #308 introduced an `init` repair that adds `PLAN.md` and `.solomon/` to consumer `.gitignore` files and removes tracked planning state from the index. The three-gate review reproduced inherited `GIT_*` variables redirecting that mutation to an unrelated repository. The same review found false success reporting, incomplete `.solomon/` repair, and an ineffective textual check in the presence of negated ignore patterns. Issue #39 already establishes the repository-wide Git subprocess isolation contract.

## Problem

Running `solomon-harness init` from a worktree, hook, or host environment carrying `GIT_DIR`, `GIT_WORK_TREE`, or `GIT_INDEX_FILE` can mutate the wrong repository index. Even when Git refuses the removal, the helper reports success. Existing `.solomon/` files remain tracked, and a later negation can make the intended ignore rule ineffective. The repair therefore violates repository isolation, truthfulness, and its own local-state invariant.

## Requirements

1. Every Git subprocess used by planning-artifact repair operates only on the explicit `workspace_root`, with all inherited `GIT_*` variables removed and a ten-second local-operation timeout.
2. The final project-local `.gitignore` semantics ignore root `PLAN.md` and the root `.solomon/` tree, including when prior rules negate either path. Rules emitted by the harness are root-anchored so they do not hide nested files with the same names.
3. A successful repair removes tracked `PLAN.md` and every tracked `.solomon/` path from the target index without deleting working files.
4. Git inspection or mutation failure raises an actionable `RuntimeError`; the helper emits a success message only after a successful index mutation.
5. An already-correct project is idempotent: a second repair changes neither `.gitignore` nor the index.
6. A non-Git or nonexistent workspace never attempts an index mutation; an existing workspace still receives the portable local ignore entries.
7. Before reading or appending `.gitignore`, the helper opens the final path without following symbolic links and verifies that it is a regular, single-link file. An unsafe path raises an actionable `RuntimeError` before any external target can be changed.

## Implementation Pointers

- `solomon_harness/bootstrap.py` — evaluate exact local rules in order and verify effective Git semantics; append root-anchored corrective rules at the end when needed; open `.gitignore` with no-follow semantics and validate its descriptor; run every Git command through `clean_git_env(workspace_root)` with a bounded timeout; enumerate tracked lifecycle roots; and perform one checked `git rm -r --cached` mutation for both artifacts.
- `solomon_harness/subprocess_env.py:21-36` — canonical subprocess boundary. Reuse `clean_git_env(workspace_root)`; do not introduce a second scrubber.
- `tests/test_ensure_project_gitignore.py:29-102` — add deterministic regressions for hostile Git variables, tracked `.solomon/`, a refused `git rm`, ordered negations, and idempotency.
- `docs/adrs/0035-repository-scoped-bootstrap-index-repair.md` — record why `init` may mutate the target index, why the operation fails closed, and why forced removal is rejected.

## Acceptance Criteria

```gherkin
Scenario: Ambient Git state cannot redirect the repair
  Given a target project with tracked PLAN.md
  And an unrelated repository named by GIT_DIR, GIT_WORK_TREE, and GIT_INDEX_FILE
  When planning-artifact repair runs for the target project
  Then PLAN.md leaves only the target index
  And the unrelated repository remains unchanged

Scenario: All local lifecycle state is repaired without deleting files
  Given tracked PLAN.md and .solomon/state.json in the target project
  When planning-artifact repair succeeds
  Then neither path remains tracked
  And both working-tree files still exist

Scenario: Git mutation failure is fail-closed and truthful
  Given Git refuses to remove a lifecycle artifact from the index
  When planning-artifact repair runs
  Then it raises an actionable RuntimeError
  And it does not print a success message

Scenario: Ordered negations are corrected idempotently
  Given .gitignore contains positive lifecycle rules followed by negations
  When planning-artifact repair runs twice
  Then git check-ignore reports PLAN.md and .solomon/state.json as ignored
  And the second run does not change .gitignore

Scenario: A linked ignore file cannot escape the project boundary
  Given the project .gitignore is a symbolic link to a file outside the project
  When planning-artifact repair runs
  Then it raises an actionable RuntimeError
  And the external file remains unchanged

Scenario: Generated rules are root-scoped
  Given a project without lifecycle ignore rules
  When planning-artifact repair runs
  Then the generated rules ignore root PLAN.md and root .solomon state
  And they do not ignore nested paths with those names
```

## Verification

```bash
uv run pytest -q tests/test_ensure_project_gitignore.py
uv run ruff check solomon_harness/bootstrap.py tests/test_ensure_project_gitignore.py
uv run mypy solomon_harness
uv run python scripts/spec-lint.py docs/specs/312-isolate-planning-artifact-untracking.md
uv run pytest
```

## Design Constraints

Reuse the canonical `clean_git_env` boundary. Keep fixed argv with `shell=False`, place `--` before pathspecs, preserve working-tree files, and do not force an index removal across staged-content conflicts. Open `.gitignore` without following the final path and validate the opened descriptor rather than using a check-then-open sequence. The helper may mutate only the explicitly selected repository and must fail closed when that guarantee cannot be proven.

## Out of Scope

Changing where `/solomon-start` writes `PLAN.md`; moving handoff state out of `.solomon/`; repairing unrelated Git subprocess call sites tracked by #39; rewriting arbitrary user ignore patterns; automatically committing the `.gitignore` or index changes.

## Traceability

- Issue: #312
- ADR: ADR-0035
- PR: #308
