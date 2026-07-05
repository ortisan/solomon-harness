# Flutter Common Pitfalls

The recurring Flutter defects a reviewer rejects on sight, from lifecycle misuse to leaked controllers and logic in widgets. Each bullet names a concrete failure mode drawn from the state-management, testing, and rendering skills; the closing checklist is the gate proving a change ships with none of them.

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

- [ ] No `setState` or `emit` runs after dispose/`close()`: async continuations in widgets, notifiers, and blocs are guarded by `mounted`/`isClosed`, exercised by a fast-navigation widget test.
- [ ] No `BuildContext` crosses an `await` without a `mounted` check; `use_build_context_synchronously` reports clean under `flutter analyze`.
- [ ] Every controller, `FocusNode`, `StreamSubscription`, and `Timer` introduced by the change is disposed or cancelled in `dispose()`.
- [ ] Loading states are tested with deliberate `pump(duration)`; no `pumpAndSettle` sits over an infinite animation such as `CircularProgressIndicator`.
- [ ] Rebuild scope is narrowed with `select`/`BlocSelector`/`buildWhen`; DevTools widget-build tracking shows no page-wide rebuild from a field-level change.
- [ ] Unbounded or large lists use `ListView.builder`; no `shrinkWrap: true` on a large list appears in the diff.
- [ ] Widget files contain rendering and dispatch only; HTTP and JSON stay in the data layer, business rules in domain/application.
- [ ] State and entity equality comes from `freezed`/`Equatable`, sizes and strings come from the theme and l10n, and the changed screens render correctly at 200% text scale inside `SafeArea`.
