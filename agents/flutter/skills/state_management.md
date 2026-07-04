# State Management

This skill governs how application state is modeled, owned, and rebuilt in Flutter. The stance: Riverpod 3.x with code generation is the project default; Bloc is the deliberate alternative when an event-sourced audit trail of state transitions earns its keep; `setState` is confined to ephemeral, widget-local state; all state objects are immutable via `freezed`. Pick one primary approach per app, record it in an ADR, and stay consistent — a codebase mixing three state solutions is a review reject.

## Riverpod 3.x as the default

Use `riverpod` 3.x with `riverpod_annotation` + `riverpod_generator` codegen. Declare providers with `@riverpod`; the generator picks the correct provider type, gives compile-safe parameters (families), and makes providers auto-dispose by default.

```dart
@riverpod
class PortfolioController extends _$PortfolioController {
  @override
  Future<Portfolio> build(String accountId) =>
      ref.watch(portfolioRepositoryProvider).fetch(accountId: accountId);

  Future<void> refresh() async {
    state = const AsyncLoading();
    state = await AsyncValue.guard(
      () => ref.read(portfolioRepositoryProvider).fetch(accountId: accountId),
    );
  }
}
```

Rules that keep Riverpod correct:

- Model every async dependency as `AsyncValue<T>` and render `loading`/`error`/`data` explicitly — with a Dart 3 `switch` expression on the sealed `AsyncValue`, or `.when`. A screen without an error branch is incomplete.
- `ref.watch` to react inside `build` and provider bodies; `ref.read` only for one-off actions in callbacks; `ref.listen` for side effects (snackbars, navigation). Never `ref.watch` inside a callback and never `ref.read` inside `build` to "avoid rebuilds" — that hides staleness.
- Auto-dispose is the default under codegen; opt out with `@Riverpod(keepAlive: true)` only for genuinely app-lifetime state (session, config) and say why. In 3.x, check `ref.mounted` after `await` before touching `state` in a notifier method.
- Wrap fallible mutations in `AsyncValue.guard` instead of try/catch that swallows the error.
- Wire the data layer in via providers (`portfolioRepositoryProvider`) and override them in `ProviderScope(overrides: [...])` for tests and flavors — that is the composition root.

## Avoiding provider soup

Riverpod's failure mode is hundreds of tiny interdependent providers with no ownership story. Constrain it structurally:

- One notifier per screen or per aggregate, exposing one view-state object — not one provider per field. Derive cheap projections with `select` rather than new providers: `ref.watch(portfolioControllerProvider(id).select((s) => s.valueOrNull?.total))`.
- Providers live in the application layer of the owning feature; widgets from another feature depend on that feature's public notifier, never on its internals.
- Keep provider graphs shallow: a provider depending on five other providers is a use case hiding in the dependency graph — write the use case.

## When Bloc fits

Choose `flutter_bloc` (8.x/9.x) when the domain benefits from event sourcing style: every input is a named event, transitions are traceable in order, and `BlocObserver` gives a global transition log (support tooling, analytics replay, strict audit requirements). Keep events and states `freezed`. Use `Cubit` when the event vocabulary would be `setX`-shaped noise. Bloc-specific correctness: emit only inside event handlers, guard long-running handlers with `emit.isDone`/`isClosed`, never emit after `close()`, control concurrency with `bloc_concurrency` transformers (`restartable`, `droppable`) instead of hand-rolled flags, persist with `hydrated_bloc` when state must survive restart, and test with `bloc_test` asserting the exact emitted sequence. Do not run Riverpod and Bloc side by side in one app without an ADR drawing the boundary.

## setState boundaries

`setState` is correct for state that is ephemeral, widget-local, and irrelevant to business logic: a hover flag, an expanded/collapsed toggle, an `AnimationController` value, text-field focus. The promotion test: if a second widget, a test, or persistence needs the value, it moves to the application layer. Never `setState` around data fetched from a repository — that state has no loading/error modeling and dies with the widget. If a `StatefulWidget` only exists to hold controllers next to Riverpod state, use `flutter_hooks` + `hooks_riverpod` or keep the small `StatefulWidget`; both are acceptable, mixing patterns randomly is not.

## Immutability with freezed

All states, events, entities, and view models are `freezed` data classes (freezed 3.x, `sealed`/`abstract` per the Dart 3 syntax). Value equality is what makes rebuild-skipping and `select` work: two states that are equal by value must not trigger a rebuild, and mutable state breaks that silently. Use `copyWith` for updates; collections inside state are unmodifiable views or replaced wholesale, never mutated in place — mutating a `List` inside a state object defeats change detection because identity does not change.

## Rebuild discipline (all approaches)

Subscribe to the narrowest slice: `select` in Riverpod, `BlocSelector`/`buildWhen` in Bloc, `context.select` with Provider. Watch the rebuild count in DevTools ("Track widget builds") when a screen feels slow; a full-screen rebuild on every keystroke is a subscription-scope bug, not a Flutter problem.

## Common pitfalls

- `ref.read` inside `build` to suppress rebuilds — the widget now renders stale data; use `select` to narrow instead.
- Touching `state` after an `await` without checking `ref.mounted` (Riverpod) or emitting after `close()` (Bloc); both throw or corrupt state under fast navigation.
- One provider per field ("provider soup") instead of one notifier exposing a cohesive view state.
- Mutable lists/maps inside state objects mutated in place; equality never changes, the UI never updates, and the bug looks like a rendering issue.
- `keepAlive: true` sprinkled as a cache-everything reflex; memory grows and logout leaks user data across sessions.
- Hand-rolled `isLoading`/`error` boolean pairs instead of `AsyncValue`; impossible states (`isLoading && hasError`) become representable.
- Business logic in widget callbacks (fetch, map, branch) instead of notifier/bloc methods; it is untestable without pumping widgets.
- Two state-management frameworks in one app without an ADR boundary.

## Definition of done

- [ ] The app's primary state approach (Riverpod 3.x default, or Bloc with rationale) is recorded in an ADR and used consistently.
- [ ] Providers are codegen (`@riverpod`); async state is `AsyncValue` with explicit loading/error/data rendering on every screen.
- [ ] `ref.watch`/`ref.read`/`ref.listen` used per their roles; no `ref.read` in `build`, no `ref.watch` in callbacks; `ref.mounted` checked after awaits in notifier methods.
- [ ] `keepAlive` opt-ins are justified in a comment; everything else auto-disposes.
- [ ] All states, events, and view models are `freezed`; no in-place mutation of collections held in state.
- [ ] `setState` appears only for ephemeral widget-local state; anything shared or fetched lives in the application layer.
- [ ] Rebuild scope verified: `select`/`BlocSelector`/`buildWhen` narrow subscriptions, confirmed with DevTools widget-build tracking on the hot screens.
- [ ] Notifier/bloc logic covered by tests asserting the exact state sequence, including the error path, with repositories mocked via `ProviderScope` overrides or injected fakes.
