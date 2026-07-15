# solomon-harness — Claude Code Agent Guidelines

The canonical project rules and specialist agent definitions are maintained in a central source. Read it before starting any work:
@agents/AGENTS.md

## Agent Architecture
Each specialist agent is modularly defined under `agents/<name>/`:
- **Persona:** `agents/<name>/persona.md` (defines personality and tone constraints).
- **Profile:** `agents/<name>/agents/<name>.md` (defines duties, active local skills, and external skills access).
- **Local Skills:** `agents/<name>/skills/` (short, single-concern markdown files).
- **Configuration:** `agents/<name>/.agent/config.json` (model selection and dynamic pattern switches).
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
   - `agents/<name>/.agent/config.json` — model and memory configuration.

2. **Author Specific Skills:**
   Create individual markdown files inside `agents/<agent_name>/skills/` for each specific topic/responsibility. Keep them short, focused, and precise.

3. **Update Active Skills Documentation:**
   Run the documentation script to auto-generate the list of active skills inside the agent profile:
   ```bash
   uv run python scripts/document-skills.py
   ```

4. **Compile the Harness:**
   Scaffold any missing agent files and regenerate the host-tool integrations
   (`.claude/agents/`, `.gemini/commands/`):
   ```bash
   uv run python -m solomon_harness.cli compile
   ```

## Non-Negotiable Standards
- **TDD Cycle:** Red (failing test), Green (minimal code to pass), Refactor. Never commit code without a covering test.
- **Memory Integration:** Use the SurrealDB memory backend. Decisions, issues, sessions, and handoffs must be logged via MCP tools.
- **Writing Style:** Output direct, professional English. Emojis, icons, or conversational AI filler are not allowed.
