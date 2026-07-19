# solomon-harness — AGY Agent Guidelines

The canonical project rules and specialist agent definitions are maintained in a central source. Read it before starting any work:
@agents/AGENTS.md

## Agent Architecture
Every specialist agent is modularly isolated and defined under `agents/<name>/`:
- **Persona:** `agents/<name>/persona.md` (defines core behavior, personality, and tone constraints).
- **Profile:** `agents/<name>/agents/<name>.md` (defines core duties, active local skills, and external skills access).
- **Local Skills:** `agents/<name>/skills/` (a directory of short, pulverized/topic-specific markdown files).
- **Configuration:** `agents/<name>/.agent/config.json` (source profile metadata; installed model selection belongs to the host).
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
   Regenerate the thin Claude, AGY, and Codex integrations from the existing
   canonical source files:
   ```bash
   uv run python -m solomon_harness.cli compile
   ```

## Installed Projects

This file imports `agents/AGENTS.md` because this repository is the harness
source checkout. In a consumer repository, `solomon-harness init` places the
canonical catalog at `.agents/solomon`; `.agents/agents/`,
`.agents/skills/`, `.agents/hooks.json`, and `.agents/plugins/solomon/`
(including its `mcp_config.json`) are thin AGY
adapters that point there. Claude and
Codex receive equivalent adapters from the same catalog. Rebuild them with
`solomon-harness compile` and remove unchanged manifest-owned output with
`solomon-harness uninstall`.

## Development and Testing Standards
- **Strict TDD:** Write failing tests first, observe them fail, implement the fix, and then refactor.
- **SurrealDB Memory:** The primary memory backend is SurrealDB, with SQLite as the fallback store. Use the `solomon-memory` MCP tools to persist and query decisions, sessions, handoffs, and issues.
- **Style Rules:** No AI cliches, ornaments, or emojis in generated content. Keep all communication professional and direct.
