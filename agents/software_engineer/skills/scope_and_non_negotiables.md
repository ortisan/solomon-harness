# Software Engineer Best Practices

Purpose: the working standard for implementing features and fixes in solomon-harness with strict TDD, clean Python, SOLID design, disciplined debugging, and Git Flow with conventional commits.

## Scope and non-negotiables


- Every logical change is driven by a test first. No production code is written before a failing test exists for it.
- Work only on `feature/*` or `bugfix/*` branches cut from `develop`. Never commit to `main` or `develop` directly.
- The core technology is Python. Use `pytest` for tests, `ruff` for lint and format, `mypy --strict` for types, `pytest-cov` for coverage.
- Preserve existing docstrings and comments unrelated to your change. Do not delete or rewrite them unless the user asks.
- Before coding a non-trivial feature, write `PLAN.md` (target files, edge cases, verification criteria) as the workflow requires.
