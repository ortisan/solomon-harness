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
