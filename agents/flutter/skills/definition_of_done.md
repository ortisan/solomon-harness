---
name: definition-of-done
description: Defines the completion gate for a Flutter change covering TDD evidence, layering, state-management discipline, disposal, performance, responsiveness, coverage, analyzer and format checks, secrets, and branch and commit conventions. Use when deciding whether a Flutter feature or fix is actually ready to ship.
---

# Flutter Definition of Done

The completion gate for every Flutter change: what must hold before work is called done. The pitfalls below name the ways a change gets marked done while failing this checklist; check against them before ticking any box.

## Common pitfalls

- Tests written after the implementation and shaped to pass — the Red step never happened, so the suite cannot fail on the requirement; the TDD box is unearned without an error-path test that predates the code.
- "Layering respected" ticked while `domain/` imports `package:flutter` or a repository throws across the boundary instead of returning `Either`/`Result` — the checkbox is about dependency direction and contracts, not folder names.
- Coverage quoted as one overall number — the bar is >= 85% on domain plus application specifically; widget-heavy presentation code inflates the total while mappers and error paths sit untested.
- Dispose and `mounted` guards checked off by reading the diff — without a fast-navigation widget test, emit-after-close and context-across-await bugs only surface under real route churn.
- The frame-budget item ticked because `const` and `.builder` appear in the diff — the checklist requires profiling on a real device for performance-sensitive work; constructors alone prove nothing.
- Accessibility and l10n marked done with hardcoded English strings still present and no 200% text-scale pump in any widget test — both are explicit gates in this checklist, not aspirations.
- `flutter analyze` green via new `// ignore:` lines or a relaxed ruleset — the strict-analyzer gate is met when the code satisfies the rule, not when the rule is silenced.

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
