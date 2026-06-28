# Git Flow Branches

Governs the branch model for this repository: a Git Flow topology where branch names carry a short slug and no issue number, and the issue is linked through commit and PR trailers instead. Adopt this naming exactly; the number-in-the-branch form was removed because it reads as cluttered and goes stale the moment an issue is renamed or re-scoped.

## The branch model

Five long-lived and short-lived branch kinds, with strict cut-from and merge-back rules. The rules are what keep `main` releasable at all times.

- `main`: released, production code only. Never commit directly. Every commit on `main` is a merge from `release/*` or `hotfix/*` and carries a tag.
- `develop`: the integration branch. All `feature/*` and `bugfix/*` merge here. `develop` is always green: if it goes red, fixing it preempts new work.
- `feature/<slug>`: cut from `develop`, merges back to `develop`. Short-lived. If it ages past a few days, rebase onto (or merge in) `develop` to keep the eventual merge small.
- `bugfix/<slug>`: cut from `develop` for non-critical defects, merges back to `develop`. Same lifecycle as a feature; the prefix only signals intent so the backlog reads clearly.
- `release/<version>`: cut from `develop` to stabilize a milestone. Only fixes, version bumps, and docs land here. Merge to `main` (tagged) and back into `develop`. Never add a feature on a release branch.
- `hotfix/<version>`: cut from `main` for a critical production defect. Merge to `main` (tagged) and back into `develop`. If a `release/*` branch is active, merge the hotfix into that release branch too, so the in-flight release does not regress.

Naming rules: lowercase, hyphenated, no issue number, no trailing slash beyond the one prefix separator. The slug is two to four words describing the change, not the ticket: `feature/walk-forward-backtest`, `bugfix/slippage-rounding`, not `feature/142-wf` or `feature/142-walk-forward-backtest`. Versions on `release/*` and `hotfix/*` follow SemVer: `release/1.4.0`, `hotfix/1.4.1`.

## Linking the issue without a number in the branch

The branch name stays clean; the issue is linked in three durable places instead, so traceability survives a rename:

1. A back-link comment posted on the GitHub issue when work starts ("Branch `feature/walk-forward-backtest` opened for this issue").
2. `Refs #<issue>` in the body of every commit on the branch, so `git log` and the issue's cross-reference timeline both show the work.
3. `Closes #<issue>` (or `Fixes #<issue>`) in the pull request description, so merging the PR auto-closes the issue.

Use `Refs` for partial progress and `Closes`/`Fixes` only where the merge should actually close the issue — usually once, in the PR body. Putting `Closes #142` in a mid-branch commit will close the issue the instant that commit reaches `develop`, which is premature; reserve the closing keyword for the PR.

## A worked feature flow

Issue #142, "Add walk-forward backtest split", is Ready. Cut, commit, and open the PR using the no-number convention:

```bash
git switch develop && git pull --ff-only
git switch -c feature/walk-forward-backtest          # slug only; no 142 in the name

# post the back-link so the issue points at the branch
gh issue comment 142 --body "Branch \`feature/walk-forward-backtest\` opened for this issue."

# TDD commits, each body carrying the Refs trailer
git commit -m "test(backtest): add failing walk-forward split spec

Refs #142

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"

git commit -m "feat(backtest): add walk-forward split

Refs #142

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"

git push -u origin feature/walk-forward-backtest

# the PR carries the closing keyword exactly once
gh pr create --base develop --title "feat(backtest): walk-forward split" \
  --body "Adds the walk-forward split for the backtest pipeline.

Closes #142"
```

On merge to `develop`, GitHub closes #142 because of `Closes #142` in the PR body; the commit `Refs #142` trailers leave the full work trail on the issue. A hotfix follows the same shape but branches from `main`: `git switch -c hotfix/1.4.1 main`, fix, PR into `main` with the tag, then a second merge back into `develop` (and into any live `release/*`).

## Common pitfalls

- Naming a branch `feature/142-walk-forward-backtest`: the old form is banned because the number duplicates the link the PR already makes, and it lies the moment the issue is re-scoped or split. Use the slug only.
- Putting `Closes #142` in an early commit body: the issue closes as soon as that commit lands on `develop`, before the feature is actually done. Use `Refs #142` in commits and reserve `Closes` for the PR.
- Committing directly to `main` or `develop`: it skips review and breaks the invariant that every `main` commit is a tagged merge. All change arrives by PR.
- Adding a feature to a `release/*` branch: it reopens stabilization and pushes the release date. New scope goes to `develop` for the next milestone.
- Forgetting the back-link comment: without it the issue has no pointer to the branch until the PR exists, leaving an early-stage branch orphaned and easy to duplicate.
- Letting a `feature/*` branch age for weeks without integrating `develop`: the merge becomes a conflict-heavy event instead of a routine one. Rebase or merge `develop` in every few days.
- Skipping the merge-back of a `hotfix/*` into `develop`: `main` gets the fix but `develop` does not, so the next release silently reintroduces the bug.

## Definition of done

- [ ] Branch name follows `feature/<slug>`, `bugfix/<slug>`, `release/<version>`, or `hotfix/<version>`, lowercase and hyphenated, with no issue number.
- [ ] Branch was cut from the correct base (`develop` for feature/bugfix/release, `main` for hotfix).
- [ ] A back-link comment was posted on the GitHub issue when work started.
- [ ] Every commit body carries `Refs #<issue>`; the closing keyword (`Closes`/`Fixes #<issue>`) appears once, in the PR description.
- [ ] The PR targets the correct base branch (`develop`, or `main` for release/hotfix).
- [ ] No direct commits to `main` or `develop`; both stay reachable only through reviewed merges.
- [ ] Release and hotfix branches are merged to `main` with a SemVer tag and merged back into `develop` (and any active `release/*`).
- [ ] The merged branch is deleted; no stale branches accumulate on the remote.
