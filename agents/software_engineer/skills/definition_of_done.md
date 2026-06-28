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
