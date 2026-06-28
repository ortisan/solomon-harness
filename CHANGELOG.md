# Changelog

All notable changes to solomon-harness are recorded here. The format follows Keep a Changelog, and the project adheres to Semantic Versioning.

## [0.3.0] - 2026-06-28

### Added
- `/solomon-start` now creates each issue's branch in its own isolated git worktree (sibling layout `<repo>-worktrees/<branch>`) instead of switching the primary checkout, so a dirty tree never blocks a start and several issues can be in flight at once (#8). New `solomon_harness/worktree.py` helper and `solomon-harness worktree <branch> [--base <ref>]` CLI subcommand.
- `/solomon-start` asks, before any code is written, whether the change is implemented automatically by the agent or manually by a developer (Automatic / Manual / Other), with a deterministic Automatic default on the headless path so CI never hangs (#23).
- ADR-0001 recording the start-stage execution-model decision (worktree layout plus the implementation-mode gate).

### Fixed
- The pre-commit hook ran the test suite inside the commit, leaking `GIT_*` redirectors into tests that shell out to git; it now runs the suite in a clean git environment, fixing the git half of the non-hermetic suite (#24).

### Notes
- Worktree auto-removal on merge/release is not yet automated; remove a finished worktree with `git worktree remove <path>`.

## [0.2.0] - 2026-06-28

### Changed
- Delivery-spine agent skills brought to the canonical depth standard (epic #6): `product_owner` (#9), `scrum_master` (#10), `qa` (#11), and `software_engineer` cross-cutting (#12). Each role-core skill now follows the canonical format — sharp summary, named standards, worked examples, `## Common pitfalls`, `## Definition of done` — at reference depth, with thin duplicates consolidated.

### Added
- Conventions settled and encoded: branch names carry no issue number (`feature/<slug>`); commit messages carry no `Co-Authored-By` trailer; `/solomon-*` workflows present user decisions as enumerated options.

### Notes
- `software_architect` and `sre` already met the depth bar; no change needed.
- Known issue: the test suite is not hermetic and fails inside git worktrees (#24).

## [0.1.0]

- Initial harness: specialist agents, the SurrealDB/SQLite memory layer, the `/solomon-*` delivery workflows, the GitHub project board, the incremental code index, and the living wiki.
