## Git Flow and conventional commits


- Branch from `develop`: `feature/<short-slug>` for new capability, `bugfix/<short-slug>` for defects. `release/<version>` branches off `develop` to stabilize a release; `hotfix/<version>` branches from `main` for production-critical patches.
- Merge `feature/*` and `bugfix/*` back into `develop` through a reviewed pull request. Merge `release/*` and `hotfix/*` into both `main` and `develop` so fixes are never lost, and tag the release on `main`.
- Keep branches short-lived. Rebase on `develop` to stay current before integrating; resolve conflicts locally and never merge a red branch.
- Commit in small, coherent steps, ideally at green points. Each commit builds and passes tests on its own.
- Conventional Commits format: `type(scope): description`.
  - Types: `feat`, `fix`, `docs`, `style`, `refactor`, `perf`, `test`, `build`, `ci`, `chore`.
  - Subject in imperative mood ("add retry guard", not "added"), under 72 characters (50 is the sweet spot), no trailing period, no emoji.
  - Body explains why and any trade-off, wrapped at 72 columns. Footer carries `BREAKING CHANGE:` and issue references.
  - Match type to intent: a `refactor` commit changes no behavior and adds no test for new behavior; a `feat`/`fix` ships with its tests in the same or an adjacent commit.
