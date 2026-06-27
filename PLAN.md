# Plan - Move Subagent Prompts and Rules to agents/ Directory

This plan outlines the design, implementation, and verification steps for Task 2 of the Solomon Harness: Agent Harness Refactoring.

## Requirements

1. **Move global workspace rules**:
   - Move `.agents/AGENTS.md` to `agents/AGENTS.md`.

2. **Move subagent configurations**:
   - Move all `.md` files in `.agents/agents/` to `agents/`.

3. **Update bootstrap script (`scripts/bootstrap-agent.sh`)**:
   - Modify the target of the `AGENTS.md` template interpolation to `agents/AGENTS.md`.
   - Update the script to symlink/copy `agents/AGENTS.md` to `.agents/AGENTS.md` and all subagent `.md` files from `agents/` (excluding `AGENTS.md`) to `.agents/agents/`.
   - Run the bootstrap script `./scripts/bootstrap-agent.sh` to generate/sync the files.

4. **Update and run validation checks**:
   - Modify `scripts/validate-agents.py` to validate source files in `agents/` instead of `.agents/agents/` directly.
   - Run validation script `scripts/validate-agents.py` to ensure it passes.
   - Check if other validation scripts run and pass.

5. **Version Control**:
   - Stage all changes.
   - Commit them with the message: `feat: move subagent prompts and rules to agents directory`.

## TDD and Verification Steps

1. **Move the files**:
   - Move the files from `.agents/` to `agents/` using git/shell commands.

2. **Update the Validation Script**:
   - Modify `scripts/validate-agents.py` to use `agents/` instead of `.agents/agents/`.
   - Run `python3 scripts/validate-agents.py` to verify it can scan the new directory (though files won't be in `.agents/agents/` yet until bootstrap runs, but running it should check `agents/` directly).

3. **Modify and Run the Bootstrap Script**:
   - Update `scripts/bootstrap-agent.sh`.
   - Run `scripts/bootstrap-agent.sh`.
   - Verify that the symlinks or copies are correctly created in `.agents/AGENTS.md` and `.agents/agents/*.md`.

4. **Verify All Validations**:
   - Run `python3 scripts/validate-agents.py`.
   - Run `python3 scripts/validate-templates.py`.
   - Run any other validation checks.

5. **Commit**:
   - Commit with the message `feat: move subagent prompts and rules to agents directory`.

## Execution Checklist

- [x] Write this plan in PLAN.md.
- [x] Move `.agents/AGENTS.md` to `agents/AGENTS.md`.
- [x] Move `.agents/agents/*.md` to `agents/`.
- [x] Modify `scripts/validate-agents.py` to target `agents/` instead of `.agents/agents/`.
- [x] Modify `scripts/bootstrap-agent.sh` to:
  - Interpolate `templates/AGENTS.md.template` into `agents/AGENTS.md`.
  - Symlink `agents/AGENTS.md` to `.agents/AGENTS.md`.
  - Symlink all `.md` files from `agents/` (except `AGENTS.md`) to `.agents/agents/`.
- [x] Execute `./scripts/bootstrap-agent.sh` to generate/sync configurations.
- [x] Run `python3 scripts/validate-agents.py` and other validation checks to confirm success.
- [x] Stage and commit changes with the specified git commit message.
