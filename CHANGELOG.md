# Changelog

All notable changes to solomon-harness are recorded here. The format follows Keep a Changelog, and the project adheres to Semantic Versioning.

## [Unreleased]

### Fixed
- `init` now propagates the per-branch planning-artifact ignore rule into every project: `bootstrap` ensures `.gitignore` effectively excludes `PLAN.md` and `.solomon/`, then removes either artifact from only the selected project's index while preserving working files. The repair strips inherited `GIT_*`, checks every Git result, and fails closed instead of reporting a false success. Projects bootstrapped before this kept stale lifecycle state that collided across concurrent branches.

## [0.11.0] - 2026-06-29

### Added
- cockpit per-user velocity — the throughput number (slice 3a) (#140)
- close synthetic tracking rows when their parent issue or PR resolves (#134)

## [0.10.0] - 2026-06-29

### Added
- check memory for pending tasks and output options card on session start for Claude Code and Gemini (#130)

## [0.9.0] - 2026-06-29

### Added
- multi-model SurrealDB and structural spec-audit fixes (#119)
- fetch and adapt an external skill with SHA pinning and security guards (#99)

## [0.8.0] - 2026-06-29

### Added
- implement apply_proposal in curator with validations

### Fixed
- record delivered issues as terminal and define open by a canonical predicate (#107)
- green the CI pipeline — uv dependency group, mypy module resolution, and 8 type errors (#110)
- check and repair stray core.worktree and core.bare=true config (#98)

## [0.7.0] - 2026-06-29

### Added
- feat(ui): cockpit foundation — read-only single-project board (slice 1a) (#77)

## [0.6.0] - 2026-06-29

### Added
- add the legacy_modernizer specialist and its parsimonious migration-planning contract (#83)

## [0.5.0] - 2026-06-28

### Added
- capability-broker routing + gap detection (slice A of #43) (#84)
- loop-engineering safety floor (#45)
- research_analyst specialist — valuation and research playbook (slice 1) (#82)
- milestone-gated release standard on trunk (#69)

### Fixed
- support custom TOML slash commands in Antigravity TUI (#89)

## [0.4.0] - 2026-06-28

### Fixed
- The memory client now survives a mid-session SurrealDB connection drop: it reconnects once (bounded, so a half-open socket can never hang) and otherwise falls back to SQLite and re-dispatches to each method's SQLite branch, instead of raising forever (#37). This is the durable fix for the v0.3.0-release incident where a recreated SurrealDB container silently lost writes.
- Reads no longer mask a broken connection: `get_latest_activity` reconnects/falls back or raises a distinct connection error rather than silently returning `None` (a truly empty store still returns `None`) (#37).
- Connection loss is classified by exception type (not loose message substrings), so a genuine query/data error never triggers a spurious reconnect or fallback (#37).

### Added
- Write-through markdown mirror: every memory write is also written to a human-readable `.solomon/memory-mirror/<kind>/<id>.md` (frontmatter `id, kind, created_at, synced`), and a write never raises solely because the DB is down (#35).
- Idempotent `reconcile()` (client-minted id + UPSERT) replays unsynced records to SurrealDB on recovery; it runs automatically at memory-up / session start (best-effort, bounded) and on demand via the new `solomon-harness memory sync` command (#35).
- `healthcheck` surfaces the count of pending (unsynced) memory records (#35).
- ADR-0007 records the memory-resilience model (reconnect-then-fallback + write-through mirror + reconcile).

## [0.3.1] - 2026-06-28

### Changed
- Completed epic #6: the `software_architect` and `sre` role-core skills are brought to the canonical depth standard (#52). This corrects the earlier note that both already met the bar — 14 role-core skills were below it and are now at reference depth (named standards, worked examples, `## Common pitfalls`, `## Definition of done`), with the three meta/scope files reframed as single-concern skills rather than restating shared rules.
- `PLAN.md` is now per-branch local state (gitignored): `/solomon-start` writes it for the branch in flight and it is never committed, ending the recurring concurrent-branch conflict on it (#52).

### Added
- `scripts/check-skill-depth.py`: a mechanical gate asserting every non-shared role-core skill is at least 600 words and closes with `## Common pitfalls` and `## Definition of done`, with unit tests.

### Fixed
- The test suite is now hermetic and worktree-safe (#32), and a regression guard locks the hermeticity property in (#36).

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
