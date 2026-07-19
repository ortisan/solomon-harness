# solomon-harness Release Policy

Status: canonical. This document is the single source of truth for how
solomon-harness is versioned, milestoned, branched, tagged, and published. Where
any skill, workflow, or README disagrees with this file, this file wins and the
other artifact is the bug.

It exists because the gap is real: the `product_owner` `roadmapping_and_release_planning`
skill covers outcome roadmaps and milestone intent, and the `sre`
`release_engineering_and_progressive_delivery` skill covers rollout mechanics for
running services. Neither one owns the tag, SemVer, and CHANGELOG mechanics for a
installable library. That is this document.

## What solomon-harness is, for release purposes

solomon-harness is a Claude, AGY, and Codex agent harness: a Python package plus
the `/solomon-*` delivery workflows. Two facts about distribution drive every
rule below.

- It is an installable package. `uv build` produces an sdist and wheel whose
  `solomon_harness/_payload` contains the explicit installation allowlist. Source
  checkout and wheel installs produce the same `.agents/solomon` manifest. PyPI
  publication is not currently part of the release flow: the authoritative
  release remains an immutable git tag plus a published GitHub Release, from
  which consumers install the wheel or source archive.
- It is trunk-based. Slices squash-merge into `main`. There is no `develop` branch
  and there are no long-lived `release/*` or `hotfix/*` branches.

Because there is no running service and no deployable artifact beyond the tagged
source, the release gate is a library readiness gate, not a production readiness
review. See "Library readiness gate" below.

## The release criterion

A tag is cut when a GitHub milestone reaches zero open issues with CI green on
`main`. Never per pull request. Merging a single PR closes its issue and burns down
its milestone; it does not release anything.

Milestones are the release-scope object, and every issue rolls up to exactly one
milestone. Two kinds exist.

- Epic milestone. Titled with its SemVer minor: `v0.4.0`, `v0.5.0`. The title is the
  version. Closing it (open issues == 0, CI green) cuts that minor.
- Theme / hardening milestone. Titled by theme: `memory-durability`,
  `test-ci-hardening`, `worktree-lifecycle`. Closing it cuts a patch whose version is
  computed at cut time. Theme milestones are not version-titled because several may
  batch into one patch.

`/solomon-refine` owns milestone creation. It creates the milestone when it refines
an epic's first child (or the first issue of a theme) and assigns every Ready child
to it. A parentless bug or chore goes to the nearest theme milestone.

Escape valve: `solomon-harness release prep` may cut a patch for an accumulated batch
without waiting for a milestone to fully close. Use it for an urgent fix or to drain
a backlog of small merged fixes; the normal path is still milestone-driven.

## Versioning: SemVer, computed never hand-picked

The version is Semantic Versioning, and the bump is derived from the Conventional
Commit types in the window since the last tag. Nobody picks a number by feel.

Compute the window with first-parent history so each squash-merge counts once:

```bash
git log "$(git describe --tags --abbrev=0)..main" --first-parent --pretty=%s
```

Read the Conventional Commit type prefix of each subject line and a trailing
`BREAKING CHANGE:` footer where present, then take the highest-ranked bump.

Pre-1.0 (the current 0.x series):

- The window contains any `feat` or any `BREAKING CHANGE` -> bump MINOR.
- Else the window contains a `fix`, `perf`, `refactor`, or `revert` -> bump PATCH.
- A window of only `chore`, `docs`, `ci`, `test`, `style`, or `build` is
  NON-RELEASABLE. No tag is cut. This is a normal, expected outcome for a milestone
  that was pure housekeeping.

Pre-1.0 deliberately folds breaking changes into a MINOR rather than a major bump:
under SemVer, 0.x makes no stability promise, so a 0.x breaking change does not earn
a 1.0. The 1.0 line is crossed on purpose, not by accident of a commit footer.

Post-1.0 (for when the project gets there):

- `BREAKING CHANGE` -> MAJOR.
- `feat` -> MINOR.
- `fix` or `perf` -> PATCH.

MAJOR is reserved. Post-1.0, a MAJOR bump means a deliberate break of a harness public
contract, and only these count as public contracts:

- the `solomon-harness` CLI surface (commands, subcommands, flags, exit codes);
- the `.agents/solomon/config/project.json` schema;
- the `solomon-memory` MCP tool signatures (the tool names and their parameters);
- the canonical `.agents/solomon` layout and ownership-manifest schema;
- the source `agents/<name>/` layout and the promised Claude/AGY/Codex capability
  parity compiled from it.

A change that does not alter one of these is not a MAJOR, regardless of how it feels.

### Worked bump example

The last tag is `v0.2.0`. The window `v0.2.0..main --first-parent` contains, oldest to
newest:

```
feat(loop): single-driver lock, portable gate, run-log and activity feed
feat(loop): governed autonomy ladder, denylist and kill-switch
fix(memory): retry SurrealDB signin before falling back to SQLite
docs(adr): record the single-driver lock decision
chore(release): v0.2.0   <- excluded; it is at or before the tag boundary
```

