## Common pitfalls to avoid


- `useEffect` used to sync derived state, causing extra renders and stale values. Compute in render instead.
- Array index as list key, producing wrong reconciliation on reorder.
- Stale closures in effects/callbacks from missing or suppressed dependencies.
- Manual RxJS `subscribe` without teardown (memory leak); method calls in Angular templates (runs every change detection).
- Putting fast-changing or large data in Context, re-rendering the whole subtree.
- Treating server data as client state and reinventing caching/invalidation in effects.
- Hardcoded colors/spacing instead of tokens, breaking theming and consistency.
- `div`/`span` with click handlers instead of `<button>`, losing keyboard and semantics.
- Shipping unsanitized HTML via `dangerouslySetInnerHTML`/`[innerHTML]` (XSS).
- Memoizing everything by hand, adding complexity with no measured gain (and fighting the React Compiler).
