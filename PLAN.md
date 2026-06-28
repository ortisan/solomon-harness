# PLAN — #6 delivery-spine skills to canonical depth (software_architect + sre)

Issue: #6 `feat(agents): upgrade delivery-spine agent skills to the canonical depth standard`
Branch: `feature/architect-sre-skills-canonical-depth` (worktree `sh-6`, off `origin/main` @ 0f36018)

## Problem statement

Epic #6 re-scoped to a depth upgrade and judged `software_architect` and `sre` as
"already meet the bar — no child, spot-review only", using a `<200w` "thin"
threshold. The epic's own acceptance criteria, however, set the bar at
`>= ~600 words` plus `## Common pitfalls` and `## Definition of done` plus a named
standard/tool and a worked example. A spot-review against that written bar fails:
14 role-core skills across the two agents are under it. The required spot-review
therefore does not confirm compliance, so the epic cannot close honestly until
these are addressed. This slice closes the gap for both agents.

## Scope decision (read before implementing)

Deepen all 14 sub-bar role-core skills to the canonical bar. Three of them are
meta/scope files that currently restate the shared `agents/AGENTS.md` rules or act
as an applicability gate. They are NOT exempted; instead they are rewritten as
genuine single-concern skills so reaching `>= 600w` adds real, role-specific
guidance rather than restating shared rules (which the epic's RAID tells the review
gate to reject). The reframe per meta file:

- `software_architect/when_this_skill_applies.md` — from a one-paragraph gate into
  an "architecture engagement model": which artifact for which decision, the
  blast-radius / cost-of-reversal triage test, a worked triage example, ADR-vs-
  commit-note heuristics.
- `software_architect/mandatory_project_competencies_to_honor_in_any_design.md` —
  from a restatement of AGENTS.md into "how to honor each competency at design
  time": testability seams, consumer-driven contract tests (Pact), a worked
  STRIDE-per-container table, fitness functions (ArchUnit / import-linter).
- `sre/mandatory_competencies_carried_into_sre_work.md` — from a restatement into
  "how SRE operationalizes each competency": IaC test pyramids, signed-artifact
  supply chain, structured-log/trace propagation, with named tools and an example.

### Deepening targets (14)

`software_architect` (7):
- `when_this_skill_applies.md` (100w)
- `solid_and_structural_discipline.md` (207w)
- `non_functional_requirements.md` (220w)
- `architectural_decision_records.md` (242w)
- `mandatory_project_competencies_to_honor_in_any_design.md` (273w)
- `design_contracts_as_component_boundaries.md` (307w)
- `c4_model_diagrams.md` (370w)

`sre` (7):
- `disaster_recovery.md` (201w)
- `load_and_resilience_testing.md` (205w)
- `incident_response_and_runbooks.md` (238w)
- `high_availability.md` (266w)
- `infrastructure_and_deployment_pipelines.md` (270w)
- `mandatory_competencies_carried_into_sre_work.md` (294w)
- `reliability_targets_sli_slo_sla_error_budgets.md` (439w)

## Proposed change and boundary touched

Documentation only. Rewrite each of the 11 skills to the canonical format:
sharp one-paragraph summary; topic sections naming concrete standards/tools with
versions/thresholds and at least one worked example; `## Common pitfalls` (each
with the reason a reviewer rejects it); `## Definition of done` checklist. Then
regenerate the two agent profiles' Active Skills with `scripts/document-skills.py`.
No production Python, no public contract, no data model, no dependency change.

## Target files

- All 7 `agents/software_architect/skills/*.md` listed above.
- All 7 `agents/sre/skills/*.md` listed above.
- `agents/software_architect/agents/software_architect.md` and `agents/sre/agents/sre.md` (Active Skills block, regenerated only)
- `scripts/check-skill-depth.py` (new, the mechanical gate)

## Edge cases (observable outcomes)

- A deepened skill must not restate shared AGENTS.md rules; it stays single-concern.
- `document-skills.py` must still parse the first paragraph as the one-line summary,
  so the opening paragraph stays a single sharp sentence-led paragraph.
- `solomon-harness compile` must not mutate tracked source beyond the regenerated
  Active Skills blocks.
- Named standards must be real and current (e.g. C4 model levels; ISO/IEC 25010
  quality attributes; DR RTO/RPO; SLI/SLO/SLA + error-budget math; k6/Locust for load).

## Red/green breakdown (mechanical depth proxy is the test)

The acceptance criterion is a mechanical proxy, so the "test" is a depth check, run
red-before-green per file:

1. Add `scripts/check-skill-depth.py` asserting, for every non-shared role-core
   skill in both agents' dirs: `>= 600` words, presence of `## Common pitfalls` and
   `## Definition of done`. Run it: it fails for the 14 sub-bar files (Red). Commit the gate.
2. Deepen the 7 `software_architect` skills. Re-run: the architect subset passes
   (Green). Commit.
3. Deepen the 7 `sre` skills. Re-run: all pass (Green). Commit.
4. Regenerate Active Skills (`document-skills.py`); commit the profile diff.
5. Refactor pass: trim any restated shared rules, tighten summaries.

Each step is one Conventional Commit ending with `Refs #6`.

## STRIDE

Not applicable: documentation-only change, no input/auth/data/external surface.
(The depth-check script reads repo files only; no external input.)

## Verification criteria

- `python scripts/check-skill-depth.py` passes for every non-shared role-core skill
  in both agents' dirs (`>= 600w` + both sections).
- Each deepened skill names at least one concrete standard/tool and shows one worked example.
- No deepened skill restates shared AGENTS.md rules verbatim; each stays single-concern.
- `uv run python scripts/document-skills.py` exits 0 and Active Skills renders cleanly.
- `uv run python -m solomon_harness.cli compile` produces no tracked-source diff
  beyond the regenerated Active Skills blocks.

## Epic closeout note

This slice covers architect + sre. With #9-#12 already Done, delivering this lets
the epic's spot-review pass against the written bar. The PR will use `Refs #6`
(not `Closes`) and recommend closing the epic after the architect/sre spot-review
re-runs green, leaving the close decision to the product owner.
