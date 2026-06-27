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

## Clean architecture layout

Organize by feature, then by layer. Enforce the dependency rule: dependencies point inward, domain is the center and knows nothing about Flutter, HTTP, or persistence.

```
lib/
  core/            # shared: errors, typedefs, di, theme, router, l10n
  features/<name>/
    domain/        # entities, repository interfaces, use cases (pure Dart)
    application/   # blocs/cubits/notifiers, view state models
    data/          # models (DTO with from/toJson), data sources, repo impls
    presentation/  # widgets, pages, layout
```

- **Entities** are immutable, framework-free, and hold business rules. **Models/DTOs** live in `data/` and convert to/from entities; never leak `Map<String, dynamic>` past the data layer.
- **Use cases** are single-purpose (`callable` classes, `call()` method). One use case per business action.
- **Dependency injection** with `get_it` + `injectable`, or Riverpod providers. Wire concretes only at the composition root. No `new HttpClient()` inside widgets or blocs.
- **Immutability** via `freezed` for entities, DTOs, events, and states. Use `Equatable` only where you avoid codegen. Hand-written `==`/`hashCode` is a smell.
- **Error handling**: data sources throw narrow exceptions; repositories catch and map to `Failure` subtypes; UI renders failures. Set a global `FlutterError.onError` and `PlatformDispatcher.instance.onError`, and wrap `runApp` in `runZonedGuarded` for crash reporting.

## State management

Pick one primary approach per app and stay consistent. Bloc/Cubit, Riverpod, or Provider are all acceptable per the role; below are the rules that keep each correct.

- **Bloc/Cubit (`flutter_bloc`)**: events and states immutable (freezed). Use `Cubit` for simple imperative state, `Bloc` for event-driven flows with traceable transitions. Emit only inside event handlers; never emit after `close()`. Guard async with `emit.isDone`/`isClosed`. Persist with `hydrated_bloc` when needed. Test with `bloc_test` asserting the exact emitted sequence.
- **Riverpod (2.x/3.x)**: prefer code generation (`@riverpod`). Model async state as `AsyncValue` and render its `loading`/`error`/`data` branches explicitly. Use `ref.watch` to react, `ref.read` for one-off actions in callbacks, `ref.listen` for side effects. Code-gen providers auto-dispose by default; reach for `keepAlive` only deliberately, and use a `family`/provider parameters for parameterized providers. Never call `ref.read`/`watch` outside `build` or provider bodies.
- **Provider**: expose immutable models, rebuild selectively with `Selector`/`context.select`, and dispose `ChangeNotifier`s.
- **Rebuild discipline (all approaches)**: subscribe to the narrowest slice. Use `BlocSelector`, `context.select`, or `select` providers so a widget rebuilds only when its data changes. `setState` is acceptable only for local, ephemeral widget state (e.g. a toggle, a controller); promote anything shared into the application layer.

## Widgets, rendering, and performance

Frame budget: **16ms at 60fps, 8ms at 120fps**. Jank means a frame exceeded budget on the UI or raster thread. Profile with DevTools (performance overlay, timeline), always in `--profile` mode on a real device, never in debug.

- Impeller is the default renderer on iOS and Android. Profile shader and animation jank against Impeller, not the legacy Skia path, since first-run shader compilation stalls no longer apply.
- Mark every widget that can be `const` as `const`. Const widgets skip rebuild and reuse element subtrees. Enable `prefer_const_constructors` lint.
- Split large `build` methods into small widgets instead of helper methods that return `Widget`; small widgets rebuild independently and benefit from const.
- Long or infinite lists use `ListView.builder`/`GridView.builder`/`Sliver*`. Never `ListView(children: list.map(...))` for unbounded data. Set `itemExtent`/`prototypeItem` when item height is fixed. Avoid `shrinkWrap: true` on large lists.
- Stable identity in dynamic lists with `ValueKey`/`ObjectKey` so Flutter reuses elements instead of rebuilding.
- Isolate expensive paints behind `RepaintBoundary`. Avoid wrapping large subtrees in `Opacity` (prefer `AnimatedOpacity`/`FadeTransition`) and avoid `saveLayer` (clips, blend modes) on the hot path.
- Move CPU-heavy work (JSON of large payloads, parsing, crypto) off the UI thread with `compute()` or `Isolate.run`.
- Images: use `cached_network_image`, set `cacheWidth`/`cacheHeight` to decode at display size, and `precacheImage` for above-the-fold assets.
- Always dispose `AnimationController`, `TextEditingController`, `ScrollController`, `FocusNode`, and `StreamSubscription` in `dispose()`. Leaks here cause "setState after dispose" crashes.
- Across async gaps, check `if (!mounted) return;` before using `BuildContext`. Enable `use_build_context_synchronously` lint.

