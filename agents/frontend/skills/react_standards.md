---
name: react-standards
description: Governs every React component, hook, and server/client boundary in this workspace: React 19 under Next.js 16 baseline, function components, effects as a last resort, and an explicit Server/Client split recorded in the plan. Use when writing or reviewing React components, hooks, or a page's server/client boundary.
---

# React Standards

This skill governs every React component, hook, and server/client boundary shipped in this workspace. The stance: React 19 is the baseline (the `ui/` app pins `react` 19.2.4 under Next.js 16.2.9), components are functions, effects are a last resort, and the Server/Client Component split is an explicit architectural decision recorded in the plan, never an accident of where the code happened to be written.

## Server and Client Component boundaries

React 19 makes Server Components a first-class part of the model; the Next.js App Router is where this project meets them.

- Default to Server Components. A file is server-only until a `'use client'` directive appears; everything it imports transitively joins the client bundle.
- Put `'use client'` on the smallest interactive leaf (event handlers, `useState`, browser APIs), never on a page or layout. One directive on a layout drags the whole subtree into the client bundle and shows up directly in the JS budget.
- Props crossing the boundary must be serializable: plain data and IDs, no functions (Server Actions are the one exception), no class instances. Fetch on the server, pass rows down.
- Compose server into client through `children`: a client shell can render server-rendered children it receives as props, so interactivity does not pull data fetching into the client.
- A Server Action is a public HTTP endpoint. Validate input (zod or equivalent) and authorize inside the action body; the calling component proves nothing.

```tsx
// Server Component: no directive, async, fetches directly.
export default async function VelocityPage() {
  const rows = await getVelocity();
  return <VelocityChart rows={rows} />; // client leaf receives plain data
}
```

Note for this repo: `ui/AGENTS.md` warns that Next.js 16 changed conventions; read `node_modules/next/dist/docs/` before writing App Router code rather than trusting memory.

## React 19 data and form APIs

- `use(promise)` unwraps a promise during render inside a Suspense boundary, and unlike a hook it may be called conditionally. Create the promise on the server or in the query layer and pass it down; never create it inside the same render that reads it, or every render restarts the fetch.
- Actions replace hand-rolled submit state machines. `useActionState(action, initialState)` returns `[state, formAction, isPending]`; `useFormStatus()` gives a child submit button the pending flag; `useOptimistic` renders the expected result and rolls back on failure.
- `ref` is a normal prop in React 19: no `forwardRef` in new code, and ref callbacks may return a cleanup function.
- Transitions keep input responsive: wrap non-urgent updates (filtering a large table) in `useTransition`; use `useDeferredValue` for expensive derived views. This is a direct INP lever.

```tsx
const [state, submit, pending] = useActionState(saveIssue, { error: null });
return (
  <form action={submit}>
    <input name="title" required />
    <button disabled={pending}>{pending ? "Saving" : "Save"}</button>
    {state.error && <p role="alert">{state.error}</p>}
  </form>
);
```

## Component design rules

- One responsibility per component; split container (data, state) from presentation (markup, style). Roughly 200 lines or more than 5 shape-shifting props is a refactor signal.
- Prefer composition (`children`, slot props) over boolean-flag configuration props.
- Derive, do not store: anything computable from props and state is computed during render, not mirrored into `useState`.
- List keys are stable domain IDs, never the array index when items can reorder, insert, or delete.

## Hooks discipline

- Rules of Hooks enforced with `eslint-plugin-react-hooks` (v6 flat config under ESLint 9); `exhaustive-deps` stays on. Suppressing it requires a written reason in the code.
- Dependency arrays list every reactive value. Fix instability at the source: move the function into the effect, use the updater form of `setState`, or `useCallback` only when the value is a dependency elsewhere. A missing dependency is a stale-closure bug waiting for production.
- Effects synchronize with external systems only (subscriptions, DOM, analytics). Data fetching lives in Server Components or the query layer (see `state_management`), not in raw `useEffect`.
- Custom hook contract: named `use*`, typed inputs and outputs, documented stability of the returned identities, and its own test. A hook that wraps a single `useState` is noise; inline it.
- React Compiler (1.x, stable) auto-memoizes pure components. Keep renders pure, never mutate props or state, and add manual `useMemo`/`useCallback`/`memo` only with a Profiler measurement attached to the PR.

## Suspense and error boundaries

- Every suspending read (`use`, `React.lazy`, suspense-enabled queries) has an owning `<Suspense fallback>` placed where a skeleton makes visual sense, usually per layout region, not one boundary around the whole app.
- Pair each Suspense seam with an error boundary (`react-error-boundary`); a pending promise hits the fallback, a rejection hits the error boundary. Provide a reset action so users can retry without a full reload.
- Size fallbacks to the final content to avoid layout shift; this is the same reservation rule as the CLS budget.

## When the App Router matters

Choose Next.js App Router when server data dominates the screen, SEO or streaming matters, or forms can post to Server Actions. A pure client SPA (Vite + React Router) remains correct for auth-gated internal dashboards; there, TanStack Query owns all server state and this skill's client rules apply unchanged.

## Common pitfalls

- `useEffect` deriving state from props: extra renders, stale values; compute in render.
- `'use client'` on a layout or page, silently shipping the subtree to the client.
- Creating the promise passed to `use()` during render, refetching on every render.
- Silenced `exhaustive-deps` with no justification; the stale closure surfaces weeks later.
- Server Action trusting its caller: no validation or authorization inside the action.
- One app-wide Suspense boundary, so any slow query blanks the entire screen.
- Index keys on reorderable lists; `forwardRef` and class components in new code.
- Hand-memoizing everything, fighting the React Compiler for no measured gain.

## Definition of done

- [ ] Server/Client boundaries chosen deliberately; `'use client'` only on interactive leaves; boundary props serializable.
- [ ] Server Actions validate and authorize inside the action; tests cover the rejection path.
- [ ] Forms use actions (`useActionState`/`useFormStatus`) rather than hand-rolled submit state.
- [ ] `eslint-plugin-react-hooks` clean; no suppressed `exhaustive-deps` without a written reason.
- [ ] Effects only synchronize external systems; each one returns a cleanup; no fetch-in-effect where the query layer or a Server Component fits.
- [ ] Suspense and error boundaries exist at each async seam, with retry and layout-stable fallbacks.
- [ ] No `forwardRef`, class components, or index keys in new code; memoization added only with a Profiler measurement.
- [ ] Component and hook tests written first (TDD) and passing per `testing_approach`.
