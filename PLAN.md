# Plan - Autonomous Subagents Setup (Task 3)

This plan outlines the design, implementation, and verification steps for the spawn-agent wrapper script.

## Requirements

1. **Script Path**: `scripts/spawn-agent.sh`.
2. **Dynamic Scan**: Scan the `.agents/agents/` directory dynamically for subagents without hardcoding.
3. **Subcommands**:
   - `list`: Lists all available subagents in `.agents/agents/*.md`, showing their name (from filename) and description (first paragraph/non-empty line not starting with `#`).
   - `show <agent_name>`: Displays the full contents of `.agents/agents/<agent_name>.md`.
   - `help` / `-h` / `--help`: Displays detailed usage.
4. **Style Constraints**:
   - No emojis, icons, or visual ornaments.
   - Professional, direct, senior-engineer style English (no AI clichés).
5. **Script Safety**:
   - Use `set -euo pipefail`.
   - Double-quote all variables.
   - Exit with code `0` on success and non-zero on failure with clear messages on `stderr`.
6. **Execution Permission**: The script must be executable.
7. **Commit & Wiki Sync**:
   - Commit with message: `feat: add spawn-agent helper script to manage subagent configurations`.
   - Run `./scripts/wiki-sync.sh` to sync the wiki.

## TDD and Verification Steps

We will implement a testing script `scripts/test-spawn-agent.sh` to drive our TDD cycle.

1. **Red Stage**:
   - Create `scripts/test-spawn-agent.sh` which executes tests against `scripts/spawn-agent.sh` (which doesn't exist yet or is empty).
   - Run the tests to confirm failure.
2. **Green Stage**:
   - Create `scripts/spawn-agent.sh` with the required subcommand logic.
   - Make the script executable.
   - Run `scripts/test-spawn-agent.sh` and ensure all tests pass.
3. **Refactor Stage**:
   - Add the new script to `.github/workflows/ci.yml` validation steps (bash syntax check and shellcheck).
   - Run `shellcheck` manually and fix any lint issues.
   - Confirm all tests and validations pass cleanly.

## Execution Checklist

- [x] Create `scripts/test-spawn-agent.sh` (TDD Red).
- [x] Execute `scripts/test-spawn-agent.sh` to verify failure (Red).
- [x] Create `scripts/spawn-agent.sh` with dynamic scanning and subcommands (list, show, help).
- [x] Make `scripts/spawn-agent.sh` executable.
- [x] Run `scripts/test-spawn-agent.sh` to verify success (Green).
- [x] Update `.github/workflows/ci.yml` to include `scripts/spawn-agent.sh` and `scripts/test-spawn-agent.sh`.
- [x] Run shellcheck on both scripts.
- [x] Commit all changes with message: `feat: add spawn-agent helper script to manage subagent configurations`.
- [x] Execute `./scripts/wiki-sync.sh`.
