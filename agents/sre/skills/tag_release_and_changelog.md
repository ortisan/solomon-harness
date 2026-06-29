# Tag-Release and Changelog Mechanics

Ship solomon-harness as an immutable git tag plus a published GitHub Release of the source tree, never to PyPI. This is the release mechanics for a source-distributed library: `pyproject.toml` carries `[tool.uv] package = false`, so consumers checkout the tag or download the Release archive rather than `pip install`ing it. The version is computed from Conventional Commits (never hand-picked), the cut is gated on a GitHub milestone reaching zero open issues with CI green, the model is trunk-only with one ephemeral prep branch, and CI is the single owner of the tag and the publish. The canonical, authoritative statement of this policy is `docs/release-policy.md`; this skill is the operating procedure that implements it. Where the two ever diverge, `docs/release-policy.md` wins.

## Versioning: SemVer computed, never hand-picked

The bump is derived from the Conventional Commits in the window since the last tag, highest wins. Never type a version into `pyproject.toml` by hand.

```bash
LAST=$(git tag --list 'v*' --sort=-v:refname | head -n1)   # e.g. v0.3.1
git log "$LAST..main" --first-parent --pretty='%s'          # the release window
```

`--first-parent` keeps the window to the squash-merge commits that landed on main, so one merged PR is one line and feature-branch noise is excluded.

Pre-1.0 (the project is at `0.x` now) classification of the window:

- Any `feat` **or** a `BREAKING CHANGE` (`feat!:`, `fix!:`, or a `BREAKING CHANGE:` footer) bumps the **MINOR**: `0.3.1 -> 0.4.0`.
- Else, any `fix` / `perf` / `refactor` / `revert` bumps the **PATCH**: `0.3.1 -> 0.3.2`.
- A window of only `chore` / `docs` / `ci` / `test` / `style` / `build` is **non-releasable**: no tag is cut.

Post-1.0 the standard SemVer mapping applies: `BREAKING CHANGE -> MAJOR`, `feat -> MINOR`, `fix`/`perf -> PATCH`. MAJOR is reserved for breaking a harness public contract — the `solomon-harness` CLI surface, the `.agent/config.json` schema, the `solomon-memory` MCP tool signatures, or the `agents/<name>/` layout. Nothing else justifies a major bump.

## Keep a Changelog discipline

`CHANGELOG.md` follows Keep a Changelog 1.1.0. Each released version is a `## [X.Y.Z] - YYYY-MM-DD` heading (today's date, the cut date) with `### Added` / `### Changed` / `### Fixed` / `### Notes` subsections written in the project's flat, emoji-free voice. The top heading is the source of truth for the release notes — CI publishes that exact section as the GitHub Release body. Humans never add a heading by hand; `release prep` renders it from the commit window, and the fail-closed check below rejects any non-release PR that touches it.

## The release criterion: milestone-gated, never per-PR

A tag is cut when a GitHub milestone reaches **0 open issues with CI green on main** — never on a single PR merge. A merged PR only closes its issue and burns down its milestone. Every issue rolls up to exactly one milestone:

- **Epic milestone** — titled with its SemVer minor (`v0.4.0`, `v0.5.0`); the title *is* the version. Closing it (open_issues == 0, CI green) cuts that MINOR. `release plan` still recomputes the bump from commits and asserts it agrees with the title: an epic titled `v0.4.0` whose window contains no `feat` is mis-scoped, not a release.
- **Theme / hardening milestone** — titled by theme (`memory-durability`, `test-ci-hardening`, `worktree-lifecycle`), not by version, because several may batch. Closing it cuts a PATCH whose version is computed at cut time.

`/solomon-refine` creates the milestone when it refines an epic's first child (or a theme's first issue) and assigns every Ready child; a parentless bug or chore lands on the nearest theme milestone. On-demand escape valve: `solomon-harness release prep` may cut a PATCH for an accumulated batch without waiting for a milestone to fully close.

## Trunk-only branch model and the ephemeral prep branch

Slices squash-merge into `main`. There is **no `develop`** and there are **no long-lived `release/*` or `hotfix/*` branches** — do not restore them. The only release branch is an ephemeral `chore/release-vX.Y.Z` that lives minutes:

1. `solomon-harness release prep` creates `chore/release-vX.Y.Z`, writes the computed `pyproject.toml` bump and the rendered `CHANGELOG.md` section, commits `chore(release): vX.Y.Z`, opens the PR, and stops. It never merges.
2. A **human merges that PR** — that merge is the release gate (a single-maintainer repo blocks self-approval, so a person authorizes it deliberately).
3. CI tags and publishes off the resulting main push, then the branch is deleted.

