# Spec 320: Contract-fidelity gates: spec corpus survey, precedence ladder, verification iron law

- Issue: #320 · Status: implemented
- Date: 2026-07-17 · Author: software_engineer (from the compozy benchmark, architect-reviewed)

## Context

The 2026-07-17 benchmark of compozy/compozy surfaced a defense the solomon lifecycle lacked: gates that keep implementing and reviewing agents faithful to the canonical contract instead of a paraphrase of it. Compozy adopted these after seven review rounds approved a deliverable that contradicted the spec's canonical examples. The maintainer directed the adoption; the software_architect evaluation added the solomon-specific canonical-versus-mirror rule for the two acceptance-criteria surfaces.

## Problem

Implementing agents can build from a paraphrase (issue title, PLAN.md) without reading the contract-bearing artifacts; contradictory sources are resolved differently per run or resolved by narrowing the deliverable to the current runtime shape; and completion claims are accepted without same-run verification evidence, letting review approve on engineering quality alone.

## Requirements

1. A software_engineer skill defines the spec corpus survey (inventory and fully read every contract-bearing artifact before any edit) and the contract precedence ladder (machine-checked constraints > contract catalogs > Accepted ADRs > paraphrases), including that the issue body's acceptance criteria are canonical over the spec's mirrored section and that the existing runtime shape is never the contract.
2. A software_engineer skill defines the verification iron law: same-run evidence, verification scope covering claim scope, and a report citing command, exit code, and output.
3. A qa skill defines contract parity as a review gate: field-by-field comparison, parity mismatch is a blocker, engineering quality alone can never earn approval, verdict recorded as a `Contract parity:` line.
4. `/solomon-start` wires the survey before PLAN.md and the verification report before the push confirmation; `/solomon-review` wires parity into the qa lens; the `.gemini` and `.agents` mirrors regenerate.
5. `docs/solomon-workflow.md` defines all three gates; fitness tests pin the load-bearing sentences.

## Implementation Pointers

- `agents/software_engineer/skills/spec_contract_fidelity.md` — survey, ladder, canonical/mirror rule, runtime-shape rule.
- `agents/software_engineer/skills/verification_iron_law.md` — gate sequence, scope parity, report format, failure protocol.
- `agents/qa/skills/spec_contract_parity.md` — corpus assembly, field-by-field walk, hollow-test finding, verdict integration.
- `.claude/commands/solomon-start.md` — survey bullet in step 1 (before the claim bullet); verification-report bullet opening step 6.
- `.claude/commands/solomon-review.md` — parity text appended to the qa-lens bullet in step 2.
- `docs/solomon-workflow.md` — "Contract-fidelity gates" section after the discovered-problem protocol.
- `tests/test_command_gates.py` — "Contract-fidelity gates (#320)" section; assertions run on whitespace-flattened text so prose can re-wrap.
- Regeneration: `uv run python scripts/document-skills.py` and `uv run python scripts/generate-integrations.py`.

## Acceptance Criteria

- Given a start run, when the software_engineer loads context, then the command instructs the spec corpus survey before PLAN.md and PLAN.md lists the contract-bearing artifacts.
- Given contradictory sources, when the implementer resolves them, then the command and skill state the ladder, the canonical/mirror rule, and that a paraphrase never overrides a higher rung.
- Given a completion claim, when the start stage reaches the push confirmation, then a verification report with commands, exit codes, and output summary precedes it.
- Given a review run, when the qa lens executes, then it performs the field-by-field parity check, treats a mismatch as a blocker, and records the `Contract parity:` line.
- Given CI, when the validators run, then the skill-depth gate, the integrations drift test, and the full suite pass.

## Verification

```
uv run pytest tests/test_command_gates.py -q
uv run python scripts/check-skill-depth.py
uv run pytest -q
```

## Design Constraints

Prompt-level gates pinned by fitness tests (the house mechanism for workflow policy — elicitation gate #222, spec bar #280); no new runtime code; no new interactive steps that could hang headless runs; emoji-free professional output; the human merge gate is unchanged (ADR-0019/ADR-0020).

## Out of Scope

- A mechanical AC-equivalence lint between issue body and spec mirror (needs GitHub API access CI lacks; the review-stage prompt check covers it for now).
- The other compozy adoption packages (agent-output audit, QA living tree, loop guardrails, review-round dedup), tracked as separate issues.

## Traceability

- Issue: #320
- ADR: docs/adrs/0038-contract-fidelity-gates.md
- PR: opened by this branch (`feature/contract-fidelity-gates`)
