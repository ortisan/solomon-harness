# PLAN.md: feat(agents): practice_curator — agent definition and cited audit of one delivery

Problem statement: The `practice_curator` agent does not exist yet. This slice creates the agent definition, profile, persona, config, and its first capability: a sourced gap report on one delivery with cited evidence (issue #18).

## Proposed changes
- Create the folder `agents/practice_curator/` with `persona.md`, profile `agents/practice_curator/agents/practice_curator.md`, `skills/`, and `.agent/config.json`.
- Create skills: `auditing_delivered_work.md`, `sourcing_the_state_of_the_art.md`, `benchmarking_across_domains.md`, `scope_and_non_negotiables.md`.
- Update `agents/AGENTS.md` to index `practice_curator`.
- Regenerate Active Skills and compile host-tool integrations by running `cli compile` / `document-skills.py`.

## Target files
- `agents/practice_curator/persona.md`
- `agents/practice_curator/agents/practice_curator.md`
- `agents/practice_curator/.agent/config.json`
- `agents/practice_curator/skills/auditing_delivered_work.md`
- `agents/practice_curator/skills/sourcing_the_state_of_the_art.md`
- `agents/practice_curator/skills/benchmarking_across_domains.md`
- `agents/practice_curator/skills/scope_and_non_negotiables.md`
- `agents/AGENTS.md`

## Edge cases
- Empty or invalid PR/diff input for audit.
- Sourcing a best practice with fewer than 2 dated sources (falls back to "insufficient evidence").
- Attempting to edit other agent files (blocked/forbidden).
- No gaps identified in a delivery (returns "no gap found").

## TDD breakdown
1. **Red**: Verify agent structure tests fail.
   **Green**: Define basic agent structure (folder, persona, profile, config).
   *Commit: feat(agents): define practice_curator agent structure Refs #18*
2. **Red**: Verify depth and quality metrics tests fail on skills.
   **Green**: Author skills `auditing_delivered_work.md`, `sourcing_the_state_of_the_art.md`, `benchmarking_across_domains.md`, `scope_and_non_negotiables.md` meeting >= 600 words, no cliches, required sections.
   *Commit: feat(agents): author practice_curator skills Refs #18*
3. **Red**: Index and compilation validation tests fail.
   **Green**: Run compile, document-skills, and add practice_curator to `agents/AGENTS.md`.
   *Commit: feat(agents): compile practice_curator agent integrations Refs #18*

## STRIDE notes
- **Spoofing/Elevation of Privilege**: No active scripts run dynamically in this slice; skills are purely descriptive/analytical instructions.
- **Information Disclosure**: Audited artifacts are local repository diffs; no external secrets or environment variables are processed.

## Verification criteria
- `uv run pytest tests/test_practice_curator.py` passes.
- All 700+ tests pass.
