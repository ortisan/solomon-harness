# Release Notes & Version History

Solomon Harness enforces a milestone-gated release standard. Version tags are cut automatically upon milestone closure, with version numbers computed from Conventional Commits.

---

## Recent Releases

For a living, complete list of all delivered issues and pull requests, refer directly to the **[Delivered Issues Log](Delivered)**.

### v0.7.0 (2026-06-29)
* **Cockpit UI Shell:** Introduced the SPA cockpit shell, a unified read API, and a visual single-project dashboard.
* **Coordinated Agent Audits:** Equipped the `practice_curator` with fleet-sweep capabilities to propose bounded improvements for individual agents.
* **Git Worktree Isolation:** Strengthened the worktree branch lifecycle for headless development.

### v0.6.0 (2026-06-29)
* **Educational Psychologist Agent:** Added a specialized agent focused on instructional design and cognitive load management.
* **Legacy Modernization Pipeline:** Added the `legacy_modernizer` specialist to sequence code migrations.

### v0.5.0 (2026-06-29)
* **SurrealDB Memory Enhancements:** Fixed memory leaks and connection drop-outs during long-running tasks.
* **Research Analyst Agent:** Added a research agent for fundamental qualitative analysis.
* **Milestone-Gated Releases:** Established the trunk-based release policy gate.

---

## Release Policy & Versioning

The harness employs strict rules to ensure releases are stable, traceable, and free from human error:

### 1. Milestone-Gated releases
No release is cut directly from a single Pull Request. Instead, issues roll up to milestones (e.g. `v0.7.0`). A release tag is cut only when:
* The milestone has **0 open issues**.
* The automated CI build is green on `main`.

### 2. Calculated Versioning (SemVer)
Version numbers are computed programmatically from the Git history since the last tag:
* `BREAKING CHANGE` or `feat` bumps the **Minor** version (during `0.x` pre-releases) or **Major** version (post-1.0).
* `fix`, `perf`, `refactor` bumps the **Patch** version.
* `chore`, `docs`, and `test` changes are non-releasable.

### 3. Automated Wiki & Documentation Sync
Every release run automatically triggers `scripts/wiki-sync.sh` to update the wiki files directly from the repository's `docs/wiki/` directory.

> [!IMPORTANT]
> Because release versions are derived programmatically from the Git log, manually editing version tags or writing custom release version numbers is prohibited. Version control is fully managed by the CI release runner.
