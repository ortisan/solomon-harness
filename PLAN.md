# PLAN.md: feat(agents): practice_curator as a capability-broker proxy that acquires missing agents/skills on demand

Problem statement:
This is the parent epic issue #43 for the self-extending fleet model. No code lands directly on this issue; it tracks child issues #46 (Slice A: demand routing), #47 (Slice B: skill acquisition), #48 (Slice C: direct agent scaffolding), #49 (Slice D: agent_builder delegation), and #50 (Slice E: start/refine integration). Slice A is already implemented on main (carrying the capability router core, the curator's capability_broker skill, and ADR-0008). We are initializing this epic's branch to establish the tracking PR and memory state.

## Proposed changes
- Initialize the epic tracking branch `feature/practice-curator-capability-broker-proxy`.
- Verify the slice A implementation (`solomon_harness/capability_router.py`) and its unit tests (`tests/test_capability_router.py`).
- Verify ADR-0008 is accepted and documented.

## Target files
- `PLAN.md` (this file)
- `.solomon/handoffs/issue-43-start-to-review.md` (handoff contract)

## Edge cases
- No direct code changes: Since this is an epic, we do not commit functional code to this branch directly. Instead, we verify slice A, generate the plan, and hand off to Code Review.
- Non-interactive execution: We proceed automatically without prompting the user.

## TDD breakdown
1. **Red**: Run the existing capability router tests to verify they are registered and executable.
2. **Green**: Ensure all 21 tests in `tests/test_capability_router.py` pass successfully.
3. **Refactor**: Verify the architectural design decision is recorded in the ADR and project memory.

## STRIDE notes
- **Spoofing**: Matcher functions are injected as ports/stubs; production LLM call boundaries are clean.
- **Tampering**: Catalog loading strictly enforces path confinement and rejects symlinks.
- **Repudiation**: Decisions and handoffs are logged in the project SurrealDB.
- **Information Disclosure**: Catalog read limits protect memory; no data is leaked.
- **Denial of Service**: Giant catalog files are read-capped to prevent memory exhaustion.
- **Elevation of Privilege**: No fetched code is executed; skills are quarantined.

## Verification criteria
- `uv run pytest tests/test_capability_router.py` passes all 21 tests.
- Handoff contract exists at `.solomon/handoffs/issue-43-start-to-review.md`.
