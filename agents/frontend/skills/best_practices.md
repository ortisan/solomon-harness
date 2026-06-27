# Frontend Best Practices: React and Angular

Build accessible, fast, well-tested React and Angular interfaces with a disciplined approach to components, hooks, state, and design tokens.

## Scope and non-negotiables

This skill governs every UI change you ship: React and Angular components, hooks/signals, client state, styling via design tokens, accessibility, and performance. Work only on `feature/*` or `bugfix/*` branches under Git Flow, and commit with Conventional Commits.

Mandatory competencies carried from the project rules, made concrete for this role:

- TDD is mandatory. Red-Green-Refactor on every component and hook. Write the failing test first (render assertion, interaction, or accessibility check), then the implementation. No UI logic lands without a test that would fail if the logic broke.
- SOLID and modular design. One responsibility per component. Split container (data/state) from presentational (markup/style). A component over ~200 lines or with more than ~5 props that change shape is a refactor signal.
- Design contracts at boundaries. Every component has an explicit, typed prop/input contract (TypeScript interfaces, `@Input()`/`@Output()` or `input()`/`output()` with types). No `any`. No implicit `undefined` in public props. Document required vs optional and default values.
- Mock all external services in tests. Network, browser APIs, timers, and analytics are mocked (MSW for HTTP, `vi.useFakeTimers`/`jasmine.clock`). Tests must be deterministic and offline.
- Preserve existing docstrings and comments unrelated to your change.
- Guard numeric and external data before render. Frontends display quant/ML outputs; protect against `NaN`, `Infinity`, divide-by-zero, and null/undefined. Never render a raw division (`a / b`) into the DOM without a zero/finite check, and never index an array from API data without verifying length. Validate response shape at the fetch boundary (zod/io-ts or equivalent) before it reaches a component.
- Security is part of the contract. Apply STRIDE at the UI boundary: Spoofing (validate auth state, never trust client-stored roles for gating sensitive data), Tampering (validate and sanitize all inputs, never build DOM from untrusted strings), Repudiation (log meaningful user actions where required), Information disclosure (no secrets/tokens in bundles, source maps, or `localStorage`; scrub PII from logs), Denial of service (debounce/throttle expensive handlers, cancel in-flight requests), Elevation of privilege (server is the authority for permissions; client gating is UX only). Never use `dangerouslySetInnerHTML`/`[innerHTML]` with unsanitized content; sanitize with DOMPurify or Angular's `DomSanitizer`. Ship a Content-Security-Policy and avoid inline event handlers.

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

## Angular standards

- Standalone components by default (the default since Angular 19; do not add `standalone: true`, and avoid NgModules for new features).
- Signals for component state and derived values (`signal`, `computed`, `effect`, `linkedSignal` for state that resets from a source). Use the new control flow (`@if`, `@for`, `@switch`) with `track` on every `@for`.
- `ChangeDetectionStrategy.OnPush` on every component. Drive views with the `async` pipe or signals rather than manual `subscribe`. Zoneless change detection is available in recent versions and removes the Zone.js dependency; if you adopt it, keep the same OnPush/signal discipline so views still update predictably.
- RxJS hygiene: never leak subscriptions. Use the `async` pipe, `takeUntilDestroyed()`, or `toSignal()`. Manual `subscribe` without teardown is a defect.
- For remote data, prefer `toSignal()` or the `resource()`/`httpResource()` reactive APIs (Angular 19+, still stabilizing) over hand-managed subscriptions and effects.
- Use `inject()` over constructor injection for cleaner, tree-shakable code. Use typed reactive forms (`FormGroup<...>`); avoid template-driven forms for non-trivial input. Prefer the signal-based `input()`/`output()`/`model()` over decorators in new components.
- Lazy-load routes and use `@defer` blocks for below-the-fold or heavy components.
- Keep templates thin: no complex expressions or method calls in bindings (they run every change detection); precompute in `computed` signals or component fields.

## State management

Decision order, smallest scope first:

1. Local component state (`useState`/signal) for state used by one component.
2. Lifted/shared state via props/inputs or `children` composition.
3. Context (React) or a shared service with signals (Angular) for low-frequency, app-wide values: theme, locale, current user. Do not put high-frequency or large data in Context; it re-renders all consumers.
4. Server cache library for remote data: TanStack Query or RTK Query (React), or a signal store fed by typed services (Angular). Treat server data as a cache, not as client state. You get caching, dedup, retries, and invalidation for free instead of hand-rolling them in effects.
5. Dedicated client store (Redux Toolkit or Zustand for React; NgRx SignalStore or a service for Angular) only for genuinely global, cross-cutting client state.

Separate server state from client/UI state. Most "global state" pain is actually un-cached server state living in the wrong place.

## Design tokens and styling

