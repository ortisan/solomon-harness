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
- `agents/<name>/.agent/config.json` — source profile metadata.

Follow `agents/AGENTS.md` for all work: strict TDD, SOLID, design contracts, and
the humanizer rules (no emojis, no AI cliches in any output).

This is the Codex/AGENTS entrypoint for the harness source checkout. In a
consumer repository, `solomon-harness init` installs the canonical rules,
agents, workflows, runtime, config, and state under `.agents/solomon`; the root
`AGENTS.md` is then only a managed pointer block to
`.agents/solomon/AGENTS.md`. Claude, AGY, and Codex adapters are compiled from
that same catalog and must expose equivalent functionality. Do not copy this
source repository's root trees into a consumer project.

<!-- solomon-harness:start -->
The Solomon rules are in `agents/AGENTS.md`. Read that file completely before starting work.
<!-- solomon-harness:end -->
