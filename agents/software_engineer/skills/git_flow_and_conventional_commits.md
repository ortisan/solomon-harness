# Trunk-Based Development and Conventional Commits

This skill governs the implementer's branch and commit workflow for this repository: how to name a branch, how to link it to an issue, and how to write Conventional Commits 1.0.0 messages. The model is trunk-based — short-lived branches squash-merge into `main`, with no `develop` and no long-lived `release/*` or `hotfix/*` branches. The stance is exact and non-negotiable on three repo-specific facts: branches carry no issue number, commit messages carry no attribution trailer, and the Conventional-Commit type is load-bearing because it drives the computed SemVer bump and the CHANGELOG. Everything below respects all three.

## Branch naming and issue linking

Branch from `main`. Use exactly two short-lived working prefixes:

- `feature/<slug>` for a new capability.
- `bugfix/<slug>` for a defect.

The `<slug>` is a short, kebab-case description of the work, and nothing else. Do not put an issue number in the branch name. The old `feature/<issue>-<slug>` form is banned in this repo; a branch named `feature/123-add-retry` is a review finding, not a style preference.

```
git switch main && git pull
git switch -c feature/order-retry-guard      # correct: slug only
# git switch -c feature/123-order-retry-guard  # BANNED: no issue number in branch
```

The issue is linked three other ways, none of which is the branch name:

1. A back-link comment posted on the issue pointing at the branch or draft PR.
2. `Refs #<issue>` in the body of each related commit.
3. `Closes #<issue>` in the pull request description, so the merge auto-closes the issue.

## Trunk-based integration

This repository is trunk-based. `main` is the single integration trunk and the only long-lived branch: there is no `develop`, and there are no long-lived `release/*` or `hotfix/*` branches. Integrate a `feature/*` or `bugfix/*` branch through a reviewed pull request that **squash-merges** into `main`, so each PR lands as exactly one commit on the trunk. Keep branches short-lived: rebase on `main` to stay current before integrating, resolve conflicts locally, and never merge a red branch. A production-critical fix is just another `bugfix/*` branch that squash-merges to `main` and ships forward in the next release — not a branch off a tag.

The squash collapses every commit on the branch into one trunk commit, and **its subject line is the Conventional-Commit message that the release tooling reads**. The bump is computed from `git log <last-tag>..main --first-parent`, and on a squash-merged trunk every commit is a first-parent commit, so the squash commit's type is what counts. Set the squash commit's type and subject deliberately at merge time; do not accept the default concatenation of branch commits.

Releases never come from a long-lived branch. The only non-working branch is an **ephemeral `chore/release-vX.Y.Z` prep branch** that lives for minutes: `solomon-harness release prep` opens it carrying the `pyproject` version bump and the new CHANGELOG section, commits `chore(release): vX.Y.Z`, and opens a PR. A human merges that PR — that merge is the release gate — and CI then creates the tag and publishes the GitHub Release. The branch is deleted immediately after. You do not hand-edit `pyproject.version` or add CHANGELOG headings yourself; `release prep` writes them and a CI check rejects any non-release PR that touches them.

## Conventional Commits 1.0.0

Every commit message follows `type(scope): subject`, optional body, optional footer.

- Allowed types in this repo: `feat`, `fix`, `perf`, `refactor`, `revert`, `docs`, `chore`, `test`, `ci`, `build`, `style`.
- `scope` is optional and names the area touched, for example `feat(orders):`.
- Subject is in the imperative mood ("add retry guard", not "added"), under 72 characters with 50 as the target, no trailing period, no emoji.
- Body explains why and any trade-off, wrapped at 72 columns, separated from the subject by a blank line.
- Footer carries issue references (`Refs #<issue>`) and breaking-change notices.

Breaking changes are declared with a `BREAKING CHANGE:` footer, spelled out in full. Do not use the `!` shorthand (`feat!:` or `feat(api)!:`) in this repo; the explicit footer is required so the impact is described, not just flagged.

Match the type to intent: a `refactor` commit changes no behavior and adds no test for new behavior; a `feat` or `fix` ships with its tests in the same or an adjacent commit, per the TDD cycle. Commit in small, coherent steps, ideally at green points, where each commit builds and passes its tests on its own.

### Types drive the release

The Conventional-Commit type is not cosmetic. The release version is **computed, never hand-picked**: `solomon-harness release plan` reads `git log <last-tag>..main --first-parent`, takes the highest-ranked bump across that window, and the CHANGELOG section is generated from those same commits. While this repo is pre-1.0 (`0.x`), the mapping is:

| Type in the window | Pre-1.0 bump |
| --- | --- |
| any `feat` | MINOR |
| any `BREAKING CHANGE:` footer | MINOR |
| `fix`, `perf`, `refactor`, `revert` (no `feat`/breaking present) | PATCH |
| only `chore`, `docs`, `ci`, `test`, `style`, `build` | non-releasable (no tag) |

