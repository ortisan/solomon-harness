# PLAN: feat(workflow): practice_curator — autonomous audit trigger on /solomon-release

## Problem statement

Slice 1's audit is only run when someone remembers to invoke it. To make benchmarking continuous, the curator's audit should fire automatically when a delivery lands via `/solomon-release` — and it must never block or fail a release if its tooling is unavailable. (Refs #21)

## Proposed change and the boundary it touches

We will implement an autonomous trigger step/command `audit-trigger` inside `solomon_harness/release.py` and register it as a subcommand of `release`.
During `/solomon-release` closeout, this command will be invoked. It will execute the `practice_curator` agent headless to perform the audit on the delivered artifact.
The trigger will be degrade-safe: any failure or unavailability of the engine/tooling will log `audit skipped: sourcing unavailable` and exit 0, ensuring the release is never blocked.
We will also document the trigger in `docs/solomon-workflow.md` and add the trigger step to `.claude/commands/solomon-release.md`.

## Target files

- `solomon_harness/release.py`
- `.claude/commands/solomon-release.md`
- `docs/solomon-workflow.md`

## Edge cases as observable outcomes

- **Happy path**: Release completed, trigger runs `practice_curator` audit, outputs success.
- **Sourcing/tooling down**: Trigger fails to reach or execute engine/sourcing tool, logs `audit skipped: sourcing unavailable` and exits 0.
- **Agent directory missing**: Curator agent directory not found, logs `audit skipped: curator agent directory not found` and exits 0.

## TDD breakdown

1. **Red**: Write tests for `cmd_audit_trigger` checking success and degrade-safe execution (done).
2. **Green**: Implement `cmd_audit_trigger` in `solomon_harness/release.py` to make the unit tests pass.
3. **Refactor**: Verify ruff check passes and clean up the implementation.
4. **Integration**: Wire the `audit-trigger` subcommand into `release.py`'s command line parser.
5. **Prompting/Docs**: Update `.claude/commands/solomon-release.md` close-out steps and document the trigger in `docs/solomon-workflow.md`.

## STRIDE notes

- **Information Disclosure**: Trigger outputs standard messages and logs error types without leaking internal database configurations or keys.
- **Denial of Service**: The trigger is run with a timeout to prevent it from hanging indefinitely and blocking the execution. It is non-blocking (fails open with exit code 0).
- **Elevation of Privilege**: The subprocess executes the engine using standard user permissions without escalation.

## Objectively checkable verification criteria

- `uv run pytest tests/test_release.py` passes all tests.
- `uv run python -m solomon_harness.release audit-trigger --version 1.0.0` runs successfully or logs degrade message when engine is not set up.
