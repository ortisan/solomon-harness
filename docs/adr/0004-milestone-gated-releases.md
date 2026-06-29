# ADR-0004: Milestone-gated SemVer releases on trunk

- Status: accepted
- Date: 2026-06-28
- Deciders: scrum_master, software_architect, sre, product_owner
- Issue: #34

> Numbering note: this ADR is numbered 0004 to avoid collisions with ADRs in
> flight on unmerged branches (loop-safety uses 0001-loop, cockpit uses 0002 and
> 0003). The final number may be reconciled when these branches merge; if so,
> update the cross-references and the `save_decision` record accordingly.

## Context and problem statement

solomon-harness is a Claude Code / Gemini agent harness (a Python package plus the
`/solomon-*` delivery workflows). It is a single-maintainer, trunk-based repo:
slices squash-merge into `main`, with no `develop` branch and no long-lived
`release/*` or `hotfix/*` branches. Distribution is a git tag plus a GitHub
Release of the source tree — it is **not** published to PyPI (`pyproject` carries
`[tool.uv] package = false`; consumers check out the tag or download the Release
archive).

Releasing was governed by several rules that contradicted each other, and the
machinery to execute any of them was missing:

- **Per-PR skill vs. epic-completion policy.** The release skill behaved as
  though every merged PR could cut a release, while the standing policy said a
  tag is cut "at epic completion." A reader could not tell whether one merge
  releases or not.
- **Develop-branch bug.** Release tooling assumed a `develop` branch and
  release/hotfix branches that do not exist in this trunk-only repo, so the
  documented flow could not be followed as written.