Revisit a fatter branch model only under a concrete trigger: external consumers pin old tags and need backports, a second maintainer works vNext while vCurrent stabilizes, or a deployed running service appears. None of those hold today.

## CLI surface: `release plan | prep | check`

- **`release plan`** — read-only and headless-safe. Detects the target (a milestone at/near 0 open issues, or an on-demand batch), computes the SemVer bump from the commit window, and prints the planned version plus the rendered CHANGELOG section. Safe to run unattended, so the loop may *propose* a release with it.
- **`release prep`** — opens a PR only, never merges (the prep-branch steps above).
- **`release check`** — the read-only, fail-closed gate below; non-zero exit on any mismatch.

## The fail-closed `release check` invariant

`solomon-harness release check` asserts, and CI enforces on every `chore/release-*` PR, all of:

- `git` tag-to-be == `pyproject.toml` `version` == the top `CHANGELOG.md` `## [X.Y.Z]` heading (Keep a Changelog, dated today);
- the tag does **not** already exist (`git rev-parse vX.Y.Z` must fail) — published tags are immutable and never re-cut;
- `pytest` and `ruff check` are green.

A second CI guard runs on every non-`chore/release-*` PR and rejects any diff that touches `pyproject.toml`'s `version` line or adds a `CHANGELOG.md` heading. Together these structurally prevent three-way version drift: humans never hand-edit the version or the changelog heading; only `release prep` writes them.

```yaml
# .github/workflows/version-guard.yml — reject hand-edits on ordinary PRs
- name: No manual version or changelog-heading edits outside chore/release-*
  if: ${{ !startsWith(github.head_ref, 'chore/release-') }}
  run: |
    base=origin/${{ github.base_ref }}
    if git diff "$base...HEAD" -- pyproject.toml | grep -qE '^\+version *='; then
      echo "::error::version bumps belong only on chore/release-* (run 'release prep')"; exit 1
    fi
    if git diff "$base...HEAD" -- CHANGELOG.md | grep -qE '^\+## \['; then
      echo "::error::CHANGELOG headings are written by 'release prep', not by hand"; exit 1
    fi
```

## CI is the single tag and publish owner

