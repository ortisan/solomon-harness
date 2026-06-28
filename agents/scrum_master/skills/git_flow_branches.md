## Git Flow branches


- `main`: released, production code only. Never commit directly.
- `develop`: integration branch. All `feature/*` and `bugfix/*` merge here.
- `feature/<short-name>`: cut from `develop`, merge back to `develop`. Short-lived; rebase or merge `develop` in if it ages past a few days.
- `bugfix/<short-name>`: cut from `develop` for non-critical defects, merge back to `develop`.
- `release/<version>`: cut from `develop` to stabilize a milestone. Only fixes, version bumps, and docs land here. Merge to `main` (tagged) and back into `develop`. Never add features on a release branch.
- `hotfix/<version>`: cut from `main` for critical production defects. Merge to `main` (tagged) and back into `develop`. If a `release/*` branch is active, merge the hotfix into that release branch instead of `develop` so the in-flight release picks up the fix.
- Branch names are lowercase, hyphenated, and reference the issue where useful (e.g. `feature/walk-forward-backtest`).
