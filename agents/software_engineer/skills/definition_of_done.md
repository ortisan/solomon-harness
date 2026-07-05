# Software Engineer Definition of Done

The exit gate for implementation work: a change ships only when every item below holds, from the first red test to the reviewed pull request. The pitfalls name the ways this checklist gets ticked without being true; check them before claiming done.

## Common pitfalls

- Declaring TDD satisfied because tests exist in the final diff — a test never observed red proves nothing, so the "failing test existed first" item is unverified and the test may assert nothing.
- Reporting suite-wide coverage instead of coverage on the changed code — the 90 percent line-and-branch floor applies to the diff, and a large untouched suite hides an untested change.
- Ticking the mocking item while tests still hit the network, the wall clock, or a real database — the suite becomes nondeterministic and order-dependent, which the checklist explicitly forbids.
- Running plain `mypy` or skipping the `ruff` format check and calling the gate green — the standard is `mypy --strict` with no new warnings, and a looser invocation is a silent waiver.
- Wiring new infrastructure directly into domain code and marking the hexagon item done — without a port and its adapter, swapping the dependency later forces edits inside the core.
- Closing a bug with a fix but no permanent regression test — the defect returns with the next refactor, and the regression-test item was never met.
- Marking work done from a local branch with mixed or non-conventional commits and no reviewed pull request — integration via a reviewed PR on a `feature/*` or `bugfix/*` branch is part of done, not follow-up.

## Definition of done


- A failing test existed first for every behavior, was observed red, and now passes.
- Full `pytest` suite is green; changed code has at least 90 percent line and branch coverage with meaningful assertions.
- All external services are mocked; tests are deterministic and order-independent.
- `ruff` (lint and format) and `mypy --strict` pass with no new warnings.
- Public functions are typed and named for intent; nesting and complexity are within the stated limits.
- Edge cases, error paths, and divide-by-zero/overflow/shape guards are covered where applicable.
- Core domain stays framework-free; new infrastructure sits behind a port and its adapter.
- STRIDE review noted in `PLAN.md` for boundary-touching features; no secrets in code or history.
- Bug fixes ship with a permanent regression test.
- Work is on a `feature/*` or `bugfix/*` branch with conventional commits, integrated via reviewed pull request; existing unrelated docstrings and comments are intact.
