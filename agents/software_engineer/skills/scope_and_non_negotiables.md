# Software Engineer Best Practices

Purpose: the working standard for implementing features and fixes in solomon-harness with strict TDD, clean Python, SOLID design, disciplined debugging, and Git Flow with conventional commits.

## Scope and non-negotiables


- Every logical change is driven by a test first. No production code is written before a failing test exists for it.
- Work only on `feature/*` or `bugfix/*` branches cut from `develop`. Never commit to `main` or `develop` directly.
- The core technology is Python. Use `pytest` for tests, `ruff` for lint and format, `mypy --strict` for types, `pytest-cov` for coverage.
- Preserve existing docstrings and comments unrelated to your change. Do not delete or rewrite them unless the user asks.
- Before coding a non-trivial feature, write `PLAN.md` (target files, edge cases, verification criteria) as the workflow requires.

## Common pitfalls

- Production code written before a failing test exists for it — it breaks the test-first non-negotiable and yields tests that confirm the implementation instead of specifying behavior.
- Commits landing directly on `main` or `develop` instead of a `feature/*` or `bugfix/*` branch — it bypasses review and the branch discipline this scope mandates.
- A non-trivial feature started without `PLAN.md` — target files, edge cases, and verification criteria were never fenced, so scope creep is invisible in review.
- Docstrings or comments unrelated to the change deleted or rewritten in the diff — the scope requires preserving them unless the user explicitly asks otherwise.
- A tool outside the sanctioned set (`pytest`, `ruff`, `mypy --strict`, `pytest-cov`) introduced without an ADR — deviating from a project default requires a recorded decision, not a silent substitution.
- The type gate loosened by running `mypy` without `--strict` or accepting new errors — the non-negotiable names the strict invocation, so anything weaker is an unrecorded waiver.

## Definition of done

- [ ] Every production change in the diff traces to a test that failed first; no line of code exists that a test did not demand.
- [ ] The work sits on a `feature/*` or `bugfix/*` branch; `main` and `develop` received no direct commits.
- [ ] For a non-trivial feature, `PLAN.md` exists with target files, edge cases, and verification criteria, and the diff touches nothing outside its target-files list.
- [ ] `pytest`, `ruff` (lint and format), `mypy --strict`, and `pytest-cov` all ran clean on the change.
- [ ] Docstrings and comments unrelated to the change are intact, byte for byte, in the diff.
- [ ] Any deviation from a non-negotiable in this file is backed by an accepted ADR, not an inline justification in the PR.
