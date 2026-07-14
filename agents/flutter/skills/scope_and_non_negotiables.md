---
name: scope-and-non-negotiables
description: States the operational standard for Flutter and Dart changes, covering strict TDD, SOLID modularity, typed Either/Result design contracts at boundaries, mocked external services, and preserved docstrings, applied on feature and bugfix branches. Use when scoping or reviewing any Flutter widget, state, navigation, platform-integration, or test change for baseline compliance.
---

# Flutter and Dart Best Practices

Operational standard for building cross-platform Flutter apps with clean architecture, predictable state, responsive UI, and a trustworthy test suite.

## Scope and non-negotiables


This skill governs every Flutter and Dart change you ship: widget code, state management, navigation, platform integration, and tests. Apply it on `feature/*` and `bugfix/*` branches and commit under Conventional Commits.

Mandatory competencies for this role, restated with concrete targets:

- **Strict TDD (Red, Green, Refactor).** Write the failing test first for every use case, bloc/notifier, repository, and non-trivial widget. No production logic lands without a test that fails before it and passes after.
- **SOLID and high modularity.** One reason to change per class. Depend on abstractions (repository interfaces, not HTTP clients). Keep widgets dumb and push logic into the domain/application layer.
- **Design contracts at boundaries.** Repositories, data sources, and use cases expose typed interfaces. Return `Either<Failure, T>` (fpdart, preferred over the less-maintained dartz) or a sealed `Result` type instead of throwing across layers. Domain never imports `package:flutter`.
- **QA: mock all external services.** No test touches a real network, file system, platform channel, or clock. Use `mocktail`/`mockito` for collaborators and `bloc_test` for blocs.
- **Preserve existing docstrings and comments** unrelated to your change.

## Common pitfalls

- Production logic committed first with tests back-filled — violates the strict Red-Green-Refactor mandate; a test that never failed does not verify the requirement.
- `package:flutter` imported into the domain layer — breaks the framework-free domain rule and couples business logic to the UI toolkit.
- Raw exceptions thrown across layer boundaries instead of returning `Either<Failure, T>` (fpdart) or a sealed `Result` — bypasses the design-contract rule and forces callers into blind try/catch.
- Business logic (fetching, mapping, branching) inside widget code — violates the widgets-stay-dumb rule; the logic becomes untestable without pumping widgets.
- A test touching a real network, file system, platform channel, or clock — violates the mock-everything-external rule and makes the suite nondeterministic.
- Docstrings or comments unrelated to the change deleted or reworded — explicitly forbidden by this skill's preservation rule.
- Commits landed off `feature/*`/`bugfix/*` or without Conventional Commit messages — outside the branch and commit discipline this scope mandates.

## Definition of done

- [ ] Every new use case, bloc/notifier, repository, and non-trivial widget in the change has a test that failed before the implementation landed.
- [ ] `domain/` compiles without `package:flutter`, and dependencies point inward: presentation and data depend on domain, never the reverse.
- [ ] Boundary calls return `Either<Failure, T>` or a sealed `Result`; no raw `throw` crosses a layer in the diff.
- [ ] Widgets added or touched by the change contain rendering and dispatch only; new logic lives in domain/application classes with their own tests.
- [ ] No test in the change reaches a real network, file system, platform channel, or `DateTime.now()`; collaborators are `mocktail`/`mockito` mocks and blocs are tested with `bloc_test`.
- [ ] Docstrings and comments unrelated to the change are byte-identical to before.
- [ ] The branch is `feature/*` or `bugfix/*` and every commit message parses as a Conventional Commit.
