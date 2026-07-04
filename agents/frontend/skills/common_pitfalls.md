# Frontend Common Pitfalls

The React and Angular defects that recur in review, from index keys and stale closures to leaked subscriptions and unsanitized HTML. Each bullet is a rejection on sight, grounded in this agent's standards for hooks, RxJS teardown, design tokens, and server state; the closing checklist verifies a diff carries none of them.

## Common pitfalls

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

## Definition of done

- [ ] Every list rendered in the diff keys on a stable domain id (`key={row.id}`, `track row.id`); no array-index keys on lists that can reorder, insert, or delete.
- [ ] No `useEffect` derives state computable in render; every effect lists its full dependencies, returns a cleanup, and any `exhaustive-deps` suppression carries a written reason.
- [ ] Every RxJS `subscribe` in the diff has teardown via `takeUntilDestroyed()` or the `async` pipe; Angular templates contain no method calls in bindings.
- [ ] Context holds only small, slow-changing values; server data goes through the query/cache layer (TanStack Query or equivalent), not hand-rolled caching in effects.
- [ ] All colors and spacing resolve to semantic design tokens; no raw hex, rgb, or magic pixel values appear in the diff.
- [ ] Interactive elements are `<button>` or `<a>` (or carry the full role, tabindex, and key handling); no bare `div`/`span` click handlers.
- [ ] Any HTML reaching `dangerouslySetInnerHTML`/`[innerHTML]` passes through DOMPurify or `DomSanitizer` first.
- [ ] Manual `useMemo`/`useCallback`/`memo` additions come with a Profiler measurement; otherwise renders stay pure and the React Compiler owns memoization.
