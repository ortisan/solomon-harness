# solomon-harness — Agent Instructions

The single source of truth for this project's rules and agent definitions is:

    agents/AGENTS.md

Read it first. It holds the communication rules, specialist competencies, the
development workflow lifecycle, the memory guide, and the index of every
specialist agent.

Each agent is defined under `agents/<name>/`:

- `agents/<name>/persona.md` — the persona.
- `agents/<name>/agents/<name>.md` — the role definition.
- `agents/<name>/skills/` — the agent's skills.
- `agents/<name>/.agent/config.json` — model and memory configuration.

Follow `agents/AGENTS.md` for all work: strict TDD, SOLID, design contracts, and
the humanizer rules (no emojis, no AI cliches in any output).
