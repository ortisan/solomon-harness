# Plan - Workspace Rules Templates Language Update (Task 5)

This plan outlines the steps to translate the rule templates (`CLAUDE.md.template` and `AGENTS.md.template`) to English, regenerate the final rule files, and commit the changes.

## Requirements
1. **Language**: Rewrite templates and rules in clean, direct, professional English.
2. **No Emojis or Icons**: Ensure no emojis, icons, or visual ornaments are used.
3. **Humanizer Principles**:
   - Write instructions in a direct, clear, professional human-like English.
   - Avoid typical AI clichés ("delve", "leverage", "testament to", "feel free to", "dive into", etc.).
   - Explicitly instruct the agent that all output text (commit messages, PRs, wiki pages, comments) must be written in a natural, direct, professional human-like tone, without emojis or icons.
4. **Specialist Competencies**:
   - **Programming & Architecture**: Strict TDD, SOLID, modular design, design contracts as boundaries, preservation of docstrings/comments.
   - **Quantitative Trading & DRL/ML Engineer**:
     - Model Hypothesis: State target Sharpe ratio, Drawdown limit, Profit factor, latency/slippage constraints, dataset/features, model architecture.
     - Validation: Overfitting checks, cross-validation, out-of-sample tests. Zero data leakage.
     - Safety: Shape validation on tensors, division-by-zero checks, float overflow checks.
   - **QA Specialist**: Mandatory unit/integration tests for code, mocking API calls, backtesting tests.
   - **Scrum Master**: Instructions on using `scripts/scrum-master.sh` for issues/milestones.
   - **Code Reviewer**: Check against spec compliance first, then code quality.
5. **Workflow Lifecycle**:
   - Conception (creating issue via scrum-master.sh) -> Planning (creating plan md) -> Execution (TDD) -> Verification -> Code Review -> Release & Wiki Sync (wiki-sync.sh).
6. **Interpolation Variables**:
   - Use `{{PROJECT_NAME}}`, `{{TECH_STACK}}`, and `{{GIT_REMOTE}}`.

## Execution Steps
- [ ] Rewrite `templates/CLAUDE.md.template` in English.
- [ ] Rewrite `templates/AGENTS.md.template` in English.
- [ ] Run `./scripts/bootstrap-agent.sh` to update/overwrite the final `CLAUDE.md` and `.agents/AGENTS.md` files.
- [ ] Verify that the generated files are correctly formatted and in English.
- [ ] Stage and commit the updated files to the repository.
- [ ] Notify the parent agent with the final status.
