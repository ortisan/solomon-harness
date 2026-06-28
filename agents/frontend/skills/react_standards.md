## React standards


- Function components and hooks only. No class components in new code.
- Follow the Rules of Hooks: call hooks at the top level, never inside conditions, loops, or callbacks. Enforce with `eslint-plugin-react-hooks` and keep `exhaustive-deps` on; do not silence it without a written reason.
- Do not use `useEffect` for derived state or for transforming props into state. Compute during render or with `useMemo`. Reserve effects for synchronizing with external systems (subscriptions, DOM, network).
- Memoize by measurement, not by default. Add `useMemo`/`useCallback`/`memo` only when the React Profiler shows a real cost or a referential-equality requirement (dependency of another hook, `memo` child). If the project adopts the React Compiler (1.0, stable), it auto-memoizes correct components and most hand-written `useMemo`/`useCallback` becomes unnecessary; keep components compiler-safe (pure render, no mutation of props/state) and still profile before adding any by hand.
- React 19 APIs where they fit: `use` to read promises/context, form actions with `useActionState` and `useFormStatus` for submission state, `useOptimistic` for optimistic UI, and `ref` passed as a normal prop (no `forwardRef` boilerplate in new code).
- Stable, meaningful `key` props in lists. Never use the array index as key when items can reorder, insert, or delete.
- Lift state only as far as needed. Prefer composition and `children` to avoid prop drilling before reaching for Context.
- Concurrent features: use `useTransition` for non-urgent updates (filtering large lists), `Suspense` for async boundaries, and `useDeferredValue` for expensive derived views.
- If on Next.js App Router, default to Server Components; mark `'use client'` only where interactivity or browser APIs are required. Keep client bundles small.
- Side-effect cleanup: every subscription, listener, timer, and `AbortController` created in an effect is torn down in its cleanup return.
