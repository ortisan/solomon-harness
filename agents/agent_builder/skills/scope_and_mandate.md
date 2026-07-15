---
name: scope-and-mandate
description: Governs the creation, scaffolding, and registration of new specialist agents in either a source checkout or an installed consumer, with path confinement, canonical rules updates, and compiled Claude, AGY, and Codex integrations. Use when scaffolding a brand-new agent directory or verifying a generated agent is safely confined and fully registered.
---

# Agent Builder Scope and Mandate

The Agent Builder specialist agent governs the creation, scaffolding, and registration of new specialist agents within the Solomon Harness ecosystem. By centralizing the scaffolding logic into a dedicated meta-agent, we preserve structural consistency, enforce formatting gates, and ensure clean separation of concerns between routing/brokerage (managed by the practice curator) and file-system code generation.

## Agent Directory Layout Standards

Every specialist agent must occupy a dedicated subdirectory below the canonical catalog. The catalog root is `agents/` while authoring this source checkout and `.agents/solomon/agents/` in an installed consumer. The generated structure must adhere to this layout without deviation:
- `<catalog-root>/<name>/persona.md` — The agent's operational persona, defining its tone, perspective, and domain of expertise.
- `<catalog-root>/<name>/agents/<name>.md` — The role profile, detailing the core duties, active skills, and required competencies.
- `<catalog-root>/<name>/skills/` — A directory containing markdown skill files providing granular, topic-specific reference guides.
- `<catalog-root>/<name>/.agent/config.json` — Configuration file specifying model parameters, memory constraints, and tenant identifiers.

Consequently, the installed role and configuration paths are
`.agents/solomon/agents/<name>/agents/<name>.md` and
`.agents/solomon/agents/<name>/.agent/config.json`; neither may be shortened to a
project-root path.

When creating these files, the Agent Builder must populate them with clean templates that contain placeholders conforming to the system requirements (such as the ban on emojis, icons, or AI cliches).

## Security and Confinement Verification

To prevent path traversal attacks or accidental filesystem writes outside the designated boundary, the Agent Builder must enforce strict security checks:
1. Target Path Resolution: Retrieve the real path of the destination using absolute canonical resolution (`os.path.realpath` or `Path.resolve`).
2. Confinement Assertion: Explicitly check that the resolved target remains below the selected canonical catalog root. If the path escapes that root (for example, containing `../` sequences that resolve outside the tree), the operation must immediately raise a value error and halt.
3. Filename Validation: Validate the new agent's name against a strict snake_case regex (`^[a-z0-9_]+$`). Any name containing uppercase letters, hyphens, or special characters must be rejected.

## Registry Integration and Compilation

Once the agent files are successfully scaffolded on disk, the Agent Builder is responsible for updating the central registry files:
1. Canonical rules: add the new agent to the index list in alphabetical order, with a clear one-sentence summary of its primary focus. The target is `agents/AGENTS.md` in this source checkout and `.agents/solomon/AGENTS.md` in an installed consumer.
2. Source checkout only: update the harness's own `README.md` count/table and `scripts/validate-agents.py` keyword registration. In an installed consumer, do not read or modify the product repository's `README.md`, scripts, agent count, or documentation tables.
3. Integration Compilation: invoke `solomon-harness compile` (or the equivalent programmatic operation) to regenerate `.claude/agents/<name>.md`, `.agents/agents/<name>/agent.md`, and `.codex/agents/<name>.toml`, ensuring that the new agent is immediately discoverable in all three hosts.

## Verifying the Integration Sync Points

A newly scaffolded agent is not complete until every downstream reference to it is consistent; the Agent Builder treats each sync point as a checklist item to verify, not merely as a file to write once and forget.

- Canonical rules roster entry: after inserting the new agent into the "The specialist agents" list in alphabetical order, read the selected rules file back and confirm the line appears exactly once, sits between its correct alphabetical neighbors, and no adjacent line was altered, duplicated, or dropped.
- Source checkout only, harness `README.md` agent count and table: recompute the count from `agents/*/agents/*.md`, confirm the spelt-out number matches, and confirm the new row has a working relative link and a description consistent with the profile. Skip this sync point entirely in an installed consumer so product documentation remains product-owned.
- Source checkout only, `scripts/validate-agents.py` `REQUIRED_KEYWORDS` registration: add the profile filename, title-case name, and three to six domain keywords in the same commit. Skip this sync point in installed consumers; their scripts are outside the harness ownership boundary.
- Regenerating all host adapters via `compile`: Claude's `.claude/agents/<name>.md`, AGY's `.agents/agents/<name>/agent.md`, and Codex's `.codex/agents/<name>.toml` are generated metadata, never hand-edited. Run `solomon-harness compile` after every scaffold, then confirm all three files exist, are non-empty, and point to the same canonical profile. In an installed consumer that profile is `.agents/solomon/agents/<name>/agents/<name>.md`; this source checkout retains `agents/<name>/agents/<name>.md` as its authoring location.

Treat a scaffold as done only once every sync point applicable to the current layout has been independently re-read and confirmed. A source checkout includes the two source-only checks; an installed consumer includes only the canonical catalog/rules and compiled-host checks.

## Common pitfalls

- Generating template files containing prohibited AI cliches such as 'delve', 'leverage', or 'feel free'.
- Writing files without validating the absolute canonical path, allowing potential path traversal outside the project directory.
- Forgetting to run the compilation step after scaffolding, which leaves the agent unregistered in the host-tool configurations.
- Using hyphens or uppercase letters in the agent directory name instead of strict snake_case, violating formatting checks.
- Failing to verify that all markdown skill files created under the new agent's skill directory include the required header sections.

## Definition of done

- [ ] All directories and files are created under the validated canonical catalog path.
- [ ] No path traversal escape is possible via user-controlled inputs.
- [ ] The new agent is registered alphabetically in the canonical rules file.
- [ ] Source checkout only: the harness `README.md` count/table and `scripts/validate-agents.py` entry are updated; installed consumers leave product-owned docs and scripts unchanged.
- [ ] Compilation succeeds without conflicts and the Claude, AGY, and Codex integration profiles are present and point to the same canonical profile.
- [ ] No emojis, icons, or prohibited AI cliches exist in the generated template files.
