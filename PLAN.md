# Plan - Standardized Subagent Contract Templates (Task 2)

This plan outlines the steps to create and validate the standardized contract templates representing deliverables of the autonomous subagents.

## Requirements

1. Create six template files under `docs/templates/contracts/`:
   - `prd_contract.md`: Deliverable of the Product Owner. Must structure the requirements, user stories, business value, active requirements, scope boundaries, and high-level milestones.
   - `design_contract.md`: Deliverable of the Software Architect. Must structure component design, C4 architectural block diagrams (using Mermaid), data flow models, API schemas, and ADR mappings.
   - `qa_report_contract.md`: Deliverable of the QA Specialist. Must detail test coverage, test logs (unit/integration/E2E), backtesting metrics (for quant models), and UAT validation checklists.
   - `docs_contract.md`: Deliverable of the Technical & Business Documenter. Must structure user manuals, API developer guides, and business process mappings.
   - `obs_contract.md`: Deliverable of the Observability Specialist. Must detail application metrics, logging standards, tracing endpoints, and alert triggers.
   - `security_contract.md`: Deliverable of the Security Specialist. Must structure threat modeling (STRIDE), dependencies checking, and vulnerability mitigation reports.

2. Formatting and Style Constraints:
   - Written in professional, direct, senior-engineer style English.
   - No emojis, icons, or visual ornaments.
   - Avoid AI clichés (e.g., "delve", "leverage", "testament to", "feel free to", "in summary").
   - Incorporate Git Flow (branches like `develop`, `feature/*`, `release/*`) and Conventional Commits practices (commit message rules) in templates where applicable (e.g. tracking branches and commits in release or QA logs).
   - Follow humanizer guidelines.

3. Git and Automation:
   - Stage and commit files to Git with the exact message: `feat: add artifact templates to represent deliverables as 10 subagent contracts`.
   - Run `./scripts/wiki-sync.sh` to sync the wiki.

## TDD and Verification Steps

1. **Red Stage**:
   - Write a python script `scripts/validate-templates.py` to validate:
     - The presence of the 6 templates under `docs/templates/contracts/`.
     - Absence of emojis and AI clichés.
     - Presence of required sections/keywords per template:
       - `prd_contract.md`: "Requirements", "User Stories", "Business Value", "Active Requirements", "Scope Boundaries", "High-Level Milestones", "Git Flow", "Conventional Commits".
       - `design_contract.md`: "Component Design", "C4", "Mermaid", "Data Flow", "API Schemas", "ADR Mappings", "Git Flow", "Conventional Commits".
       - `qa_report_contract.md`: "Test Coverage", "Test Logs", "Unit", "Integration", "E2E", "Backtesting Metrics", "UAT Validation Checklist", "Git Flow", "Conventional Commits".
       - `docs_contract.md`: "User Manual", "API Developer Guide", "Business Process Mappings", "Git Flow", "Conventional Commits".
       - `obs_contract.md`: "Application Metrics", "Logging Standards", "Tracing Endpoints", "Alert Triggers", "Git Flow", "Conventional Commits".
       - `security_contract.md`: "Threat Modeling", "STRIDE", "Dependencies Checking", "Vulnerability Mitigation", "Git Flow", "Conventional Commits".
   - Run `python3 scripts/validate-templates.py` to confirm failure (Red Stage).

2. **Green Stage**:
   - Create `docs/templates/contracts/` directory.
   - Write all 6 templates in `docs/templates/contracts/` satisfying all constraints and keywords.
   - Run `python3 scripts/validate-templates.py` to verify success (Green Stage).

3. **Refactor Stage**:
   - Refine wording and template structure to ensure a direct, professional, and natural senior engineer style.
   - Ensure the validation script still runs successfully.

## Execution Checklist

- [ ] Write `scripts/validate-templates.py`.
- [ ] Run `python3 scripts/validate-templates.py` to verify failure (Red Stage).
- [ ] Write `docs/templates/contracts/prd_contract.md`.
- [ ] Write `docs/templates/contracts/design_contract.md`.
- [ ] Write `docs/templates/contracts/qa_report_contract.md`.
- [ ] Write `docs/templates/contracts/docs_contract.md`.
- [ ] Write `docs/templates/contracts/obs_contract.md`.
- [ ] Write `docs/templates/contracts/security_contract.md`.
- [ ] Run `python3 scripts/validate-templates.py` to verify success (Green Stage).
- [ ] Stage and commit changes with message: `feat: add artifact templates to represent deliverables as 10 subagent contracts`.
- [ ] Run `./scripts/wiki-sync.sh` to sync the wiki.
