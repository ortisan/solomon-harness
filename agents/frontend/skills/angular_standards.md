## Angular standards


- Standalone components by default (the default since Angular 19; do not add `standalone: true`, and avoid NgModules for new features).
- Signals for component state and derived values (`signal`, `computed`, `effect`, `linkedSignal` for state that resets from a source). Use the new control flow (`@if`, `@for`, `@switch`) with `track` on every `@for`.
- `ChangeDetectionStrategy.OnPush` on every component. Drive views with the `async` pipe or signals rather than manual `subscribe`. Zoneless change detection is available in recent versions and removes the Zone.js dependency; if you adopt it, keep the same OnPush/signal discipline so views still update predictably.
- RxJS hygiene: never leak subscriptions. Use the `async` pipe, `takeUntilDestroyed()`, or `toSignal()`. Manual `subscribe` without teardown is a defect.
- For remote data, prefer `toSignal()` or the `resource()`/`httpResource()` reactive APIs (Angular 19+, still stabilizing) over hand-managed subscriptions and effects.
- Use `inject()` over constructor injection for cleaner, tree-shakable code. Use typed reactive forms (`FormGroup<...>`); avoid template-driven forms for non-trivial input. Prefer the signal-based `input()`/`output()`/`model()` over decorators in new components.
- Lazy-load routes and use `@defer` blocks for below-the-fold or heavy components.
- Keep templates thin: no complex expressions or method calls in bindings (they run every change detection); precompute in `computed` signals or component fields.
