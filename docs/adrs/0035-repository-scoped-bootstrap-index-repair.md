# ADR-0035: Repository-scoped bootstrap index repair

- Status: accepted
- Date: 2026-07-16
- Deciders: software_architect, security, software_engineer
- Issue: #312

## Context and problem statement

`solomon-harness init` must retrofit the existing project-local convention that `PLAN.md` and `.solomon/` are lifecycle state rather than shared source. Adding ignore entries alone does not repair files already tracked by Git, so PR #308 added automatic `git rm --cached`. Review reproduced inherited `GIT_DIR`, `GIT_WORK_TREE`, and `GIT_INDEX_FILE` redirecting that mutation to another repository and found that failed removals were reported as successful. The decision must define whether `init` may mutate a consumer index and the safety contract around that mutation.

## Decision drivers

- Repository isolation: no caller environment may redirect a mutation outside the explicit `workspace_root`.
- Working-data preservation: repair removes index entries but never deletes lifecycle files from the working tree.
- Truthful failure semantics: an unsuccessful mutation cannot be logged as success or silently ignored.
- Portable convention: project-local `.gitignore` rules, not a developer's global excludes, carry the lifecycle invariant.
- Idempotency: converged projects perform no further file or index mutation.

## Considered options

- **A. Add ignore rules but never repair the index.** Safe from index mutation, but already-tracked lifecycle state continues to collide across branches and the reported defect remains.
- **B. Repair the index best-effort and swallow Git errors.** Keeps `init` running, but produces false success and leaves callers unable to distinguish a repaired project from an unsafe one.
- **C. Run a repository-scoped, checked, fail-closed index repair.** Strip all inherited `GIT_*`, use fixed local Git commands with a timeout, remove both lifecycle roots in one checked operation, and raise an actionable error on failure.
- **D. Force index removal with `git rm -f`.** Maximizes automatic convergence, but can discard staged index state the developer intentionally prepared.

## Decision outcome

Chosen: **C — repository-scoped, checked, fail-closed repair**.

`init` may append explicit project-local rules for root `PLAN.md` and `.solomon/`, then remove those roots from the selected project's index while leaving working files intact. Every Git subprocess in this path receives `clean_git_env(workspace_root)`, fixed argv with a `--` pathspec boundary, captured output, and a ten-second timeout. The helper inspects tracked paths first and issues one recursive cached-only removal for the roots that are actually tracked.

Ignore-rule evaluation respects order and negation. When existing rules do not leave both lifecycle artifacts effectively ignored, corrective exact rules are appended at the end so they become the final project-local decision. An already-converged file is not rewritten.

The error set is closed to an actionable `RuntimeError` from this helper: unavailable Git, timeout, failed ignore inspection, failed index listing, or refused index removal. No success message is emitted before the checked mutation returns zero. The operation does not use `-f`; staged-content conflicts require the developer to resolve the index and rerun `init`.

### Consequences

- Positive: worktree and hook environments cannot redirect the repair; both lifecycle roots self-heal; success output is trustworthy; repeated initialization is idempotent.
- Negative: `init` now fails when Git cannot safely remove a tracked artifact, and the developer must resolve staged-content conflicts manually before retrying.
- Follow-ups: issue #39 remains responsible for auditing unrelated Git subprocesses. PR #308 must keep the hostile-environment and failure-path regressions as permanent fitness functions.

## More information

- Implements issue #312 in PR #308.
- Reuses the subprocess boundary established after issue #24 and tracked further by issue #39.
- The decision is mirrored in project memory with branch and commit provenance.
