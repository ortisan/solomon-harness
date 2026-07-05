# Plan: feat(agents): agent_builder meta-agent; delegate new-agent construction

## 1. Problem Statement
Link #49 (feat(agents): agent_builder meta-agent; delegate new-agent construction). Address SOLID/DRY violation and separation of concerns by extracting agent construction/scaffolding logic from `practice_curator` to a dedicated `agent_builder` meta-agent.

## 2. Proposed Change and Boundary
- Create `agents/agent_builder` directory containing its definition (`persona.md`, `agent_builder.md`, `config.json`, and default skill `scope_and_mandate.md`).
- Add `agent_builder` to `CORE_AGENTS` in `solomon_harness/agent_selection.py`.
- Refactor `broker_agent` in `solomon_harness/curator.py` to delegate agent building to `solomon_harness/agent_builder.py` (which we will create to represent `agent_builder`'s core construction capability).
- Register `agent_builder` in `agents/AGENTS.md` and run compile to generate `.claude/agents/agent_builder.md`.

## 3. Target Files
- `solomon_harness/agent_selection.py`
- `solomon_harness/curator.py`
- `solomon_harness/agent_builder.py` (new)
- `agents/AGENTS.md`
- `agents/agent_builder/persona.md`
- `agents/agent_builder/agents/agent_builder.md`
- `agents/agent_builder/skills/scope_and_mandate.md`
- `agents/agent_builder/.agent/config.json`

## 4. Edge Cases
- **Invalid agent names**: Handled via regex to ensure only valid snake_case names are allowed.
- **Path traversal / confinement escape**: Strict verification that the target path resolved via realpath starts with the `agents/` directory prefix.
- **Non-interactive/headless execution defaults**: Sensible fallback behaviors when executing without human interaction.

## 5. TDD Breakdown
- **Commit 1**: Write failing test verifying `agent_builder` is included in `CORE_AGENTS` and `select_agents` returns it.
- **Commit 2**: Implement `agent_builder` agent definition files under `agents/agent_builder`, add to `CORE_AGENTS`, register in `agents/AGENTS.md`, and run compile so it becomes green.
- **Commit 3**: Write failing test verifying `broker_agent` delegates to `agent_builder` (e.g. check it calls the new delegate module).
- **Commit 4**: Create `solomon_harness/agent_builder.py` and refactor `broker_agent` to import and delegate to `agent_builder.build_agent`.
- **Commit 5**: Verify all tests in `tests/test_curator.py` pass with zero regressions.

## 6. STRIDE Notes
- **Spoofing/Tampering**: Restrict scaffolding target path to realpath under `agents/` (confinement check).
- **Information Disclosure**: Strict validation of `agent_name` preventing injects or path disclosure.

## 7. Objectively Checkable Verification Criteria
- `select_agents` returns `agent_builder`.
- `agents/agent_builder/` directory exists and contains persona, agent definition, and config.json.
- `solomon-harness compile` command successfully compiles the integrations and generates `.claude/agents/agent_builder.md`.
- `broker_agent` delegates to `solomon_harness/agent_builder.py`.
- Running `uv run pytest` yields passing tests across all modules.
