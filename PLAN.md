# PLAN.md: feat(agents): scaffold, register, and compile a new agent (direct)

Problem statement: When no agent fits and no skill closes the gap, scaffold a new agent directory (`agents/<new>/`) from templates, register it in `agents/AGENTS.md`, run `scripts/document-skills.py` and `solomon-harness compile` to generate integrations, and open a draft PR adding exactly that one agent (#48).

## Proposed changes
- Implement `scaffold_new_agent(workspace_root, name, description)` in `solomon_harness/bootstrap.py` to:
  1. Validate the agent name using a strict regex (`^[a-z0-9_]+$`) and verify the resolved path is confined within `agents/`.
  2. Create the directories `agents/<name>/`, `agents/<name>/agents/`, and `agents/<name>/skills/`.
  3. Write `persona.md`, `agents/<name>.md`, and `skills/scope_and_mandate.md` from templates.
  4. Call `scaffold_agents(workspace_root)` to populate `main.py` and `.agent/config.json`.
  5. Register the new agent alphabetically in `agents/AGENTS.md` under `## The specialist agents`.
  6. Execute `scripts/document-skills.py` to document the new agent's skills.
  7. Run compile (`scaffold_agents` + `_generate_integrations`) to create `.claude/agents/<name>.md`.
- Wire `scaffold` subcommand under `agents` in `solomon_harness/cli.py` to support `solomon-harness agents scaffold <name> --description "<desc>"`.
- Implement unit tests in `tests/test_scaffold_agent.py` to verify scaffolding, validation, AGENTS.md registration, idempotency, compiling, and CLI parsing.

## Target files
- `solomon_harness/bootstrap.py`
- `solomon_harness/cli.py`
- `tests/test_scaffold_agent.py`

## Edge cases
- Invalid agent name (spaces, uppercase, symbols, path traversal like `../foo`).
- Agent directory already exists (idempotency - should print a message and exit cleanly without duplicate PR/scaffolding).
- `agents/AGENTS.md` missing or does not contain `## The specialist agents` section.
- Newly scaffolded agent is correctly discoverable by `discover_agents()`.

## STRIDE notes
- **Elevation of Privilege / Path Traversal**: Creating a new agent with a name like `../../bad_path` could write files outside `agents/`.
  *Mitigation*: Validate the agent name using a strict regex: `^[a-z0-9_]+$` and check confinement using `os.path.realpath`.

## TDD breakdown
1. **Red**: Write a test in `tests/test_scaffold_agent.py` that asserts `scaffold_new_agent` validates name formats, checks path confinement, and creates basic directories and files (`persona.md`, `agents/<name>.md`, `skills/scope_and_mandate.md`).
   **Green**: Implement name validation, path confinement checks, and directory/file creation in `solomon_harness/bootstrap.py`.
   *Commit: test: add basic scaffold validation and directory/file creation tests and implementation*
2. **Red**: Write a test asserting that `scaffold_new_agent` copies `main.py` and `.agent/config.json` via `scaffold_agents(workspace_root)`.
   **Green**: Call `scaffold_agents(workspace_root)` within `scaffold_new_agent`.
   *Commit: test: verify main.py and config.json are scaffolded*
3. **Red**: Write a test asserting that `scaffold_new_agent` registers the new agent alphabetically in `agents/AGENTS.md` under `## The specialist agents` and doesn't create duplicate entries (idempotency).
   **Green**: Parse `agents/AGENTS.md`, insert the new agent alphabetically in the bulleted list under `## The specialist agents`, write it back, and ensure no duplicates.
   *Commit: test: verify AGENTS.md registration and idempotence*
4. **Red**: Write a test verifying that `scripts/document-skills.py` and `_generate_integrations` are invoked, updating the profile file and generating `.claude/agents/<name>.md`.
   **Green**: Wire up `document-skills.py` execution (via subprocess) and compile steps (via `scaffold_agents` and `_generate_integrations`) inside `scaffold_new_agent`.
   *Commit: test: verify compile and document-skills integration*
5. **Red**: Write a test verifying the CLI command `solomon-harness agents scaffold <name> --description <desc>` parses arguments correctly and invokes `scaffold_new_agent`.
   **Green**: Update `solomon_harness/cli.py` to support `agents scaffold` parser and handler.
   *Commit: test: add CLI parser and handler tests and implementation*

## Verification criteria
- Run pytest suite: `PYTHONPATH=. uv run pytest tests/test_scaffold_agent.py` passes.
- Scaffolded agent is listed by `discover_agents`.
- No files under `agents/` are modified other than the newly scaffolded agent and `AGENTS.md` (read-only confinement for other agents).
