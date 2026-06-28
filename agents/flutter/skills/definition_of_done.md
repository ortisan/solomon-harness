## Definition of done


- [ ] Failing test written first for each new use case, bloc/notifier, repository, and non-trivial widget; all green now.
- [ ] Layering respected: domain is framework-free; data, application, and presentation depend inward; boundaries return `Either`/`Result`.
- [ ] One state-management approach used consistently; widgets subscribe to the narrowest slice; no emit/setState after dispose.
- [ ] All controllers, focus nodes, and subscriptions disposed; `BuildContext` use across async gaps guarded by `mounted`.
- [ ] Long lists use `.builder`; expensive paints behind `RepaintBoundary`; const applied; profiled within frame budget on a real device when performance-sensitive.
- [ ] UI responsive across breakpoints and 200% text scale; tap targets meet minimums; `SafeArea` and `Semantics` in place; no hardcoded strings (l10n wired).
- [ ] All external services mocked in tests; bloc/widget/golden coverage present; domain+application coverage >=85%.
- [ ] `dart format`, `flutter analyze` (strict), and `flutter test --coverage` pass; no `!` bang abuse; sound null safety.
- [ ] Secrets in secure storage, release build obfuscated, no PII in logs.
- [ ] Branch is `feature/*` or `bugfix/*`; commits follow Conventional Commits; existing docstrings/comments preserved.
