# Plan - New Subagent Contract Templates & Profile Expansion (Task 2 Expansion)

This plan outlines the steps to create and validate two new contract templates (Flutter and Web Frontend) and add prompt profiles for SRE and SEO subagents.

## Requirements

1. Create two new template files under `docs/templates/contracts/`:
   - `flutter_contract.md`: Technical contract for Flutter deliverables. Cover Dart dependencies, state management model, responsive widgets checklist, and integration tests.
   - `frontend_contract.md`: Technical contract for React & Angular frontend deliverables. Cover styles, components, state management store structure, and web test coverage.

2. Create two new subagent profiles under `.agents/agents/`:
   - `sre.md`: SRE Specialist. High availability, infrastructure configurations, deployment pipelines, load testing, incident runbooks, disaster recovery strategies, and SLA/SLO metrics.
   - `seo.md`: SEO Specialist. HTML semantic hierarchy, metadata schema validation, indexing/crawling instructions (robots.txt, sitemaps), page speed optimizations, and site indexability audits.

3. Formatting and Style Constraints:
   - Written in professional, direct, senior-engineer style English.
   - No emojis, icons, or visual ornaments.
   - Avoid AI clichés (e.g., "delve", "leverage", "testament to", "feel free to", "in summary").
   - Conforming to Git Flow and Conventional Commits.
   - Follow humanizer guidelines.

4. Git and Automation:
   - Stage and commit files to Git with the exact message: `feat: add artifact templates to represent deliverables as 10 subagent contracts`.
   - Run `./scripts/wiki-sync.sh` to sync the wiki.

## TDD and Verification Steps

1. **Red Stage**:
   - Update `scripts/validate-agents.py` to check for SRE and SEO profiles and their keywords:
     - `sre.md`: "SRE Specialist", "high availability", "infrastructure", "deployment pipelines", "load testing", "incident runbooks", "disaster recovery", "SLA/SLO", "Git Flow", "Conventional Commits"
     - `seo.md`: "SEO Specialist", "semantic hierarchy", "metadata", "indexing/crawling", "page speed", "audits", "Git Flow", "Conventional Commits"
   - Run `python3 scripts/validate-agents.py` to confirm failure (Red Stage).

2. **Green Stage**:
   - Write `sre.md` and `seo.md` in `.agents/agents/`.
   - Run `python3 scripts/validate-agents.py` to verify success (Green Stage).

3. **Refactor Stage**:
   - Refine wording and template structure to ensure a direct, professional, and natural senior engineer style.
   - Ensure all validation scripts run successfully.

## Execution Checklist

- [x] Create/Update `docs/templates/contracts/flutter_contract.md` and `frontend_contract.md`.
- [x] Update `scripts/validate-templates.py` and run to verify templates.
- [x] Update `scripts/validate-agents.py` to check for SRE and SEO subagents.
- [x] Run `python3 scripts/validate-agents.py` to verify failure (Red Stage).
- [x] Create `.agents/agents/sre.md`.
- [x] Create `.agents/agents/seo.md`.
- [x] Run `python3 scripts/validate-agents.py` to verify success (Green Stage).
- [x] Stage and commit changes with the exact message: `feat: add artifact templates to represent deliverables as 10 subagent contracts`.
- [x] Run `./scripts/wiki-sync.sh` to sync the wiki.
