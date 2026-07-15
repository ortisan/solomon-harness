# solomon-harness — Antigravity Agent Guidelines

The canonical project rules and specialist agent definitions are maintained in a central source. Read it before starting any work:
@agents/AGENTS.md

## Agent Architecture
Every specialist agent is modularly isolated and defined under `agents/<name>/`:
- **Persona:** `agents/<name>/persona.md` (defines core behavior, personality, and tone constraints).
- **Profile:** `agents/<name>/agents/<name>.md` (defines core duties, active local skills, and external skills access).
- **Local Skills:** `agents/<name>/skills/` (a directory of short, pulverized/topic-specific markdown files).
- **Configuration:** `agents/<name>/.agent/config.json` (defines model specifications and dynamic architectural patterns).
- **Specs:** `docs/specs/` (specification documents defining requirements and design constraints for feature issues).
- **ADRs:** `docs/adrs/` (Architectural Decision Records tracking architecture and technology selections).


## Best Practices for Agent Creation
When introducing a new agent to the harness, adhere to the following sequence:

1. **Create the Agent Structure:**
   Bootstrap a workspace with `uv run python -m solomon_harness.cli init`. To add a
   single agent, create the folder layout by hand or copy an existing agent
   directory under `agents/`, then fill in `agents/<name>/agents/<name>.md`,
   `persona.md`, `skills/`, and `.agent/config.json`.

2. **Define Topic-Specific (Pulverized) Skills:**
   Instead of writing a single large `best_practices.md` file, split the agent's knowledge into single-concern files under `agents/<agent_name>/skills/` (e.g., `tdd_workflow.md`, `input_validation.md`, `error_handling.md`).

3. **Auto-Document the Agent's Skills:**
   Run the skills documenter script to scan and link the pulverized skills into the agent's main markdown file:
   ```bash
   uv run python scripts/document-skills.py
   ```

4. **Compile the Harness:**
   Scaffold any missing agent files and regenerate the host-tool integrations
   (`.claude/agents/`, `.gemini/commands/`):
   ```bash
   uv run python -m solomon_harness.cli compile
   ```

## Development and Testing Standards
- **Strict TDD:** Write failing tests first, observe them fail, implement the fix, and then refactor.
- **SurrealDB Memory:** The primary memory backend is SurrealDB, with SQLite as the fallback store. Use the `solomon-memory` MCP tools to persist and query decisions, sessions, handoffs, and issues.
- **Style Rules:** No AI cliches, ornaments, or emojis in generated content. Keep all communication professional and direct.
