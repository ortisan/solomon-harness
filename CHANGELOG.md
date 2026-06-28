# Changelog

All notable changes to solomon-harness are recorded here. The format follows Keep a Changelog, and the project adheres to Semantic Versioning.

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
