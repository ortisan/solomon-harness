# solomon-harness

The canonical project rules and the specialist agent definitions are maintained
in one central source. Read it before any work:

@agents/AGENTS.md

Each specialist agent is defined under `agents/<name>/` (persona, the role in
`agents/<name>.md`, and skills). The project memory is available as the
`solomon-memory` MCP server (configured in `.gemini/settings.json`); use its
tools to read and write decisions, issues, sessions and handoffs.
