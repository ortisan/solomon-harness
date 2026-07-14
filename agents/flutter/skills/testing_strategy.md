---
name: testing-strategy
description: Governs the Flutter test pyramid, covering unit tests on domain and application code with mocktail, widget tests with deliberate pumping, a scoped golden-test net, and on-device integration tests via integration_test or patrol. Use when writing tests for a Flutter change, choosing between pump and pumpAndSettle, or deciding what belongs in a golden or integration test.
---

# Testing Strategy

This skill governs the Flutter test pyramid: unit tests on domain and application code, widget tests on presentation, golden tests as a scoped visual-regression net, and a thin layer of on-device integration tests. The stance: many fast unit tests, fewer widget tests, fewest integration tests; everything external is mocked below integration level; a test that depends on real time, real network, or `pumpAndSettle` luck is a broken test.

## Unit tests: domain and application

Cover every use case, repository implementation (against mocked data sources), mapper, and notifier/bloc. Target >= 85% line coverage on `domain/` and `application/`; presentation coverage is earned through widget and golden tests, not chased with trivial build-method tests. Domain tests run under plain `dart test` with no Flutter binding — needing `TestWidgetsFlutterBinding` in a domain test means the layer leaked. Inject a fake clock (`package:clock`'s `withClock`, or a constructor-injected `now()`) and seeded data; never `DateTime.now()` or real timers in assertions. For Riverpod, unit-test notifiers through a `ProviderContainer` with repository overrides and assert the emitted `AsyncValue` sequence; for Bloc, `bloc_test` asserts the exact state sequence per event, including the error path.

## Mocking with mocktail

Use `mocktail` (1.x) as the standard mocking library — no codegen, null-safe by design:

```dart
class MockPortfolioRepository extends Mock implements PortfolioRepository {}

setUpAll(() => registerFallbackValue(FakeAccountId()));

test('maps repository failure to error state', () async {
  final repo = MockPortfolioRepository();
  when(() => repo.fetch(accountId: any(named: 'accountId')))
      .thenAnswer((_) async => const Result.err(PortfolioNetwork()));
  // ... assert the notifier emits AsyncError / the error view state
  verify(() => repo.fetch(accountId: 'acc-1')).called(1);
});
```

Rules: `registerFallbackValue` in `setUpAll` for any custom type used with `any()`; stub with `thenAnswer` for futures/streams; `verify` interactions only when the interaction is the contract (commands), not for queries whose result already proves the behavior. Mock at the boundary you own — repositories and data sources — not three layers deep. Platform channels are faked via `TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger.setMockMethodCallHandler`; HTTP via an injected mocked `Dio`/`http.Client`, never by hitting the network.

## Widget tests and the pumpAndSettle traps

`testWidgets` pumps the widget under a minimal harness — `MaterialApp` (or the real router config when testing navigation) plus `ProviderScope`/`BlocProvider` overrides injecting mocks. Drive with `tester.tap`/`enterText`/`drag`, assert with `find`.

Pumping is where widget tests rot, so be exact about it:

- `pumpAndSettle` repeatedly pumps until no frames are scheduled. Against an infinite animation (`CircularProgressIndicator`, shimmer, `repeat()` controllers) it never settles and times out after the default 10 minutes of fake time — the test hangs, then fails with a misleading timeout. Testing a loading state therefore uses `pump(const Duration(milliseconds: 100))`, never `pumpAndSettle`.
- `pumpAndSettle` advances fake time in 100 ms steps; it does not wait for real async I/O. A pending future that completes off the fake-time clock still needs an explicit `await tester.pump()` after completion, or `tester.runAsync` for genuinely real async (rare; slow — quarantine it).
- Prefer deliberate pumps: one `pump()` to start the frame after `setState`, `pump(duration)` to advance a known animation, `pumpAndSettle` only for finite, self-terminating transitions such as a route push.
- Timers left running at test end fail the test ("A Timer is still pending"); cancel debouncers in `dispose` and flush them by advancing fake time.

## Golden tests policy

Goldens are a scoped net, not a screenshot-everything reflex — they are brittle to intentional design change and each update is a review event. Policy: goldens cover the design-system components (buttons, cards, form fields in all states) and a handful of critical screens, at compact and expanded sizes, light and dark, and 200% text scale. Use `alchemist` (or `golden_toolkit`) so real fonts load and device configurations are declarative; the default Ahem-font goldens hide text-overflow regressions. Pin golden generation to one platform (CI's Linux runners) because antialiasing differs across OSes; regenerate with `flutter test --update-goldens` only on an intentional visual change, and review the image diff in the PR — a blind regeneration converts the net into noise.

## Integration tests on device

`integration_test` covers the few critical end-to-end journeys — auth, the primary money path (checkout/order), core navigation — on a real device or emulator via `flutter test integration_test` (or `flutter drive` for timeline capture). Use `patrol` (3.x) when the journey crosses into native UI that `integration_test` cannot touch: permission dialogs, notifications, system settings — `$.native.grantPermissionWhenInUse()` instead of flaky taps at coordinates. Point the app at a hermetic backend (local fake server or staging with seeded fixtures); assertions against live production data are flake generators. Keep this layer small (single digits of scenarios), stable, and run on every PR if runtime allows, otherwise on merge to main plus nightly.

## Common pitfalls

- `pumpAndSettle` over an infinite animation; the test times out and gets "fixed" by deleting the assertion.
- Sleeping (`await Future.delayed`) in tests instead of pumping fake time; slow and still racy.
- `DateTime.now()` in code under test with no injected clock; assertions drift and fail at midnight or month ends.
- Mockito-with-codegen habits in a mocktail project: missing `registerFallbackValue` for custom matchers, `verify` on every query.
- Goldens regenerated wholesale to make CI green, burying a real regression in a 40-image diff.
- Goldens rendered with the Ahem placeholder font, hiding overflow and line-break regressions.
- Widget tests that re-test business logic through the UI instead of asserting rendering and dispatch; slow suites that duplicate unit coverage.
- Integration tests against live backends or with real network in "unit" tests; red suites on every backend hiccup.
- Coverage theater: 85% overall while `domain/` mappers and error paths sit untested.

## Definition of done

- [ ] Every use case, repository implementation, mapper, and notifier/bloc has unit tests including the error path; `domain/` + `application/` line coverage >= 85%.
- [ ] Domain tests run under plain `dart test`; time is injected via a fake clock; no real timers, network, or `DateTime.now()` in assertions.
- [ ] Mocks are mocktail at owned boundaries; fallback values registered; interaction `verify` used only for command contracts.
- [ ] Widget tests inject mocks via `ProviderScope`/`BlocProvider` overrides and use deliberate pumps; no `pumpAndSettle` on infinite animations; no pending-timer failures.
- [ ] Goldens cover design-system components and critical screens across size, theme, and 200% text scale, with real fonts, generated on the pinned CI platform; regenerations are reviewed image diffs.
- [ ] The critical journeys run as `integration_test`/`patrol` on a device against a hermetic backend, green on the agreed cadence.
- [ ] The whole pyramid runs in CI; a failing layer blocks merge.