- **release.yml published-manual-vs-draft-auto race (#34).** The release skill
  ran `gh release create` by hand while a workflow also created a Release, so a
  manually published Release raced an auto-created draft for the same tag —
  producing duplicate or conflicting Releases.
- **No milestones existed.** The policy spoke of releasing at epic completion,
  but there was no milestone object to anchor "scope complete," so there was no
  observable, automatable release trigger.

The forces: keep the trunk-only model and its single human release gate; make the
version impossible to drift across `pyproject`, the tag, and the CHANGELOG; give
the autonomous loop something safe it may propose without ever publishing; and
fit a tag-release library that has no running service and is not on PyPI.

## Decision drivers

- Coherent, reviewable release scope — a release bundles a milestone's worth of
  work, not the noise of every individual merge.
- No three-way version drift — the tag, `pyproject.version`, and the top
  CHANGELOG heading are structurally forced to agree.
- A single, explicit human release gate is preserved.
- Trunk-only simplicity is preserved — no `develop`, no long-lived release or
  hotfix branches.
- Headless / loop safety — the autonomous loop may *propose* a release but can
  never publish one unattended.
- Reversibility — published tags are immutable; a bad release is fixed by rolling
  forward, not by re-tagging.
- Fit for a tag-release library with no running service and no PyPI artifact.

## Considered options

- **A. Event-driven, milestone-gated SemVer on trunk** (chosen): a tag is cut
  when a GitHub milestone reaches zero open issues with CI green; the version is
  computed from Conventional Commits; CI owns tag and publish; an ephemeral
  `chore/release-vX.Y.Z` prep PR is the human gate.
- **B. Continuous per-merge auto-release**: every merge to `main` that contains a
  releasable commit cuts a tag.
- **C. Fixed weekly release train**: a scheduled job cuts whatever has
  accumulated on `main` each week.
- **D. Git Flow release branches**: cut a long-lived `release/*` branch, stabilize
  it, then tag and back-merge.

### Scoring against the drivers

Scored + (satisfies), o (partial), - (fails); the chosen option dominates on
scope coherence, human gate, and trunk simplicity without losing the rest.

| Option | Coherent scope | No version drift | Human gate | Trunk-only | Loop-safe | Library fit |
| --- | --- | --- | --- | --- | --- | --- |
| A. Milestone-gated (chosen) | + | + | + | + | + | + |
| B. Continuous per-merge | - | o | - | + | - | o |
| C. Weekly train | o | o | o | + | o | o |
| D. Git Flow release branch | + | o | + | - | o | - |

- **B** releases on every merge, so it cannot bundle a coherent scope, removes the
  deliberate human gate, and would have the loop publishing unattended — the exact
  hazard #34 exposed.
- **C** decouples a release from "scope done": it ships half-finished milestones
  or empty windows on a clock, and still needs separate drift and gate machinery.
- **D** delivers coherent scope and a clear gate, but it reintroduces a
  long-lived branch and back-merges — directly reversing the trunk-only / no-develop
  decision and re-creating the develop-branch class of bug we are removing.

Milestone-gated won because it ties a release to a meaningful unit of completed
work (the milestone), keeps the trunk-only model, gives the loop a non-mutating
action to propose, and makes version drift structurally impossible.

## Decision outcome

Chosen: **Option A — adopt event-driven, milestone-gated SemVer releases on
trunk.** This **clarifies and strengthens** the prior "tag at epic completion"
decision; it explicitly does **not** overturn trunk-only / no-develop. It was
chosen over continuous per-merge auto-release (a), a fixed weekly release train
(b), and Git Flow release branches (c). The full policy is the seven sections
below.

### 1. Versioning — SemVer, computed, never hand-picked

The bump is derived from Conventional Commits in
`git log <last-tag>..main --first-parent` (highest wins).

- Pre-1.0 (current 0.x): a window containing any `feat` OR a `BREAKING CHANGE`
  bumps MINOR; otherwise a window with `fix`/`perf`/`refactor`/`revert` bumps
  PATCH; a window of only `chore`/`docs`/`ci`/`test`/`style`/`build` is
  non-releasable (no tag).
- Post-1.0: `BREAKING CHANGE` -> MAJOR, `feat` -> MINOR, `fix`/`perf` -> PATCH.
- MAJOR is reserved for breaking a harness public contract: the
  `solomon-harness` CLI surface, the `.agent/config.json` schema, the
  `solomon-memory` MCP tool signatures, or the `agents/<name>/` layout.
- A published tag is immutable — never moved. A bad release is superseded by the
  next PATCH (a revert PR that ships forward), never by re-tagging.

### 2. Release criterion — a closed milestone, never a per-PR event

A tag is cut when a GitHub milestone reaches 0 open issues with CI green on
`main`. Never per-PR. A single PR merge only closes its issue and burns down its
milestone. Every issue rolls up to exactly one milestone (epics + thematic):

- EPIC milestone: titled with its SemVer minor (`v0.4.0`, `v0.5.0`) — the title
  *is* the version. Closing it (`open_issues == 0`, CI green) cuts the MINOR.
- THEME / hardening milestone: titled by theme (`memory-durability`,
  `test-ci-hardening`, `worktree-lifecycle`); closing it cuts a PATCH whose
  version is computed at cut time (theme milestones are not version-titled
  because several may batch).
- `/solomon-refine` creates the milestone when it refines an epic's first child
  (or the first issue of a theme) and assigns every Ready child; a parentless
  bug/chore goes to the nearest theme milestone.
- On-demand escape valve: `solomon-harness release prep` may cut a PATCH for an
  accumulated batch without waiting for a milestone to fully close.

### 3. Branch model — trunk-only

Do not restore `develop`; do not fatten a release branch. The only release branch
is an ephemeral `chore/release-vX.Y.Z` prep branch that lives minutes: `release
prep` opens it carrying the `pyproject` bump plus the CHANGELOG section; the human
merges that PR (that merge **is** the human release gate); CI then tags and
publishes; the branch is deleted. Revisit fattening only under a concrete trigger:
external consumers pin old tags and need backports; a second maintainer works
vNext while vCurrent stabilizes; or a deployed running service appears.

### 4. Tag / publish ownership — CI is the single owner

On the prep-PR merge to `main`, the resulting `main` push carries a
`chore(release): vX.Y.Z` commit; the release workflow creates and pushes the
annotated tag and publishes (`draft: false`) the GitHub Release with the CHANGELOG
section as notes. The manual `gh release create` is **removed** from the release
skill (it caused the published-manual vs. draft-auto race, #34). CI uses the
default `GITHUB_TOKEN` with `contents: write` to push a tag (tags are not
branch-protected) — no PAT, and CI never pushes a commit to protected `main`.

### 5. Fail-closed invariant

`solomon-harness release check` asserts (and CI enforces on every
`chore/release-*` PR): `tag == pyproject.version ==` the top `CHANGELOG.md`
heading (Keep a Changelog, carrying the cut date) AND the tag does not already
exist. Tests and ruff are a separate gate (the `ci.yml` suite), not part of
`release check`. Humans never hand-edit `pyproject.version` or add a CHANGELOG
heading; `release prep` writes them, and the `pr-guards` job rejects any
non-release PR that touches them — which structurally prevents three-way version
drift.

### 6. CLI surface — `solomon-harness release plan|prep|check`

- `release plan` (read-only, headless-safe): compute the SemVer bump from the
  commits on trunk since the last tag and print the planned version plus the
  rendered CHANGELOG section. It computes the version only; the milestone-at-zero
  gate is a board check the `/solomon-release` skill (or the loop) performs via
  `gh`. Safe to run unattended — the loop may *propose* a release with it.
- `release prep` (opens a PR only, never merges): create `chore/release-vX.Y.Z`,
  write the computed `pyproject` bump plus the CHANGELOG section, commit
  `chore(release): vX.Y.Z`, open the PR, then STOP.
- `release check` (read-only gate, fail-closed): the invariant in section 5;
  non-zero exit on any mismatch.

### 7. Readiness gate — a library readiness gate, not an SLO/canary PRR

The canary / blue-green / SLO-burn / on-call Production Readiness Review does not
apply to a tag-release library with no running service. The release gate is a
**library readiness gate**: tests + ruff green on `main`; `python -c "import
solomon_harness"` succeeds; the `solomon-harness` console script runs; `release
check` passes. Carry forward only the reversibility kernel from progressive
delivery: immutable, never-moved tags; rollback = a revert PR that auto-ships the
next patch; backward-compatible expand/contract migrations for the SurrealDB /
SQLite memory store.

### Consequences

- Positive: a release maps to a completed, reviewable unit of work (a milestone)
  rather than to incidental merges; the version cannot drift across the tag,
  `pyproject`, and the CHANGELOG because one command writes all three and a
  fail-closed check guards them; the single human release gate is the prep-PR
  merge; CI is the sole tag/publish owner, which closes the #34 manual-vs-auto
  race; the trunk-only model is kept intact, so the develop-branch class of bug
  is removed; the autonomous loop gains a safe, non-mutating action (`release
  plan`) it may propose without ever publishing.
- Negative: releasing now depends on milestone hygiene — issues must be assigned
  to exactly one milestone or scope drifts and the trigger never fires; the
  computed-bump and fail-closed-check machinery is more upfront tooling than a
  per-merge tag; the on-demand `release prep` escape valve is the only relief if a
  milestone stalls near, but not at, zero open issues; mis-titled epic milestones
  (the title must equal the SemVer minor) can mislead, so titling discipline
  matters.
- Follow-ups: cross-PR with the loop-safety floor (PR #45) — the loop autonomy
  ladder (`LOCKED_STAGES` / `AUTOMATION_ALLOWED_STAGES` / `loop_policy.py`) lives
  on that not-yet-merged branch, not on `main`, so do not reference those symbols
  as existing on `main`. Once #45 merges: add the non-mutating `release plan` and
  `release prep` to `AUTOMATION_ALLOWED_STAGES`, keep tag/publish human- and
  CI-gated, and fix the headless human-gate ordering in
  `loop_policy.decide_stage`. Branch-model fattening (a `release/*` branch) stays
  out of scope until a concrete trigger appears (external consumers pinning old
  tags, a second maintainer on vNext, or a deployed running service).

## More information

This decision clarifies and strengthens the prior "tag at epic completion" record
and does not overturn the trunk-only / no-develop decision. It supersedes the
per-PR behavior of the release skill and the manual `gh release create` step that
caused #34. Implemented by the `solomon-harness release plan|prep|check` CLI
surface, the `release.yml` workflow (sole tag/publish owner), and the
`/solomon-release` workflow; milestones are created by `/solomon-refine`. Recorded
in the project memory via `save_decision`.
