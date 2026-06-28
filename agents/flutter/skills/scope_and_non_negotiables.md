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
