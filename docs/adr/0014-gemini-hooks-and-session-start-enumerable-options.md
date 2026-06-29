# ADR-0014: Gemini Hooks and Session-Start Enumerable Options

- Status: accepted
- Date: 2026-06-29
- Deciders: software_engineer, software_architect, qa, security
- Issue: #130

## Context and problem statement

When starting an agent session in Claude Code or the Gemini/Antigravity CLI, the agent must quickly determine if there is any pending task or active session in flight. Previously, the SessionStart hook only rendered a static status digest, requiring the user to manually type `/solomon-loop` to decide the next step. To streamline this workflow and eliminate unnecessary steps, we want to check memory at session startup and immediately present the user with a list of enumerated choices (e.g. continue start/review/release, or start a new issue). This needs to be supported in both Claude and Gemini settings and hooks.

## Decision drivers

- **Automation:** Minimize manual steps needed to resume or start a task when beginning a CLI session.
- **Consistency:** Maintain a uniform, cross-client experience for both Claude Code and Gemini/Antigravity CLI.
- **Autonomy & Safety:** Keep the user in control (human-in-the-loop) via clean, numbered options, avoiding dispersion.

## Considered options

- **Option 1:** Hardcode logic in local host configuration hooks. This makes configuration files complex and harder to maintain across projects.
- **Option 2:** Handle routing and formatting programmatically in Python (`solomon_harness/digest.py`) via the `SessionStart` CLI hook. This centralizes the logic in the harness codebase and enables dynamic, memory-aware option cards for all client integrations.

## Decision outcome

Chosen option "Option 2", because it keeps the configuration files clean and allows the harness to automatically serve rich, dynamic option lists to any host CLI.

### Consequences

- Positive: The agent immediately reads the startup hook stdout and presents numbered choices on start, facilitating instant continuation of in-flight tasks.
- Negative: Moves command representation and next-step decisions into Python, introducing tighter coupling between digest generation and the CLI commands.
- Follow-ups: Ensure strict validation of all parameters parsed/formatted into commands (e.g. PR and issue numbers) to prevent command injection.

## More information

This decision is also recorded in the project memory via `save_decision`.
