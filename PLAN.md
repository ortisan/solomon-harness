# Plan: feat(agents): add educational_psychologist specialist agent

- Issue: #68 https://github.com/ortisan/solomon-harness/issues/68
- Branch: feature/add-educational-psychologist

## Problem Statement
The harness roster currently lacks a specialist covering psychopedagogy or the learning sciences. Any learning-facing project driven by the harness has no dedicated expert to consult. We need to introduce an `educational_psychologist` agent whose skills are grounded in established, evidence-based methodologies.

## Proposed Change
1. Create folder structure `agents/educational_psychologist/` with `persona.md`, `agents/educational_psychologist.md`, `.agent/config.json`, and 9 skills under `skills/`.
2. Register the agent in `scripts/validate-agents.py`.
3. Add the agent to `agents/AGENTS.md`.
4. Create test suite `tests/test_educational_psychologist.py` to cover agent validations.

## Target Files
- `agents/educational_psychologist/persona.md`
- `agents/educational_psychologist/agents/educational_psychologist.md`
- `agents/educational_psychologist/.agent/config.json`
- `agents/educational_psychologist/skills/cognitive_load_theory.md`
- `agents/educational_psychologist/skills/retrieval_practice.md`
- `agents/educational_psychologist/skills/distributed_practice.md`
- `agents/educational_psychologist/skills/dual_coding.md`
- `agents/educational_psychologist/skills/backward_design.md`
- `agents/educational_psychologist/skills/evidence_based_sourcing.md`
- `agents/educational_psychologist/skills/definition_of_done.md`
- `agents/educational_psychologist/skills/common_pitfalls.md`
- `agents/educational_psychologist/skills/scope_and_non_negotiables.md`
- `scripts/validate-agents.py`
- `agents/AGENTS.md`
- `tests/test_educational_psychologist.py`

## Edge Cases & STRIDE
- Platitude detection: The manual gate must reject generalist advice.
- Verification script `scripts/check-skill-depth.py` must run and exit 0 for this agent.
- STRIDE: No input validation required since these are static markdown/config files, but we must verify that no code execution is introduced in active skills and no untrusted markdown injection occurs.

## TDD Loop Breakdown
1. **Step 1 (Red)**: Add tests to `tests/test_educational_psychologist.py` validating that the folder structure, config format, and allow-list attributions are checked. Run and fail.
2. **Step 2 (Green)**: Implement `agents/educational_psychologist/` directory and files, including the 9 skills with allow-list attributions and 600+ word counts. Run tests to pass.
3. **Step 3 (Red)**: Write a test asserting that `scripts/validate-agents.py` checks `educational_psychologist.md`. Run and fail.
4. **Step 4 (Green)**: Register the agent in `scripts/validate-agents.py` and run `scripts/document-skills.py`. Run tests to pass.
5. **Step 5 (Red/Green)**: Run `scripts/check-skill-depth.py` on the agent and ensure it passes, refactoring any skills that do not clear the depth gate.

## Verification Criteria
- `python scripts/check-skill-depth.py educational_psychologist` exits 0.
- `python scripts/validate-agents.py` exits 0.
- `python scripts/document-skills.py` exits 0.
- `solomon-harness compile` exits 0.
- `python -m unittest tests.test_educational_psychologist` passes.
