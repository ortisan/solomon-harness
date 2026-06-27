# Plan - Autonomous Subagents Setup (Task 1)

This plan outlines the steps to create and validate the persistent markdown profiles for ten specialized autonomous subagents.

## Requirements

1. Create the persistent markdown files in `.agents/agents/` folder:
   - `product_owner.md`: Product Owner profile. Translates user requirements to structured specifications, writes/manages the PRD, coordinates deliverables. Outputs the PRD contract.
   - `scrum_master.md`: Scrum Master profile. Project tracking, milestones, issue backlogs, orchestrates sprint planning/status meetings, coordinates reviews. Integrates with scrum-master script.
   - `software_architect.md`: Software Architect profile. System design, C4 diagrams, design contracts, Architectural Decision Records (ADRs). Outputs the Design Contract.
   - `software_engineer.md`: Software Engineer profile. Feature implementation, debugging, code quality, TDD cycle, clean/modular code.
   - `ml_engineer.md`: ML Engineer profile. ML models, feature engineering pipelines, validation, tracking hyperparameters, metrics, and dataset versions.
   - `quant_trader.md`: Quant Trader profile. Quantitative trading algorithms, backtest pipelines, validation of transaction costs, slippage, market regimes, risk parameters.
   - `qa.md`: QA Specialist profile. Test automation (unit, integration, E2E, backtests), verification reviews, user acceptance testing (UAT). Outputs the QA Report.
   - `documenter.md`: Technical & Business Documenter profile. Standardizes business value, writes technical manuals, design documentation, and user guides.
   - `observability.md`: Observability Specialist profile. Sets up log diagnostics, metrics tracking, performance profiling, and system monitoring dashboards.
   - `security.md`: Security Specialist profile. Threat modeling, security static analysis (SAST), vulnerability checks, and validates project dependencies.

2. Formatting and Style Constraints:
   - Written in professional, concise, direct English.
   - No emojis or icons in any profile or documentation.
   - Follow humanizer guidelines (avoiding AI clichés like "delve", "leverage", "testament", etc.).

3. Git and Automation:
   - Stage and commit files with the message: `feat: add persistent markdown profiles for 10 autonomous subagents`.
   - Run the `./scripts/wiki-sync.sh` script to sync the project wiki.

## TDD and Verification Steps

1. **Red Stage**:
   - Update/Create a local validation script `scripts/validate-agents.py`.
   - This script checks:
     - Existence of all 10 agent files under `.agents/agents/`.
     - Absence of emojis or icons (using Unicode symbol category check).
     - Absence of AI cliches.
     - Presence of specific required keywords/duties per profile.
   - Running the script before writing the profile files will fail.

2. **Green Stage**:
   - Create the 10 agent profile files with full descriptions aligned with their duties.
   - Run the validation script `python3 scripts/validate-agents.py` to verify all checks pass.

3. **Refactor Stage**:
   - Review and improve the wording and structure of the profiles.
   - Run the validation script to ensure checks remain green.

## Execution Steps

- [x] Write the initial TDD validation script (`scripts/validate-agents.py`).
- [ ] Update the TDD validation script (`scripts/validate-agents.py`) for 10 subagents.
- [ ] Execute `python3 scripts/validate-agents.py` and verify failure (Red Stage).
- [x] Create `.agents/agents/product_owner.md` following the requirements.
- [x] Create `.agents/agents/scrum_master.md` (correcting "status meetings").
- [x] Create `.agents/agents/software_architect.md` following the requirements.
- [x] Create `.agents/agents/software_engineer.md` following the requirements.
- [x] Create `.agents/agents/ml_engineer.md` (correcting "validation" keyword).
- [x] Create `.agents/agents/quant_trader.md` following the requirements.
- [x] Create `.agents/agents/qa.md` following the requirements.
- [ ] Create `.agents/agents/documenter.md` following the requirements.
- [ ] Create `.agents/agents/observability.md` following the requirements.
- [ ] Create `.agents/agents/security.md` following the requirements.
- [ ] Execute `python3 scripts/validate-agents.py` and verify success (Green Stage).
- [ ] Stage all modified and new files.
- [ ] Commit with message: `feat: add persistent markdown profiles for 10 autonomous subagents`.
- [ ] Run `./scripts/wiki-sync.sh` to sync the wiki.
