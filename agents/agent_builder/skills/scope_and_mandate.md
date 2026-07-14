---
name: scope-and-mandate
description: Governs the creation, scaffolding, and registration of new specialist agents — the mandated agents/<name>/ directory layout, path-traversal and snake_case-name confinement checks, and the registry updates to agents/AGENTS.md, README.md, and the compiled host-tool integrations. Use when scaffolding a brand-new agent directory or verifying a generated agent is safely confined and fully registered.
---

# Agent Builder Scope and Mandate

The Agent Builder specialist agent governs the creation, scaffolding, and registration of new specialist agents within the Solomon Harness ecosystem. By centralizing the scaffolding logic into a dedicated meta-agent, we preserve structural consistency, enforce formatting gates, and ensure clean separation of concerns between routing/brokerage (managed by the practice curator) and file-system code generation.

## Agent Directory Layout Standards

Every specialist agent must occupy a dedicated subdirectory directly under the `agents/` root of the workspace. The generated structure must adhere to the following layout without deviation:
- `agents/<name>/persona.md` — The agent's operational persona, defining its tone, perspective, and domain of expertise.
- `agents/<name>/agents/<name>.md` — The role profile, detailing the core duties, active skills, and required competencies.
- `agents/<name>/skills/` — A directory containing markdown skill files providing granular, topic-specific reference guides.
- `agents/<name>/.agent/config.json` — Configuration file specifying model parameters, memory constraints, and tenant identifiers.

When creating these files, the Agent Builder must populate them with clean templates that contain placeholders conforming to the system requirements (such as the ban on emojis, icons, or AI cliches).

## Security and Confinement Verification

To prevent path traversal attacks or accidental filesystem writes outside the designated boundary, the Agent Builder must enforce strict security checks:
1. Target Path Resolution: Retrieve the real path of the destination using absolute canonical resolution (`os.path.realpath` or `Path.resolve`).
2. Confinement Assertion: Explicitly check that the resolved target path starts with the real path of the repository's `agents/` folder. If the path escapes the agents folder (for example, containing `../` sequences that resolve outside the tree), the operation must immediately raise a value error and halt.
3. Filename Validation: Validate the new agent's name against a strict snake_case regex (`^[a-z0-9_]+$`). Any name containing uppercase letters, hyphens, or special characters must be rejected.

## Registry Integration and Compilation

Once the agent files are successfully scaffolded on disk, the Agent Builder is responsible for updating the central registry files:
1. `agents/AGENTS.md`: Add the new agent to the index list in alphabetical order, with a clear one-sentence summary of its primary focus.
2. `README.md`: Update the spelt-out count of role-specific agents and add the new agent to the markdown table detailing all specialist roles.
3. Integration Compilation: Invoke the harness compilation process (`solomon-harness compile` or the equivalent programmatic script) to regenerate the host-tool integrations, such as `.claude/agents/<name>.md` profiles, ensuring that the new agent is immediately discoverable.

## Verifying the Integration Sync Points

A newly scaffolded agent is not complete until every downstream reference to it is consistent; the Agent Builder treats each sync point as a checklist item to verify, not merely as a file to write once and forget.

- `agents/AGENTS.md` roster entry: after inserting the new agent into the "The specialist agents" list in alphabetical order with a one-sentence summary, read the file back and confirm the new line appears exactly once, sits between its correct alphabetical neighbors, and that no adjacent agent's line was accidentally altered, duplicated, or dropped in the edit.
- `README.md` agent count and table: the README states a spelt-out count of role-specific agents and lists every agent in a markdown table with a folder link and a one-line description. After editing, recompute the count from the number of `agents/*/agents/*.md` files on disk, confirm the spelt-out number in the README prose matches that count exactly, and confirm the new row was appended to the table with a working relative link and a description consistent with the profile.
- `scripts/validate-agents.py` `REQUIRED_KEYWORDS` registration: this dictionary maps each profile filename to the literal keywords CI checks for inside that profile's body. A new agent needs its own entry in the dictionary — the agent's title-case name plus three to six domain keywords drawn directly from its Core Duties — or the profile will compile cleanly but fail the keyword gate on the next CI run. Add this entry in the same commit that adds the profile, never as a follow-up, so the keyword gate is never red between commits.
- Regenerating `.claude/agents/` via `compile`: the host-tool integration files under `.claude/agents/` and `.gemini/commands/` are generated artifacts, never hand-edited. Run `uv run python -m solomon_harness.cli compile` after every scaffold, then confirm `.claude/agents/<name>.md` exists, is non-empty, and reflects the persona and duties just written, so the new agent is discoverable in the same session instead of after a separate manual step.

Treat a scaffold as done only once all four sync points have been independently re-read and confirmed, not assumed from the fact that the scaffolding command or the compile step exited without error; a clean exit code proves the writer did not crash, not that the roster, the README, the keyword gate, and the compiled profile all agree with one another.

## Common pitfalls

- Generating template files containing prohibited AI cliches such as 'delve', 'leverage', or 'feel free'.
- Writing files without validating the absolute canonical path, allowing potential path traversal outside the project directory.
- Forgetting to run the compilation step after scaffolding, which leaves the agent unregistered in the host-tool configurations.
- Using hyphens or uppercase letters in the agent directory name instead of strict snake_case, violating formatting checks.
- Failing to verify that all markdown skill files created under the new agent's skill directory include the required header sections.

## Definition of done

- [ ] All directories and files are created under the validated `agents/` path.
- [ ] No path traversal escape is possible via user-controlled inputs.
- [ ] The new agent is registered alphabetically in `agents/AGENTS.md` and documented in the main `README.md`.
- [ ] The Spelt-out agent count in `README.md` is updated and matches the file system count.
- [ ] Compilation succeeds without errors and the generated integration profiles are present.
- [ ] No emojis, icons, or prohibited AI cliches exist in the generated template files.
