# ADR-0026: Skill discovery frontmatter and profile delegation cues

- Status: accepted
- Date: 2026-07-14
- Deciders: software_architect, practice_curator, agent_builder
- Issue: n/a (direct user directive)

## Context and problem statement

The roster's 225+ skill files are deep in content but carry no discovery
metadata: a host tool (or another agent) choosing which skill to load has only
the filename and the first body paragraph, truncated to 140 characters by
`scripts/document-skills.py`. The generated Claude Code subagents in
`.claude/agents/` describe each agent with the profile's opening sentence — a
role label, not a delegation trigger — so automatic delegation by the host tool
under-fires. Meanwhile the ecosystem converged on the open Agent Skills format
(SKILL.md), whose core is exactly this metadata: a `name` and a third-person
`description` stating what the skill does and when to use it, pre-loaded so the
body is read only when relevant. Profiles also diverged structurally (some
lacked `## Outputs`; handoff relationships lived only in prose), and the
600-word depth bar ran in CI against just two agents.

## Decision drivers

- Skill and agent selection quality: descriptions with explicit triggers are
  what host tools use to route work; role labels under-trigger.
- Alignment with the open Agent Skills convention without breaking the house
  single-file, `snake_case.md` format and its tooling chain
  (`document-skills.py`, `check-skill-depth.py`, `generate-integrations.py`).
- Enforceability: every new convention must be machine-checked in CI, not
  aspirational.

## Considered options

- **Option 1: Full migration to the Agent Skills directory layout** — each
  skill becomes `<skill-name>/SKILL.md` with hyphenated gerund names and
  bundled resources. Maximum portability, but rewrites the entire tooling and
  test chain and abandons the mandated snake_case single-file format.
- **Option 2: Adopt the spec's discovery metadata inside the house format** —
  add YAML frontmatter (`name`, `description` with a literal "Use when"
  trigger) to every skill file, standardize profiles (Delegation cue, Outputs,
  Handoffs), derive subagent descriptions from the cue, and extend the CI
  gates to enforce all of it across the whole roster.
- **Option 3: No format change** — only add new agents and skills.

## Decision outcome

Chosen option "Option 2", because it captures the substance of the open format
(description-driven discovery, progressive disclosure: metadata first, body on
demand) while preserving the existing pipeline and CI gates. Concretely:

- Every `agents/*/skills/*.md` opens with frontmatter: `name` equal to the
  filename stem with underscores replaced by hyphens (the spec's charset), and
  a single-line third-person `description` (max 1024 characters) that states
  what the skill governs and carries a literal `Use when` trigger.
- `scripts/check-skill-depth.py` enforces the frontmatter contract in the
  repo-wide format gate, measures the 600-word depth bar on the body only, and
  scans the whole roster by default instead of two hand-picked agents.
- `scripts/document-skills.py` prefers the frontmatter description when
  building each profile's Active Skills list.
- Every profile carries a `## Delegation cue` section (one `Use this agent
  when ...` sentence); `scripts/generate-integrations.py` emits the subagent
  description as the profile's opening line plus that cue, so generated
  subagents state both what the agent does and when to delegate to it.
- `solomon_harness.bootstrap.scaffold_new_agent` emits the new shape, so new
  agents are born compliant.

### Consequences

- Positive: host tools and orchestrators can route to the right agent and
  skill from metadata alone; the profile skill lists carry authored one-liners
  instead of truncated first sentences; the depth bar now protects all agents.
- Negative: every skill file gained a frontmatter block (one-time churn across
  the tree), and externally sourced skills installed via `solomon-harness
  skills add` must gain frontmatter to pass the gate.

## Common pitfalls

- Writing the description as a role label without the "Use when" trigger; the
  format gate rejects it because trigger-less descriptions under-fire.
- Padding a shallow skill over the depth bar with a long description; the word
  count deliberately excludes frontmatter.

## Definition of done

- [ ] `scripts/check-skill-depth.py` exits 0 with no arguments on the full tree.
- [ ] `scripts/validate-agents.py` and the README roster tests pass.
- [ ] `.claude/agents/*.md` regenerated with cue-bearing descriptions.
