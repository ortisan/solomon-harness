---
name: tooling-and-ci-gates
description: Governs Flutter toolchain discipline, covering very_good_analysis lint policy, mechanical dart format enforcement, reproducible code generation in CI, build flavor and scheme setup, and the fail-fast CI pipeline with caching. Use when configuring analysis_options.yaml, setting up a CI pipeline, adding a build flavor, or reviewing whether generated code is reproducible.
---

# Tooling and CI Gates

This skill governs the Flutter toolchain discipline: static analysis and lint policy, formatting, code generation in CI, flavor/scheme setup, and the CI pipeline with its caching strategy. The stance: the pipeline is the quality gate — analyzer clean at the strictest ruleset, format enforced mechanically, generated code reproducible, and every merge blocked on the full ladder. A rule that only lives in review comments does not exist.

## Analyzer and lint policy

Adopt `very_good_analysis` (6.x or later) as the base ruleset — it is a strict superset of `flutter_lints` — and layer language strict modes on top in `analysis_options.yaml`:

```yaml
include: package:very_good_analysis/analysis_options.yaml
analyzer:
  language:
    strict-casts: true
    strict-inference: true
    strict-raw-types: true
  errors:
    unused_import: error
  exclude:
    - "**/*.g.dart"
    - "**/*.freezed.dart"
```

Run `flutter analyze --fatal-infos` in CI so infos and warnings fail the build; a warning tolerated for one sprint becomes two hundred. Every `// ignore:` requires a same-line reason and is grep-audited in review — an ignore without a reason is a reject. Sound null safety discipline belongs here too: avoid the `!` bang operator in favor of `?.`, `??`, pattern matching, and exhaustive `switch` on sealed types; `avoid_dynamic_calls` stays enabled. Project-specific rules the analyzer cannot express (import direction between layers, banned packages in `domain/`) run as `custom_lint` plugins — the same mechanism `riverpod_lint` and `bloc_lint` use, so wire those in when the corresponding framework is present.

## Formatting

`dart format --set-exit-if-changed .` is a CI gate, not advice. Dart's formatter is not configurable beyond page width, which is the point — zero style debate. On Dart 3.7+ the formatter applies the new tall style and reads `page_width` from `analysis_options.yaml` if the project overrides the 80-column default; whatever the choice, the repo pins one formatter version via the Flutter SDK pin so CI and laptops agree. Kill hand-managed trailing commas as review topics: the formatter owns them now.

## Code generation in CI

Projects using `freezed`, `json_serializable`, `riverpod_generator`, or `go_router_builder` must make generated code reproducible. Two valid policies — pick one and record it:

1. Commit generated files (default here: builds and IDEs work without a generation step). CI then verifies freshness: run `dart run build_runner build --delete-conflicting-outputs` and fail if `git diff --exit-code` shows drift — stale generated code is a real bug class, not cosmetics.
2. Do not commit them; CI and every workflow runs `build_runner` before analyze/test. Simpler diffs, slower cold starts.

Either way, pin the generator package versions in `pubspec.yaml` and commit `pubspec.lock` for apps, so two machines cannot generate different output from the same source.

## Flavors and schemes

Separate development/staging/production as build flavors (Android `productFlavors` with `applicationIdSuffix`, iOS schemes + `.xcconfig` per flavor), each with its own entrypoint (`main_development.dart`, `main_production.dart`) wiring the flavor's config at the composition root. Non-secret environment values travel via `--dart-define-from-file=env/dev.json`, never hardcoded per file; secrets do not travel in Dart code at all (see the mobile security skill). Flavored apps install side by side thanks to distinct application ids, which QA needs daily. CI builds at minimum the development flavor per PR and the production flavor on release branches, with `flutter build apk --flavor production -t lib/main_production.dart` style invocations scripted, not typed from memory.

## CI pipeline and caching

The PR gate, in order (fail fast): format check -> codegen freshness -> `flutter analyze --fatal-infos` -> `flutter test --coverage` + coverage threshold (enforce the >= 85% domain/application bar from the testing skill via `lcov` filtering) -> debug/dev build. Integration tests on device/emulator run on merge to main or nightly if PR runtime is too long.

On GitHub Actions, `subosito/flutter-action@v2` with `cache: true` caches the Flutter SDK; add `actions/cache` for `~/.pub-cache` keyed on `pubspec.lock`, and for the Gradle caches (`~/.gradle/caches`, wrapper) keyed on the Gradle files — Android builds dominate pipeline time without it. Pin the exact Flutter version in the workflow (the same one in `pubspec.yaml`'s `environment`), never `channel: stable` floating, or a Flutter release morning breaks every PR. Codemagic covers the Apple side well (managed macOS runners, code signing via App Store Connect integration, `flutter-version` pinned in `codemagic.yaml`); its default dependency caching covers pub and CocoaPods. Whatever the CI vendor, iOS release builds need a macOS runner and both stores need the signing material injected from CI secrets, not committed keystores.

## Common pitfalls

- `flutter_lints` alone with warnings tolerated in CI; the codebase accretes hundreds of ignored diagnostics that mask new ones.
- `// ignore:` without a reason, or file-wide `ignore_for_file` used to silence a rule the code should satisfy.
- Generated `*.g.dart`/`*.freezed.dart` committed but stale because CI never re-runs `build_runner` and diffs; runtime behavior diverges from source.
- Floating `channel: stable` in CI while developers pin locally; upstream releases break PRs unrelated to their diff.
- No `pubspec.lock` committed for an app, so CI resolves different package versions than the author tested.
- Flavor config via `if (kReleaseMode)` branching instead of entrypoints + dart-define; staging URLs ship in production binaries.
- Uncached Gradle/pub in CI: 25-minute pipelines that teams then "optimize" by deleting test steps.
- Coverage collected but no threshold enforced; the number decays silently.

## Definition of done

- [ ] `analysis_options.yaml` includes `very_good_analysis` (6.x+) plus strict-casts/inference/raw-types; `flutter analyze --fatal-infos` is green in CI.
- [ ] Every `// ignore:` carries a written reason; framework lint plugins (`riverpod_lint`/`bloc_lint`, custom import rules) are wired where applicable.
- [ ] `dart format --set-exit-if-changed .` gates every PR with the formatter version pinned via the SDK pin.
- [ ] Codegen policy (committed + freshness diff, or generated in CI) is recorded and enforced; generator versions pinned; `pubspec.lock` committed.
- [ ] Flavors exist for dev/staging/prod with separate entrypoints, application ids, and `--dart-define-from-file` config; no secrets in Dart.
- [ ] CI runs format, codegen freshness, analyze, tests with the coverage threshold, and a build, in fail-fast order; merge is blocked on any failure.
- [ ] Flutter SDK version pinned identically in CI and `pubspec.yaml`; pub and Gradle caches keyed on lockfiles; iOS jobs on macOS runners with signing from CI secrets.