The highest-ranked type in the window is `feat`. Pre-1.0 rule: any `feat` bumps the
MINOR. The computed version is `v0.3.0`. The `fix` and `docs` entries do not change
the outcome; they only matter when no `feat` or `BREAKING CHANGE` is present.

A second window containing only `fix(memory): ...` and `chore(ci): ...` would compute
`v0.2.1` (the `fix` forces a PATCH; the `chore` alone would have been non-releasable).

## Branch model: trunk-only

Do not restore `develop`. Do not fatten a release branch. `main` is the trunk; every
slice squash-merges into it behind CI and review.

The only release branch is an ephemeral `chore/release-vX.Y.Z` prep branch that lives
for minutes:

1. `release prep` creates `chore/release-vX.Y.Z` carrying the `pyproject.toml` version
   bump and the new `CHANGELOG.md` section.
2. The human merges that PR. That merge is the human release gate.
3. CI tags and publishes from the resulting `main` push.
4. The branch is deleted.

Revisit fattening the branch model only under a concrete trigger, never preemptively:

- external consumers pin old tags and need backports;
- a second maintainer works vNext while vCurrent stabilizes;
- a deployed running service appears (today there is none).

Absent one of those, trunk-only stands.

## Tag and publish ownership: CI is the single owner

CI owns the tag and the GitHub Release. Humans never run `gh release create` by hand;
that manual step is removed from the `solomon-release` skill because it caused a
published-manual versus draft-auto race (issue #34). The flow:

1. The human merges the `chore/release-vX.Y.Z` prep PR into `main`. The merge lands a
   single `chore(release): vX.Y.Z` commit on `main`.
2. The release workflow triggers on that `main` push. It reads the version from
   `pyproject.toml`, creates and pushes the annotated tag `vX.Y.Z`, and publishes
   (`draft: false`) the GitHub Release using the matching `CHANGELOG.md` section as the
   release notes.

CI authenticates with the default `GITHUB_TOKEN` granted `contents: write`. It pushes a
tag, and tags are not branch-protected, so no personal access token is needed. CI never
pushes a commit to protected `main`; the only commit that reaches `main` is the one the
human merged. The token's reach is exactly "create a tag and a Release," nothing more.

This replaces the previous tag-triggered draft-only workflow. The trigger moves from
"a tag was pushed" to "a release commit landed on main," and the same job both creates
the tag and publishes the Release, so there is one owner and no manual race.

## Fail-closed invariant

`solomon-harness release check` is a read-only gate that asserts, and CI enforces on
every `chore/release-*` PR:

- `git tag` to be created == `pyproject.toml` version == the top `CHANGELOG.md` heading;
- the `CHANGELOG.md` top heading carries a date in Keep a Changelog form
  (`## [X.Y.Z] - YYYY-MM-DD`; `release prep` stamps the cut date);
- the tag does not already exist.

`check` exits non-zero on any mismatch, so a drifted release cannot proceed. Tests and
`ruff` are a separate gate (the `ci.yml` suite and the library readiness gate), not part
of `release check` — `check` is purely the version/tag/CHANGELOG consistency invariant.

`check` only proves internal agreement (tag == pyproject == CHANGELOG); it says nothing
about whether the window those three still describe is the right one. A `feat`/`fix`
commit that lands on `main` after the prep PR opens but before it merges would pass
`check` (the prep PR's own three copies still agree with each other) while silently
missing from the changelog and the version it computed. `release verify-window` closes
that gap: right before CI tags, it re-runs the same commit-window computation `plan`
uses — `<last-tag>..HEAD --first-parent` on the just-pushed `main` — and fails loudly if
that disagrees with what `pyproject.toml`/`CHANGELOG.md` already declare, even when the
bump level (and so the version number) happens not to change. Better to abort the tag
than publish one with a stale changelog.

Humans never hand-edit `pyproject.toml` `version` and never add a `CHANGELOG.md`
heading by hand. `release prep` writes both. A complementary CI check rejects any
non-release PR that touches `pyproject.toml` `version` or adds a `CHANGELOG.md` heading.
Together these structurally prevent three-way version drift: the only place a version is
written is `release prep`, and the only place it is published is CI, and `check` proves
the three copies agree before either side acts.

## CLI surface

`solomon-harness release plan | prep | check | verify-window`.

- `release plan` — read-only, headless-safe. Compute the SemVer bump from the commit
  window on trunk since the last tag (`<last-tag>..main --first-parent`) and print the
  planned version plus the rendered CHANGELOG section. It computes the version only; it
  does not query GitHub — the milestone-at-zero gate is a board check done by the
  `/solomon-release` skill (or the loop) via `gh`. It mutates nothing, so the loop may
  run it unattended to propose a release.
- `release prep` — opens a PR, never merges. Create `chore/release-vX.Y.Z`, write the
  computed `pyproject.toml` bump and the `CHANGELOG.md` section, commit
  `chore(release): vX.Y.Z`, open the PR, then stop. The human takes it from there.
- `release check` — the fail-closed gate above. Read-only; non-zero exit on any
  mismatch. Runs locally and in CI on every `chore/release-*` PR.
- `release verify-window` — the merge-time recompute above. Read-only; non-zero exit
  when the commit window recomputed against the current trunk `HEAD` disagrees with the
  declared version or CHANGELOG. Runs in CI's `release` job, right before it tags.

The split is the safety boundary: `plan` and `prep` can be automated because they only
read or open a PR; merging, tagging, and publishing stay human-and-CI-gated.

## Library readiness gate

A tag-release library with no running service has no canary, no blue-green, no
SLO-burn alert, and no on-call rotation, so the `sre` production readiness review does
not apply to a solomon-harness release. The release gate is a library readiness gate:

- tests and `ruff` are green on `main`;
- `python -c "import solomon_harness"` succeeds;
- the `solomon-harness` console script runs;
- `uv build` produces an sdist and wheel, and a no-dependency wheel smoke install
  can run `init` with the same managed manifest as source mode;
- the installed Claude, AGY, and Codex adapters expose the same specialists,
  workflows, hooks, MCP server, and headless-engine capability;
- `release check` passes.

Carry forward only the reversibility kernel from progressive delivery, the part that is
real for a library:

- tags are immutable and never moved;
- rollback is a revert PR that auto-ships the next patch (see below);
- memory-store schema changes are backward-compatible expand/contract migrations, so a
  consumer on the old tag and one on the new tag both read the SurrealDB-primary /
  SQLite-fallback store without a break.

## Rollback: immutable tags, revert forward

A published tag is immutable. It is never moved and never re-pointed. A bad release is
superseded by the next PATCH that ships forward, never by re-tagging.

To roll back: open a revert PR on `main` that undoes the bad change. It carries a
`revert:` (or `fix:`) commit, so the next `release plan` computes a PATCH, and the
normal `prep` -> human merge -> CI tag-and-publish flow ships it. The bad tag stays in
history as a record; the fix is a new, higher tag. There is no force-push, no deleted
tag, no moved Release.

## End-to-end runbook

For an epic milestone `v0.5.0` reaching zero open issues with CI green (v0.4.0 already
shipped the memory-resilience release, so the cockpit epic is the next minor):

1. Confirm the `v0.5.0` milestone has zero open issues with CI green on `main` (a board
   check via `gh`), then `solomon-harness release plan` computes the bump from
   `<last-tag>..main --first-parent` and prints `v0.5.0` and the CHANGELOG section. Safe
   to have proposed by the loop.
2. `solomon-harness release prep` — opens `chore/release-v0.5.0` with the
   `pyproject.toml` bump and the CHANGELOG section, commit `chore(release): v0.5.0`.
3. CI on the PR runs `release check` (version == tag == CHANGELOG, tag absent) plus the
   `ci.yml` tests + ruff suite and, for non-release PRs, the version/CHANGELOG drift guard.
4. The human merges the prep PR into `main`. That is the release authorization.
5. The release workflow triggers on the `main` push, creates and pushes the annotated
   `v0.5.0` tag with `GITHUB_TOKEN`, and publishes the GitHub Release from the CHANGELOG
   section.
6. The ephemeral branch is deleted; the milestone is closed; the release is recorded in
   project memory via `save_release`.

For a theme milestone or an on-demand batch the flow is identical except the version is
computed at cut time rather than read from the milestone title.

## Follow-up: the loop autonomy ladder

The loop autonomy ladder (`LOCKED_STAGES`, `AUTOMATION_ALLOWED_STAGES`, and
`loop_policy.decide_stage`) lives on the not-yet-merged `feature/loop-safety-floor`
branch (PR #45), not on `main`. Do not reference those symbols as if they exist on
`main` today.

Once PR #45 merges, two changes wire this policy into the loop:

- add the non-mutating `release plan` and `release prep` to `AUTOMATION_ALLOWED_STAGES`
  so the loop may propose and prepare a release, while tag and publish stay human- and
  CI-gated;
- fix the headless human-gate ordering in `loop_policy.decide_stage` so a headless run
  stops at the human release gate instead of stepping past it.

Until then, treat `release plan` and `release prep` as operator-invoked.

## Related references

- `product_owner` / `roadmapping_and_release_planning` — milestone and roadmap intent,
  theme -> epic -> story hierarchy. This document is the version/tag/CHANGELOG mechanics
  that skill defers to.
- `sre` / `release_engineering_and_progressive_delivery` — rollout mechanics for running
  services. Only its reversibility kernel applies here.
- `docs/solomon-workflow.md` — where the release stage sits in the delivery lifecycle.
- `CHANGELOG.md` — Keep a Changelog, the published source of release notes.
