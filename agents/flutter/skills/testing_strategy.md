## Testing strategy


Follow the test pyramid: many unit tests, fewer widget tests, fewest integration tests.

- **Unit (`flutter_test`/`test`)**: cover every use case, repository implementation (with mocked data sources), and mapper. Target **>=85% line coverage on `domain/` and `application/`**.
- **Bloc/notifier**: `bloc_test` asserting the precise state sequence for each event, including error paths. Inject a fake clock and seeded data; never real time.
- **Widget (`testWidgets`)**: `pumpWidget` the widget under a minimal `MaterialApp`, drive with `tester.tap`/`enterText`/`drag`, and assert with `find`. Use `pump(duration)` to advance animations deliberately; reserve `pumpAndSettle` for finite animations (it hangs on infinite ones). Inject mocked blocs/providers via `BlocProvider`/`ProviderScope` overrides.
- **Golden tests** for visual regression on key components and screens (`matchesGoldenFile`, or `alchemist`/`golden_toolkit` for multi-device/font-loaded goldens). Regenerate goldens intentionally, never blindly.
- **Integration (`integration_test`)**: cover critical end-to-end flows (auth, checkout, primary navigation) on a device/emulator; use `patrol` when you need native permission dialogs or system UI. Keep these few and stable.
- **Mock everything external**: HTTP (`http`/`dio` clients), platform channels (`TestDefaultBinaryMessengerBinding`), secure storage, and time. A test that fails because the network is down is a broken test.