## Navigation

- Use `go_router` for declarative routing, deep links, and web URL support. Define routes centrally; prefer type-safe routes (typed `GoRoute`/codegen) over raw string paths.
- Keep navigation logic out of widgets where possible; trigger it from the application layer's resolved state (e.g. redirect on auth state).

## Responsive and adaptive UI

- Drive layout from `LayoutBuilder` and `MediaQuery` (size, `textScaler`, `padding`, `viewInsets`), not hardcoded pixel constants. Define breakpoints (for example compact <600, medium 600–840, expanded >840 logical px) and branch layout on them.
- Use `Flexible`/`Expanded`/`Wrap`/`FittedBox` and `AspectRatio` to scale; reserve `flutter_screenutil` for tightly speced designs. Wrap screens in `SafeArea`.
- Honor `MediaQuery.textScaler`; never lock text scale. Layout must survive 200% font scaling without overflow.
- Tap targets at least **48x48 dp (Material)** / **44x44 pt (iOS)**. Provide `Semantics` labels for icon-only controls; verify contrast and screen-reader order.
- Adapt platform conventions with `Theme.of(context).platform` or `.adaptive` constructors (switches, dialogs, scroll physics) when targeting both iOS and Android.
- No hardcoded user-facing strings. Use `flutter_localizations` + `intl` with ARB files; reference `AppLocalizations`.

## Testing strategy

Follow the test pyramid: many unit tests, fewer widget tests, fewest integration tests.

- **Unit (`flutter_test`/`test`)**: cover every use case, repository implementation (with mocked data sources), and mapper. Target **>=85% line coverage on `domain/` and `application/`**.
- **Bloc/notifier**: `bloc_test` asserting the precise state sequence for each event, including error paths. Inject a fake clock and seeded data; never real time.
- **Widget (`testWidgets`)**: `pumpWidget` the widget under a minimal `MaterialApp`, drive with `tester.tap`/`enterText`/`drag`, and assert with `find`. Use `pump(duration)` to advance animations deliberately; reserve `pumpAndSettle` for finite animations (it hangs on infinite ones). Inject mocked blocs/providers via `BlocProvider`/`ProviderScope` overrides.
- **Golden tests** for visual regression on key components and screens (`matchesGoldenFile`, or `alchemist`/`golden_toolkit` for multi-device/font-loaded goldens). Regenerate goldens intentionally, never blindly.
- **Integration (`integration_test`)**: cover critical end-to-end flows (auth, checkout, primary navigation) on a device/emulator; use `patrol` when you need native permission dialogs or system UI. Keep these few and stable.
- **Mock everything external**: HTTP (`http`/`dio` clients), platform channels (`TestDefaultBinaryMessengerBinding`), secure storage, and time. A test that fails because the network is down is a broken test.

## Tooling and CI gates

- `flutter analyze` clean with a strict ruleset (`flutter_lints` minimum, `very_good_analysis` preferred). Treat warnings as errors in CI.
- `dart format --set-exit-if-changed .` enforced.
- Sound null safety throughout; avoid the `!` bang operator. Use `?.`, `??`, pattern matching, and exhaustive `switch` on sealed types.
- CI must run: `dart format` check, `flutter analyze`, `flutter test --coverage`, and a coverage threshold check. Block merge on any failure.

## Mobile security (STRIDE-relevant)

Flutter ships installable binaries, so threat-model the client: **Spoofing** (enforce auth tokens, certificate pinning), **Tampering** (build with `--obfuscate --split-debug-info`, validate all platform-channel input), **Repudiation** (audit-log sensitive actions server-side), **Information disclosure** (store secrets in `flutter_secure_storage`/Keychain/Keystore, never in source, prefs, or logs; redact PII from crash reports), **Denial of service** (timeouts and backoff on network calls), **Elevation of privilege** (least-privilege platform permissions, never trust client-side gating alone). No API keys or credentials committed to the repo.

## Common pitfalls

- Calling `setState`/emitting after dispose or `close()`. Guard with `mounted`/`isClosed`.
- Using `BuildContext` after an `await` without a `mounted` check.
- Forgetting to dispose controllers and subscriptions (memory leaks, ghost callbacks).
- `pumpAndSettle` on an infinite animation (test timeout).
- Rebuilding whole pages because a top-level `Bloc`/provider was watched broadly; select narrow slices instead.
- `ListView` over unbounded data instead of `.builder`; `shrinkWrap: true` on large lists.
- Business logic inside widgets; HTTP/JSON leaking out of the data layer.
- Hardcoded sizes and strings; ignoring text scale and `SafeArea`.
- Hand-rolled `==`/`hashCode` causing stale UI; use `freezed`/`Equatable`.

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
