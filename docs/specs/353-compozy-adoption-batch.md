# Spec 353: Unify and deliver the 15 remaining compozy-adoption packages

- Issue: #353 · Status: implemented
- Date: 2026-07-17 · Author: multi-specialist (compozy benchmark, maintainer-directed)

## Context

The 2026-07-17 compozy benchmark produced epic #341 (16 packages). Package 1 shipped as #347. The maintainer directed the remaining 15 to be unified into one branch and delivered together. Six specialist agents authored the new skills in parallel; the shared command/doc/test surfaces and the Python code were integrated on the main thread.

## Problem

Fifteen approved adoption packages were unbuilt. Delivered separately they would span many sessions; the maintainer wanted them unified.

## Requirements

Five code packages (nested stall watchdog; park-don't-fail; bounded remediation rounds; cross-round review dedup; blocked-issue selection guard plus refine exploration pass) and ten skill/wiring packages (AI test-hygiene scan; persona-driven exploratory QA with the docs/qa tree and untested-reset honesty rule; memory promotion/compaction; skill-authoring craft; no-workarounds escape valve and three-strikes tripwire; ADR reconciliation gate; vertical-slice sizing doctrine; loop outcome integrity; scoped subagent dispatch; opt-in council debate). Each behavior/skill/wiring is pinned by a fitness or unit test; the full suite and validators pass.

## Implementation Pointers

- `solomon_harness/loop_watchdog.py` (new), `solomon_harness/workflows.py`, `solomon_harness/loop_log.py` (`consecutive_runs_for_target`/`remediation_limit_reached`), `solomon_harness/tools/database_client.py` (LOOP_RUN_STATUSES gains `skipped`, `parked`).
- Ten skills under `agents/*/skills/`; command wiring in `.claude/commands/solomon-{review,start,refine,idea,scan-arch,scan-dedup}.md`; `docs/qa/` scaffold; `docs/solomon-workflow.md` selection guards; `docs/adrs/README.md` reconciliation convention.
- ADR-0040 (watchdog/park); ADR-0016 vocabulary table amended (skipped, parked).
- Tests: `tests/test_loop_watchdog.py`, `tests/test_loop_log.py`, `tests/test_compozy_adoption_batch.py`, additions to `tests/test_workflows.py`/`tests/test_loop_run.py`/`tests/test_typed_states.py`.

## Acceptance Criteria

- Given each of the fifteen packages, when the suite runs, then a fitness or unit test pins its behavior/skill/wiring.
- Given the validators, when CI runs, then `check-skill-depth.py`, `document-skills.py`, the integrations drift test, and the full pytest suite pass; mirrors are regenerated.
- Given the five code packages, when their unit tests run, then each passes through a red-green cycle.

## Verification

```
uv run pytest -q
uv run python scripts/check-skill-depth.py
```

## Design Constraints

House skill format (>600-word body, "Use when" trigger, closing sections); fitness-test-pinned prompt wiring; typed-state ADR discipline (closed vocabulary via OVERWRITE migration, ADR-0016/0039); no narrative code comments; emoji-free; the human merge gate unchanged.

## Out of Scope

Worktree-reset-before-retry for park (terminal cap is the safety net); a formal numbered amendment ADR for ADR-0031's reconciliation convention (documented in README as a follow-up).

## Traceability

- Issue: #353 (epic #341 packages 2-16)
- ADR: docs/adrs/0040-stall-watchdog-and-parked-runs.md
- PR: opened by this branch
