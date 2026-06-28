## State management


Decision order, smallest scope first:

1. Local component state (`useState`/signal) for state used by one component.
2. Lifted/shared state via props/inputs or `children` composition.
3. Context (React) or a shared service with signals (Angular) for low-frequency, app-wide values: theme, locale, current user. Do not put high-frequency or large data in Context; it re-renders all consumers.
4. Server cache library for remote data: TanStack Query or RTK Query (React), or a signal store fed by typed services (Angular). Treat server data as a cache, not as client state. You get caching, dedup, retries, and invalidation for free instead of hand-rolling them in effects.
5. Dedicated client store (Redux Toolkit or Zustand for React; NgRx SignalStore or a service for Angular) only for genuinely global, cross-cutting client state.

Separate server state from client/UI state. Most "global state" pain is actually un-cached server state living in the wrong place.
