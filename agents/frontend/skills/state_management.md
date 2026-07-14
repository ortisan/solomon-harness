---
name: state-management
description: Governs where state lives in React and Angular apps, treating server state as a cache and client state as local-first, promoted only under pressure, with the URL treated as state too. Use when choosing a state container, deciding if data needs a global store, or reviewing state-management choices.
---

# State Management

This skill governs where state lives in React and Angular applications. The stance: server state and client state are different problems with different tools; server data belongs in a query cache, client state starts local and is promoted only under pressure, and the URL is state too. Most "we need a global store" pain is un-cached server data living in the wrong layer.

## Server state is a cache, not state

Data that lives on the server (issues, users, metrics) is a remote cache the UI reads. It has concerns component state never has: staleness, deduplication, retries, invalidation, and background refresh. Hand-rolling those in `useEffect` plus `useState` is the single most common frontend defect factory.

- React: TanStack Query v5 is the default. RTK Query is acceptable when Redux Toolkit is already entrenched.
- Angular: `httpResource()`/`resource()` for reads, or TanStack Query's Angular adapter when you need mutations, invalidation, and optimistic updates as a system.
- Next.js App Router: Server Components fetch initial data; TanStack Query takes over on the client for anything the user's interactions must refresh. Pass server data in as `initialData` rather than fetching twice.

```tsx
const issuesQuery = useQuery({
  queryKey: ['issues', { milestone }],   // key encodes every input
  queryFn: () => fetchIssues(milestone),
  staleTime: 30_000,                      // default is 0: set deliberately
});
```

Rules: the `queryKey` includes every variable the fetch depends on; set `staleTime` consciously (0 means refetch-on-focus everywhere); mutate via `useMutation` and reconcile with `invalidateQueries` (or `setQueryData` for optimistic updates) instead of manual refetch bookkeeping. Never copy query results into `useState` — render from the cache, or you now own two sources of truth and their disagreements.

## The client-state ladder

Promote state one rung at a time, with a reason at each step:

1. `useState` / `signal()` in the component that uses it. The default; most state never leaves this rung.
2. `useReducer` when several fields change together under invariants (multi-step forms, undo). The reducer is a pure function you can unit-test without rendering.
3. Lift to the nearest common parent and pass down, or restructure with `children` composition so intermediate layers never see the props at all.
4. Context (React) or an injectable signal-holding service (Angular) for low-frequency, app-wide values: theme, locale, session identity. Context re-renders every consumer on change, so keep values coarse and stable, split contexts by concern, and memoize the provider value. Fast-changing data (cursor position, live ticks) does not belong here.
5. External store — Zustand for React (selector-based subscriptions, ~1 KB, no provider), NgRx SignalStore for Angular — only for genuinely global, cross-cutting client state that many distant components write: multi-panel editor state, an undo stack, cart contents. Reaching this rung requires a sentence of justification in the PR.

Global-store-by-default is the anti-pattern this ladder exists to prevent. A store holding server responses is rung 5 doing rung 0's job badly: you inherit invalidation, staleness, and refetch logic that TanStack Query already solved.

## URL as state

Anything the user should be able to share, bookmark, refresh, or restore with the back button belongs in the URL, not in memory: filters, pagination, sort order, active tab, selected entity.

- React: `useSearchParams` (React Router) or `nuqs` in Next.js for typed, serialized search params. Angular: query params via the Router, read as signals with `toSignal(route.queryParamMap)`.
- The URL is the single source of truth for that state. Do not mirror it into `useState` "for convenience"; derive from the params and navigate to update. Mirroring creates the classic back-button-desync bug.
- Keep it flat and human-readable (`?milestone=10&status=open`), not a base64 blob, so links are debuggable and analytics can segment on them.

## Derived and form state

- Derived values are computed, never stored: `computed()` in Angular, plain expressions or `useMemo` in React. Storing a derivation means two writes per change and an eventual mismatch.
- Form state stays inside the form abstraction (React Hook Form, typed reactive forms, or React 19 actions with `useActionState`) until submit; it does not stream keystrokes into a global store.

## Common pitfalls

- Server data in `useState`/Redux/Zustand with hand-rolled fetching in effects: no dedup, no invalidation, stale screens after mutations.
- Copying a query result into local state to edit it, then rendering the copy while the cache refreshes underneath.
- `queryKey` missing an input variable, so two different filters share one cache entry.
- Context holding fast-changing values, re-rendering the entire subtree per tick.
- Filters and pagination in memory only: refresh or a shared link loses the user's view.
- Both URL and a store claiming the same state, drifting after back navigation.
- Rung-5 store adopted on day one "because we will need it", then accreting every kind of state.

## Definition of done

- [ ] Every piece of state classified: server cache, local, lifted, context, store, or URL, and placed on the lowest sufficient rung.
- [ ] Server data flows through TanStack Query / RTK Query / `httpResource` with explicit `queryKey` inputs and a deliberate `staleTime`; no fetch-in-effect.
- [ ] Mutations reconcile the cache via invalidation or optimistic update, with the failure rollback path tested.
- [ ] No server response is copied into component or store state; the cache is the single source of truth.
- [ ] Shareable view state (filters, pagination, tabs, selection) lives in the URL and survives refresh and back/forward.
- [ ] Context values are coarse, stable, memoized, and split by concern.
- [ ] Any external store addition carries a written justification and holds only client-owned state.
- [ ] Tests cover loading, error, empty, and stale-refresh states with the network mocked (MSW), plus reducer/selector unit tests where those rungs are used.
