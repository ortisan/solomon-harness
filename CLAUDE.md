# solomon-harness — Claude Code Agent Guidelines

The canonical project rules and specialist agent definitions are maintained in a central source. Read it before starting any work:
@agents/AGENTS.md

## Agent Architecture
Each specialist agent is modularly defined under `agents/<name>/`:
- **Persona:** `agents/<name>/persona.md` (defines personality and tone constraints).
- **Profile:** `agents/<name>/agents/<name>.md` (defines duties, active local skills, and external skills access).
- **Local Skills:** `agents/<name>/skills/` (short, single-concern markdown files).
- **Configuration:** `agents/<name>/.agent/config.json` (source profile metadata; installed model selection belongs to the host).
- **Specs:** `docs/specs/` (specification documents defining requirements and design constraints for feature issues).
- **ADRs:** `docs/adrs/` (Architectural Decision Records tracking architecture and technology selections).


## How to Create a New Agent

1. **Create the Agent Folder Structure:**
   Bootstrap a workspace with `uv run python -m solomon_harness.cli init`. To add a
   single agent, create the folder layout by hand (or copy an existing agent
   directory under `agents/`), then fill in:
   - `agents/<name>/agents/<name>.md` — the role definition.
   - `agents/<name>/persona.md` — the persona.
   - `agents/<name>/skills/` — the agent's skills.
   - `agents/<name>/.agent/config.json` — source profile metadata.

2. **Author Specific Skills:**
   Create individual markdown files inside `agents/<agent_name>/skills/` for each specific topic/responsibility. Keep them short, focused, and precise.

3. **Update Active Skills Documentation:**
   Run the documentation script to auto-generate the list of active skills inside the agent profile:
   ```bash
   uv run python scripts/document-skills.py
   ```

4. **Compile the Harness:**
   Regenerate the thin Claude, AGY, and Codex integrations from the existing
   canonical source files:
   ```bash
   uv run python -m solomon_harness.cli compile
   ```

## Installed Projects

This file imports `agents/AGENTS.md` because this repository is the harness
source checkout. In a consumer repository, `solomon-harness init` places the
canonical catalog at `.agents/solomon`; `.claude/CLAUDE.md`,
`.claude/agents/`, `.claude/skills/`, `.claude/settings.json`, and `.mcp.json`
are thin Claude adapters that point there. AGY and Codex receive equivalent
adapters from the same catalog. Rebuild them with `solomon-harness compile` and
remove unchanged manifest-owned output with `solomon-harness uninstall`.

## Non-Negotiable Standards
- **TDD Cycle:** Red (failing test), Green (minimal code to pass), Refactor. Never commit code without a covering test.
- **Memory Integration:** Use the SurrealDB memory backend. Decisions, issues, sessions, and handoffs must be logged via MCP tools.
- **Writing Style:** Output direct, professional English. Emojis, icons, or conversational AI filler are not allowed.