Highest wins: one `feat` in a window of otherwise `fix` commits makes the window a MINOR. A window that contains only non-releasable types cuts no tag at all. After 1.0 the mapping tightens: `BREAKING CHANGE:` becomes a MAJOR, `feat` a MINOR, and `fix`/`perf` a PATCH — so a `BREAKING CHANGE:` footer is the one thing whose bump changes across the 1.0 boundary (MINOR before, MAJOR after).

Because of this, a **mistyped commit corrupts the computed version and the CHANGELOG**. Labeling a behavior change as `chore` can suppress a release that should have shipped, or hide a user-facing change from the changelog; labeling a docs-only change as `feat` cuts a spurious MINOR. On a squash-merge the danger concentrates in the single squash subject, so verify its type against what the change actually did before you complete the merge. Type correctness is a release-correctness invariant here, not a style nicety.

### Critical: no attribution trailer

This repository bans `Co-Authored-By` and any other authorship or "generated by" trailer in commit messages. Do not add one to any commit, ever. A commit that carries a `Co-Authored-By:` line is a review finding here. The examples below deliberately contain none, and yours must not either.

### Worked examples

A feature commit with a body and an issue reference, no attribution trailer:

```
feat(orders): add retry guard for transient broker errors

Transient 5xx responses from the broker previously failed the order
outright. Retry up to three times with exponential backoff, then
surface a typed BrokerUnavailable error so the caller can decide.

Refs #142
```

A fix commit, terse, with its issue reference:

```
fix(auth): reject tokens missing the aud claim

Refs #207
```

A breaking change using the full footer, never the `!` shorthand:

```
refactor(api): rename statement endpoint to plural form

GET /account/{id}/statement becomes /accounts/{id}/statements for
consistency with the rest of the resource naming.

BREAKING CHANGE: GET /account/{id}/statement is removed. Clients must
call GET /accounts/{id}/statements.

Refs #311
```

A pure refactor that changes no behavior:

```
refactor(orders): extract fill averaging into a pure function

No behavior change; this isolates the ratio so the division-by-zero
guard is unit-tested in one place.

Refs #142
```

The pull request, not the commit or branch, carries the closing keyword:

```
# PR description
Adds the broker retry guard.

Closes #142
```

## Common pitfalls

- Putting an issue number in the branch name (`feature/142-retry-guard`): banned here; the slug stands alone and the issue links via the back-link comment, `Refs #`, and the PR's `Closes #`.
- Adding a `Co-Authored-By:` or any "generated by" trailer to a commit: banned in this repo and an automatic review finding.
- Mistyping the squash-merge subject: the type is load-bearing, so a behavior change labeled `chore` suppresses the release it should have cut, and a docs-only change labeled `feat` cuts a spurious MINOR. Verify the squash subject's type before merging.
- Using the `!` breaking-change shorthand (`feat!:`) instead of the `BREAKING CHANGE:` footer: the footer is required so the break is described, not merely flagged.
- A subject in past tense or with a trailing period ("Added retry guard."): use the imperative mood and no period.
- Hand-editing `pyproject.version` or adding a CHANGELOG heading in a normal PR: only `release prep` writes those; a CI check rejects any non-release PR that touches them.
- Branching off a tag for a "hotfix", or trying to recreate `develop`/`release/*`/`hotfix/*`: the model is trunk-only; a critical fix is a `bugfix/*` branch that squash-merges to `main` and ships forward.
- Putting `Closes #` in a commit body instead of the PR description, or omitting it from the PR, so the merge does not auto-close the issue.
- Long-lived branches that drift from `main`; rebase before integrating and merge only green branches.
- A subject over 72 characters or stuffing the "why" into the subject instead of the body.

## Definition of done

- [ ] Branch is `feature/<slug>` or `bugfix/<slug>`, cut from `main`, with no issue number in the name.
- [ ] The issue is linked via a back-link comment plus `Refs #<issue>` in commit bodies and `Closes #<issue>` in the PR description.
- [ ] Every commit follows `type(scope): subject` with an allowed type and an imperative subject under 72 characters, no trailing period, no emoji.
- [ ] The squash-merge commit's type and subject are set deliberately and match what the change does, because that single commit drives the computed SemVer bump and the CHANGELOG.
- [ ] No commit contains a `Co-Authored-By` or any other attribution/generated-by trailer.
- [ ] Breaking changes use the `BREAKING CHANGE:` footer, never the `!` shorthand.
- [ ] Commit type matches intent: `refactor` is behavior-preserving; `feat`/`fix` carry their tests.
- [ ] No normal PR hand-edits `pyproject.version` or adds a CHANGELOG heading; those come only from `release prep`.
- [ ] Commits are small and each builds and passes its tests independently.
- [ ] The branch was rebased on `main` before integration and is green at merge.
