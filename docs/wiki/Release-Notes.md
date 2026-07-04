# Release Notes & Version History

Solomon Harness enforces a milestone-gated release standard. Version tags are cut automatically upon milestone closure, with version numbers computed from Conventional Commits.

---

## Recent Releases

For a living, complete list of all delivered issues and pull requests, refer directly to the **[Delivered Issues Log](Delivered)**.

### v0.11.0 (2026-06-29)
* **Cockpit Per-User Velocity:** Added the throughput number to the cockpit — per-person delivery velocity aggregated across projects (slice 3a).
* **Synthetic Tracking Row Close-Out:** Reconcile now closes synthetic RAID/follow-up tracking rows once their parent issue or PR resolves.

### v0.10.0 (2026-06-29)
* **Session-Start Resume Digest:** The session-start hook now checks memory for pending tasks and prints an enumerated options card for Claude Code and the Gemini CLI.

### v0.9.0 (2026-06-29)
* **Multi-Model Memory Layer:** Brought the SurrealDB store to genuinely multi-model — graph edges, timeseries metrics, and vector search — and closed a set of structural spec-audit gaps.
* **External Skill Fetching:** Added fetching and adapting an external skill into the best-fit agent, with SHA pinning and security guards.

### v0.8.0 (2026-06-29)
* **Canonical Issue Status:** Fixed merges not writing the delivered issue's terminal status back to memory, so the resume digest and cockpit no longer diverge from GitHub.
* **CI Pipeline Green:** Fixed the `uv` dependency group and a batch of `mypy` errors that had left CI red on `main`.
* **Worktree Teardown Repair:** Fixed stray `core.worktree`/`core.bare` config left behind by worktree teardown, which had corrupted the main checkout.

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

### 3. Wiki & Documentation Sync
Publishing a release does not run the wiki sync by itself. `scripts/wiki-sync.sh` is a
manual step in the `/solomon-release` workflow (see `docs/solomon-workflow.md` and
`.claude/commands/solomon-release.md`): after the release tag is cut, the workflow
refreshes `docs/wiki/Code-Overview.md`, appends the shipped issues to
`docs/wiki/Delivered.md`, renders the per-release wiki page, and then runs
`scripts/wiki-sync.sh` to push `docs/wiki/` to the GitHub wiki. Neither `ci.yml` nor
`release.yml` invokes it — CI only cuts the tag and publishes the GitHub Release.

> [!IMPORTANT]
> Because release versions are derived programmatically from the Git log, manually editing version tags or writing custom release version numbers is prohibited. Version control is fully managed by the CI release runner.