- Single source of truth for design decisions. Define tokens once (CSS custom properties and/or `tailwind.config` `theme.extend`) and consume them everywhere. No raw hex colors, pixel magic numbers, or one-off spacing in components.
- Use semantic tokens, not raw values: `--color-surface`, `--color-text-primary`, `--space-4`, not `#1a1a1a` or `16px` inline.
- Respect a spacing scale (e.g. 4px base) and a typographic scale. Tailwind utilities must map to the token theme, not arbitrary `[13px]` values except where unavoidable.
- Theming through tokens: support light/dark via `prefers-color-scheme` plus a manual override, switching token values, not rewriting component styles.
- Honor `prefers-reduced-motion`: gate non-essential animation and transitions behind it.
- Keep styles co-located and scoped (CSS Modules, Tailwind, or Angular component styles). Avoid global selectors that leak.

## Accessibility (target: WCAG 2.2 AA)

- Semantic HTML first. Use `<button>`, `<a>`, `<nav>`, `<main>`, `<label>`, headings in order. Reach for ARIA only when no native element fits, and follow the ARIA Authoring Practices for the pattern.
- Keyboard: every interactive element is reachable and operable by keyboard, in a logical tab order, with a visible focus indicator. No keyboard traps. Provide a skip-to-content link.
- Forms: every control has an associated `<label>`; errors are programmatically linked (`aria-describedby`) and announced.
- Contrast: at least 4.5:1 for normal text, 3:1 for large text and for UI component/graphic boundaries.
- Target size (WCAG 2.2 SC 2.5.8): interactive targets at least 24x24 CSS px, or with adequate spacing.
- Manage focus on route changes, dialog open/close, and dynamic content; return focus to the trigger when a dialog closes. Use a focus trap for modals (Angular CDK `FocusTrap` or a vetted React library).
- Announce async updates with a polite live region where appropriate; do not over-announce.
- Test it: run `axe-core` (jest-axe / `@axe-core/playwright`) in CI and fail on violations. Lint with `eslint-plugin-jsx-a11y`. Automated checks catch roughly 30-40 percent of issues, so add at least one keyboard-only and one screen-reader smoke pass for key flows.

## Performance (target: Core Web Vitals "good")

- Field targets at the 75th percentile: LCP under 2.5s, INP under 200ms (INP replaced FID as the responsiveness metric), CLS under 0.1.
- Code-split by route and lazy-load heavy, below-the-fold, or rarely used components (`React.lazy`/`Suspense`, Angular `@defer`, dynamic `import()`).
- Set and enforce a bundle budget (Angular `budgets` in `angular.json`; a bundle analyzer in CI for React). Treat a regressive jump in initial JS as a build failure, not a warning.
- Prevent layout shift: reserve space for images/media with explicit `width`/`height` or `aspect-ratio`, and avoid injecting content above existing content.
- Optimize images: modern formats (AVIF/WebP), responsive `srcset`, `loading="lazy"` for off-screen, and `fetchpriority="high"` for the LCP image.
- Virtualize long lists (TanStack Virtual, Angular CDK `cdk-virtual-scroll`) instead of rendering thousands of nodes.
- Keep the main thread free: debounce/throttle scroll, resize, and input handlers; move heavy computation off the render path; cancel stale requests with `AbortController`.
- Measure before optimizing. Use the React Profiler, Angular DevTools, and Lighthouse/WebPageTest. Verify each optimization against numbers, not intuition.

## Testing approach

- Test behavior, not implementation. React Testing Library queries by role/label/text the way a user finds things; avoid testing internal state or snapshotting large opaque trees.
- Cover: rendering with required props, user interactions (click, type, keyboard), conditional/empty/error/loading states, and accessibility (roles, labels, focus).
- Mock all external services (MSW for HTTP, fake timers for time). No real network in unit/integration tests.
- E2E for critical user journeys with Playwright or Cypress, including a keyboard-only path for a primary flow.
- Use Storybook (or Angular stories) for component states and visual review where it adds value; pair with visual regression for design-token-sensitive UI.
- Angular: prefer Testing Library for Angular or `TestBed` with component harnesses; assert on rendered output and emitted outputs, not private methods.

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

## Definition of done

- [ ] Tests written first and passing; meaningful coverage of states, interactions, and accessibility; all external services mocked.
- [ ] TypeScript strict, no `any` in public contracts; props/inputs explicitly typed with documented defaults.
- [ ] Component is single-responsibility; container and presentation separated where it helps.
- [ ] Semantic HTML; keyboard operable; visible focus; labels and roles correct; `axe`/jsx-a11y clean.
- [ ] Contrast >= 4.5:1 (text) and >= 3:1 (large text and UI); interactive targets >= 24x24 CSS px.
- [ ] Styling uses design tokens only; no raw hex or magic numbers; dark mode and `prefers-reduced-motion` respected.
- [ ] State at the smallest viable scope; server data via a cache library; no leaking subscriptions/effects.
- [ ] No layout shift; lazy-loading and bundle budget respected; expensive handlers debounced; profiled for regressions.
- [ ] Numeric/external data guarded against `NaN`, `Infinity`, divide-by-zero, and null before render; responses shape-validated at the boundary.
- [ ] Security checks applied: no secrets in the bundle, untrusted HTML sanitized, inputs validated, permissions enforced server-side.
- [ ] Lint and type-check pass; Conventional Commit on a `feature/*` or `bugfix/*` branch.
