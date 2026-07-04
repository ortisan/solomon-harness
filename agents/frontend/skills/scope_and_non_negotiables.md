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

## Common pitfalls

- UI logic merged without a failing-first test — violates the mandatory Red-Green-Refactor rule; a test that could not fail proves nothing about the behavior.
- One component owning data fetching, state, and markup past the ~200-line or ~5 shape-shifting-props signal — violates single responsibility and the container/presentational split this scope demands.
- `any` or implicit `undefined` in a public prop/input contract — breaks the typed design-contract boundary; every consumer inherits the untyped surface.
- Tests hitting real HTTP, timers, or analytics instead of MSW and `vi.useFakeTimers`/`jasmine.clock` — nondeterministic and online, violating the mock-all-external-services rule.
- A raw division or unchecked array index over API data rendered into the DOM — violates the numeric-guard rule; the first degenerate response shows users `NaN`.
- Client-side-only permission gating, or tokens in `localStorage` and bundles — fails the STRIDE items for elevation of privilege and information disclosure.
- `dangerouslySetInnerHTML`/`[innerHTML]` fed unsanitized content — an XSS hole this scope prohibits outright without DOMPurify or `DomSanitizer`.

## Definition of done

- [ ] Every component and hook in the change has a test (render assertion, interaction, or accessibility check) that failed before the implementation existed.
- [ ] Public prop/input contracts are fully typed: no `any`, no implicit `undefined`; required vs optional and default values documented.
- [ ] Components stay single-responsibility; anything approaching 200 lines or 5+ shape-shifting props was split into container and presentational parts.
- [ ] Tests run deterministic and offline: HTTP through MSW, timers via `vi.useFakeTimers`/`jasmine.clock`, browser APIs and analytics mocked.
- [ ] Numeric and external data guarded: no unchecked division or array indexing on API data reaches the DOM; response shapes validated with zod/io-ts at the fetch boundary.
- [ ] STRIDE at the UI boundary holds: no secrets or tokens in bundles, source maps, or `localStorage`; untrusted HTML sanitized; expensive handlers debounced; in-flight requests cancelled; permissions enforced server-side.
- [ ] Docstrings and comments unrelated to the change are untouched.
- [ ] The change sits on a `feature/*` or `bugfix/*` branch with Conventional Commit messages.
