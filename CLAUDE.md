# solomon-harness

The canonical project rules and the specialist agent definitions are maintained
in one central source. Read it before any work:

@agents/AGENTS.md

Each specialist agent is defined under `agents/<name>/` (persona, role and
skills). The Claude Code subagents under `.claude/agents/` are generated from
that folder by `scripts/generate-integrations.py`.