The manual `gh release create` is removed from the release skill — running it by hand created a published-manual vs. draft-auto race (issue #34). When the prep PR merges, the main push carries the `chore(release): vX.Y.Z` commit and the release workflow does everything: it runs `release check`, creates and pushes the annotated tag, and publishes (`draft: false`) the GitHub Release with the top CHANGELOG section as the notes.

```yaml
# .github/workflows/release.yml — fires when the chore(release) commit lands on main
on:
  push:
    branches: [main]
permissions:
  contents: write          # push the TAG and publish the Release; nothing more
jobs:
  release:
    if: startsWith(github.event.head_commit.message, 'chore(release): v')
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with: { fetch-depth: 0 }
      - run: pipx run uv sync --extra dev
      - run: uv run python -m solomon_harness.cli release check     # fail-closed gate, again, in CI
      - name: Tag and publish
        env: { GH_TOKEN: ${{ secrets.GITHUB_TOKEN }} }
        run: |
          V=v$(grep -m1 '^version' pyproject.toml | cut -d'"' -f2)
          awk '/^## \[/{n++; if(n==2) exit} n==1' CHANGELOG.md > /tmp/notes.md
          git tag -a "$V" -m "$V"
          git push origin "$V"
          gh release create "$V" --target main --title "$V" --notes-file /tmp/notes.md
```

CI uses the default `GITHUB_TOKEN` with `contents: write` to push a **tag** — tags are not branch-protected, so no PAT is needed. CI never pushes a commit to protected `main`; the only commit it ever acts on is the one the human already merged.

## Immutable tags and revert-forward rollback

A published tag is immutable: never `git tag -f`, never `git push --force` a tag, never move or delete one. A bad release is superseded by the **next PATCH that ships forward** — open a revert PR for the offending change, let it merge through the normal gate, and `release prep` will cut `vX.Y.(Z+1)` carrying that revert. Re-tagging would silently change what a pinned consumer downloads; revert-forward keeps every tag a stable, auditable point in history.

## Library readiness gate (no SLO/canary PRR)

This is a tag-released library with no running service, so the canary / blue-green / SLO-burn / on-call Production Readiness Review does not apply. The gate is a **library readiness gate**: `pytest` and `ruff` green on main, `python -c "import solomon_harness"` succeeds, the `solomon-harness` console script runs, and `release check` passes. Carry forward only the reversibility kernel from progressive delivery — immutable never-moved tags, rollback as a revert PR that auto-ships the next patch, and backward-compatible migrations below.

## Memory-store migrations stay backward-compatible

The SurrealDB-primary / SQLite-fallback memory store (`solomon_harness/tools/database_client.py`) evolves by expand/contract so a consumer on an older tag still reads a store written by a newer one, and vice versa during the window. Expand first (add the new field/table, write both, read new-with-old-fallback), release, and only contract (drop the old shape) in a *later* release once no supported tag still writes it. Never couple a destructive `DROP`/`REMOVE FIELD` to the release that stops using it — that breaks revert-forward rollback, because reverting to the prior tag would hit a schema it cannot read.

## Automation boundary (follow-up)

`release plan` and `release prep` are non-mutating to `main` (plan reads; prep only opens a PR), so the loop may propose a release with them, but the tag and publish stay human-gated (the prep-PR merge) and CI-owned. Follow-up, once the loop-safety-floor branch (PR #45) merges: add `release plan` / `release prep` to `AUTOMATION_ALLOWED_STAGES`, keep tag/publish out of it, and confirm the headless human-gate ordering in `loop_policy.decide_stage`. Those autonomy-ladder symbols do not yet exist on `main`; do not reference them as if they do.

## Common pitfalls

- Hand-editing `pyproject.toml` `version` or adding a `CHANGELOG.md` heading on an ordinary feature PR — the version guard rejects it; only `release prep` writes them.
- Cutting a tag per merged PR instead of waiting for the milestone to reach 0 open issues with CI green.
- Picking a version by feel instead of computing it from `git log <last-tag>..main --first-parent`; or dropping `--first-parent` and pulling in feature-branch commits.
- Treating a `chore`/`docs`/`ci`-only window as releasable in the 0.x line — it is non-releasable, no tag.
- Running `gh release create` by hand — that is the issue #34 race; CI is the only publisher.
- Re-tagging or force-pushing a tag to "fix" a release instead of shipping the next PATCH via a revert PR.
- Reusing an epic milestone title as the version when the commit window contains no `feat` (mis-scoped epic), or version-titling a theme milestone (its patch is computed at cut time).
- Restoring a `develop` branch or fattening a `release/*` branch with no concrete trigger (external pin, second maintainer, or running service).
- Wiring CI to push a commit to protected `main`, or reaching for a PAT — pushing the tag with the default `GITHUB_TOKEN` and `contents: write` is sufficient and never touches protected main.
- Shipping a destructive memory-store migration in the same release that retires the field, which makes revert-forward rollback impossible without data loss.
- Letting the publish run on any main push — gate the job on the `chore(release): v` head-commit message so unrelated merges do not trigger a release.

## Definition of done

- [ ] The version is computed from `git log <last-tag>..main --first-parent` by `release plan` (pre-1.0 rules), not hand-picked, and is consistent with the milestone (epic title for a minor; computed for a theme patch).
- [ ] The release was triggered by a milestone hitting 0 open issues with CI green (or a deliberate `release prep` batch), never by a single PR.
- [ ] `release prep` produced the `chore/release-vX.Y.Z` branch carrying the `pyproject.toml` bump and a dated `CHANGELOG.md` section in Keep a Changelog form; a human merged that PR.
- [ ] `release check` passes: tag == `pyproject.toml` version == top CHANGELOG heading, the tag does not already exist, and `pytest` + `ruff` are green — enforced in CI on the `chore/release-*` PR.
- [ ] The version guard is wired so non-release PRs cannot edit `pyproject.toml` version or add a CHANGELOG heading.
- [ ] CI is the sole tagger and publisher: it creates and pushes the annotated tag and publishes the Release (`draft: false`) with the top CHANGELOG section as notes, using the default `GITHUB_TOKEN` with `contents: write` — no PAT, no commit to protected main, no manual `gh release create`.
- [ ] The library readiness gate passed: `import solomon_harness` succeeds and the `solomon-harness` console script runs.
- [ ] The tag is immutable (never moved/deleted); any bad release is corrected by a revert PR that ships forward as the next PATCH.
- [ ] Any memory-store schema change is backward-compatible (expand/contract); no destructive change is coupled to the release that retires it.
- [ ] `docs/release-policy.md` is cited as the canonical policy and this run did not deviate from it.
