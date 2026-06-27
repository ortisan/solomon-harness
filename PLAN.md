# Plan - New Subagent Contract Templates (Task 2 Expansion)

This plan outlines the steps to create and validate two new contract templates requested by the parent agent to represent deliverables for Flutter and Web Frontend subagents.

## Requirements

1. Create two new template files under `docs/templates/contracts/`:
   - `flutter_contract.md`: Technical contract for Flutter deliverables. Must cover Dart dependencies, state management model, responsive widgets checklist, and integration tests.
   - `frontend_contract.md`: Technical contract for React & Angular frontend deliverables. Must cover styles, components, state management store structure, and web test coverage.

2. Formatting and Style Constraints:
   - Written in professional, direct, senior-engineer style English.
   - No emojis, icons, or visual ornaments.
   - Avoid AI clichés (e.g., "delve", "leverage", "testament to", "feel free to", "in summary").
   - Incorporate Git Flow (branches like `develop`, `feature/*`, `release/*`) and Conventional Commits practices (commit message rules) in templates where applicable (e.g. tracking branches and commits in release or QA logs).
   - Follow humanizer guidelines.

3. Git and Automation:
   - Stage and commit files to Git.
   - Run `./scripts/wiki-sync.sh` to sync the wiki.

## TDD and Verification Steps

1. **Red Stage**:
   - Update `scripts/validate-templates.py` to validate:
     - The presence of `flutter_contract.md` and `frontend_contract.md` under `docs/templates/contracts/`.
     - Absence of emojis and AI clichés.
     - Presence of required sections/keywords per template:
       - `flutter_contract.md`: "Dart dependencies", "state management model", "responsive widgets checklist", "integration tests", "Git Flow", "Conventional Commits".
       - `frontend_contract.md`: "styles", "components", "state management store structure", "web test coverage", "Git Flow", "Conventional Commits".
   - Run `python3 scripts/validate-templates.py` to confirm failure (Red Stage).

2. **Green Stage**:
   - Write the two templates in `docs/templates/contracts/` satisfying all constraints and keywords.
   - Run `python3 scripts/validate-templates.py` to verify success (Green Stage).

3. **Refactor Stage**:
   - Refine wording and template structure to ensure a direct, professional, and natural senior engineer style.
   - Ensure the validation script still runs successfully.

## Execution Checklist

- [ ] Update `scripts/validate-templates.py` with required keys for the new templates.
- [ ] Run `python3 scripts/validate-templates.py` to verify failure (Red Stage).
- [ ] Write `docs/templates/contracts/flutter_contract.md`.
- [ ] Write `docs/templates/contracts/frontend_contract.md`.
- [ ] Run `python3 scripts/validate-templates.py` to verify success (Green Stage).
- [ ] Stage and commit changes.
- [ ] Run `./scripts/wiki-sync.sh` to sync the wiki.
