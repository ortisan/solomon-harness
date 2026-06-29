# Trunk-Based Branches

Governs the branch model for this repository: a trunk-based topology where `main` is the only long-lived branch, every change lands by a reviewed, squash-merged pull request cut from `main`, and branch names carry a short slug with no issue number — the issue is linked through commit and PR trailers instead. Adopt this exactly. There is no `develop`, and there are no long-lived `release/*` or `hotfix/*` branches; the develop-plus-release-branches Git Flow model was removed because it let `main` drift from what actually ships and created merge-back debt on every release. The number-in-the-branch form was removed too, because it reads as cluttered and goes stale the moment an issue is renamed or re-scoped.

## The branch model

One long-lived branch and two short-lived working prefixes, plus a single ephemeral machine-owned release branch. The rules are what keep `main` releasable at all times.

- `main`: the trunk — released, production-ready code, releasable at every commit. Never commit directly. Every change arrives as one squash-merge from a reviewed PR, so each commit on `main` is a single self-contained slice. Tags are cut on `main` by CI, not by merging a release branch into it.
- `feature/<slug>`: cut from `main`, squash-merges back to `main` through a reviewed PR. Short-lived. If it ages past a few days, rebase onto `main` to keep the eventual merge small.
- `bugfix/<slug>`: cut from `main` for a defect, squash-merges back to `main`. Same lifecycle as a feature; the prefix only signals intent so the backlog reads clearly. A production-critical fix uses this exact shape — there is no separate hotfix branch — and reaches users in the next patch tag.
- `chore/release-vX.Y.Z`: the one exception, and it is ephemeral and machine-owned. `solomon-harness release prep` opens it carrying only the `pyproject` version bump and the CHANGELOG section, commits `chore(release): vX.Y.Z`, and opens a PR. A human merges that PR — that merge is the release gate — and CI then creates the tag and publishes the Release on `main`, after which the branch is deleted. Never open or hand-edit this branch.

Naming rules: lowercase, hyphenated, no issue number, no trailing slash beyond the one prefix separator. The slug is two to four words describing the change, not the ticket: `feature/walk-forward-backtest`, `bugfix/slippage-rounding`, not `feature/142-wf` or `feature/142-walk-forward-backtest`. The only version-bearing branch name is the generated `chore/release-vX.Y.Z`, where the version is SemVer computed by `release prep` — never hand-picked.

## Linking the issue without a number in the branch

The branch name stays clean; the issue is linked in three durable places instead, so traceability survives a rename:

1. A back-link comment posted on the GitHub issue when work starts ("Branch `feature/walk-forward-backtest` opened for this issue").
2. `Refs #<issue>` in the body of every commit on the branch, so `git log` and the issue's cross-reference timeline both show the work.
3. `Closes #<issue>` (or `Fixes #<issue>`) in the pull request description, so merging the PR auto-closes the issue.

Use `Refs` for partial progress and `Closes`/`Fixes` only where the merge should actually close the issue — once, in the PR body. Because the PR squash-merges, GitHub folds every commit message into the single merge commit; a `Closes #142` buried in a commit body would duplicate the one in the PR description and muddy the squash message. Keep the closing keyword in the PR body and leave `Refs` in the commits.

## A worked feature flow

Issue #142, "Add walk-forward backtest split", is Ready. Cut, commit, and open the PR using the no-number convention:

```bash
git switch main && git pull --ff-only
git switch -c feature/walk-forward-backtest          # slug only; no 142 in the name

# post the back-link so the issue points at the branch
gh issue comment 142 --body "Branch \`feature/walk-forward-backtest\` opened for this issue."

# TDD commits, each body carrying the Refs trailer
git commit -m "test(backtest): add failing walk-forward split spec

Refs #142"

git commit -m "feat(backtest): add walk-forward split

Refs #142"

git push -u origin feature/walk-forward-backtest

# the PR targets main and carries the closing keyword exactly once
gh pr create --base main --title "feat(backtest): walk-forward split" \
  --body "Adds the walk-forward split for the backtest pipeline.

Closes #142"
```

The PR is squash-merged into `main` after review; GitHub closes #142 from the `Closes #142` in the PR body, and the `Refs #142` commit trailers leave the full work trail on the issue's timeline. A production-critical defect follows the very same shape with a `bugfix/<slug>` cut from `main` — no hotfix branch and no merge-back step — and ships in the next patch tag. Releasing is not a branch you cut by hand: when a milestone closes, `solomon-harness release prep` opens the ephemeral `chore/release-vX.Y.Z` PR, a human merges it, and CI tags `main`.

## Common pitfalls

- Naming a branch `feature/142-walk-forward-backtest`: the old form is banned because the number duplicates the link the PR already makes, and it lies the moment the issue is re-scoped or split. Use the slug only.
- Putting `Closes #142` in a commit body: on a squash merge GitHub concatenates every commit message into the merge commit, so a stray closing keyword duplicates the one in the PR body and clutters the squash message. Use `Refs #142` in commits and reserve `Closes`/`Fixes` for the PR description.
- Committing directly to `main`: it skips review and the squash-PR gate, and breaks the invariant that every `main` commit is one self-contained, reviewed slice. All change arrives by PR.
- Hand-creating a `release/*` or `hotfix/*` branch, or hand-editing `pyproject` version or CHANGELOG: there are no such branches, and the version files are owned by `solomon-harness release prep`. A production fix is a normal `bugfix/<slug>` off `main`; a release is the machine-opened ephemeral `chore/release-vX.Y.Z` PR.
- Forgetting the back-link comment: without it the issue has no pointer to the branch until the PR exists, leaving an early-stage branch orphaned and easy to duplicate.
- Letting a `feature/*` branch age for weeks without integrating `main`: the merge becomes a conflict-heavy event instead of a routine one. Rebase onto `main` every few days.

## Definition of done

- [ ] Branch name follows `feature/<slug>` or `bugfix/<slug>`, lowercase and hyphenated, with no issue number; the only other branch is the machine-generated ephemeral `chore/release-vX.Y.Z`.
- [ ] Branch was cut from `main` and is up to date with `main` before the PR opens.
- [ ] A back-link comment was posted on the GitHub issue when work started.
- [ ] Every commit body carries `Refs #<issue>`; the closing keyword (`Closes`/`Fixes #<issue>`) appears once, in the PR description.
- [ ] The PR targets `main` and is squash-merged after review.
- [ ] No direct commits to `main`; every change reaches it only through a reviewed, squash-merged PR.
- [ ] No `develop`, `release/*`, or `hotfix/*` branch was created; a production-critical fix is a normal `bugfix/<slug>` off `main` that ships in the next patch tag.
- [ ] Version bumps and tagging are left to `solomon-harness release prep` and CI; `pyproject` version and CHANGELOG are not hand-edited.
- [ ] The merged branch is deleted; no stale branches accumulate on the remote.
