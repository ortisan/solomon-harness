# Plan - Autonomous Subagents Setup (Task 1 - Git Flow & Conventional Commits updates)

This plan outlines the steps to update the persistent markdown profiles for the subagents to explicitly enforce Git Flow and Conventional Commits.

## Requirements

1. Update the following profile files under `.agents/agents/`:
   - `scrum_master.md`: Add rules for Git Flow branching (branching from `develop` for `feature/*`, creating `release/*` for milestones, merging to `develop` and `main` on release) and validation of conventional commit formats.
   - `software_engineer.md`: Add instructions to work on `feature/*` or `bugfix/*` branches and commit using conventional commit patterns (`feat`, `fix`, `docs`, `chore`, etc.).
   - `qa.md`: Add instructions to verify and test on the correct branches (e.g., verifying `feature/*` against `develop`, and verifying `release/*` before production integration).

2. Formatting and Style Constraints:
   - Written in professional, concise, direct English.
   - No emojis or icons in any profile or documentation.
   - Follow humanizer guidelines.

3. Git and Automation:
   - Stage and commit files with a clear conventional commit message.
   - Run the `./scripts/wiki-sync.sh` script to sync the project wiki.

## TDD and Verification Steps

1. **Red Stage**:
   - Update `scripts/validate-agents.py` to add new keyword validation checks for the updated profiles:
     - `scrum_master.md`: "Git Flow", "develop", "feature/*", "release/*", "conventional commit"
     - `software_engineer.md`: "feature/*", "bugfix/*", "conventional commit"
     - `qa.md`: "feature/*", "develop", "release/*", "production"
   - Running the script before modifying the profile files will fail.

2. **Green Stage**:
   - Update `scrum_master.md`, `software_engineer.md`, and `qa.md` to incorporate the Git Flow and Conventional Commit requirements.
   - Run `python3 scripts/validate-agents.py` to verify success.

3. **Refactor Stage**:
   - Improve wording, ensuring senior developer tone and adherence to constraints.
   - Confirm validation remains successful.

## Execution Steps

- [ ] Update `scripts/validate-agents.py` with the new keyword checks.
- [ ] Run `python3 scripts/validate-agents.py` to verify failure (Red Stage).
- [ ] Update `.agents/agents/scrum_master.md`.
- [ ] Update `.agents/agents/software_engineer.md`.
- [ ] Update `.agents/agents/qa.md`.
- [ ] Run `python3 scripts/validate-agents.py` to verify success (Green Stage).
- [ ] Stage and commit changes to Git.
- [ ] Run `./scripts/wiki-sync.sh` to sync the wiki.
