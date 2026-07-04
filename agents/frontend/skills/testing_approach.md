# Testing Approach

This skill governs how frontend code is tested: Vitest plus Testing Library for components, Playwright for end-to-end journeys, and MSW at the network seam — always asserting observable behavior, never implementation details. The stack matches `ui/`: Vitest 3, `@testing-library/react` 16 with `@testing-library/jest-dom` 6, jsdom 25. TDD applies: the failing test comes first.

## Component tests: Vitest + Testing Library

Vitest runs with `environment: 'jsdom'` and `jest-dom` matchers (`toBeVisible`, `toHaveAccessibleName`). Testing Library's contract is to find elements the way a user does, which makes the query priority order a design tool, not a style preference:

1. `getByRole` with the accessible name: `getByRole('button', { name: /save/i })` — the default.
2. `getByLabelText` for form fields.
3. `getByText` / `getByPlaceholderText` / `getByDisplayValue` for non-interactive content.
4. `getByAltText` / `getByTitle` for media.
5. `getByTestId` — last resort only. Needing it for an interactive element usually means the markup has an accessibility bug; fix the markup, not the test.

Interactions use `user-event` 14, never `fireEvent`: `fireEvent.change` skips the keydown/keypress/input chain real users produce and passes components that fail in browsers.

```tsx
test('creates an issue', async () => {
  const user = userEvent.setup();
  render(<IssueForm />);
  await user.type(screen.getByLabelText(/title/i), 'Fix reconcile');
  await user.click(screen.getByRole('button', { name: /save/i }));
  expect(await screen.findByRole('status')).toHaveTextContent(/saved/i);
});
```

Async rules: `findBy*` for elements that appear later; `queryBy*` (which returns null) only for asserting absence — `getBy*` throws, so it can never assert a negative. With fake timers, construct `userEvent.setup({ advanceTimers: vi.advanceTimersByTime })` or every awaited keystroke hangs. Cover the full state matrix per component: loading, error, empty, and populated, plus keyboard operation of the primary interaction.

Angular: Testing Library for Angular or `TestBed` with component harnesses, asserting rendered output and emitted outputs under the same query priorities.

## Network mocks: MSW 2.x

Mock the wire, not the module. MSW intercepts requests at the network level, so components exercise their real fetch/query code paths.

- `setupServer(...handlers)` in the Vitest setup file with `onUnhandledRequest: 'error'`, so an unexpected request fails loudly instead of hanging.
- Happy-path handlers are defined once and shared; individual tests override with `server.use(http.get('/api/issues', () => HttpResponse.json([], { status: 500 })))` to force error and empty states.
- The same handler definitions run in the browser via `setupWorker` for Playwright and local development, keeping mock behavior identical across layers.
- Never stub `global.fetch` or mock the HTTP client module: those tests pass while serialization, headers, and query-layer behavior go unexercised.

## End-to-end: Playwright

- A handful of critical journeys, not hundreds of permutations: sign-in, the primary create/edit flow, the payment-equivalent path. Component tests carry the combinatorial breadth; E2E proves the seams.
- Locate by role (`page.getByRole('button', { name: 'Save' })`) and assert with web-first assertions (`await expect(locator).toBeVisible()`), which auto-retry. `page.waitForTimeout()` is banned: it is either too short (flake) or too long (slow) and always wrong.
- Run against a production build, with `trace: 'on-first-retry'` so failures ship a full trace instead of a screenshot guess.
- Include one keyboard-only pass and an `@axe-core/playwright` scan of each covered journey, tying into the accessibility gate.

## What not to test

- Implementation details: internal state values, "the effect ran", private methods, mocked child props. These couple tests to refactors instead of behavior; a rename should not fail a test whose behavior is unchanged.
- Large-tree snapshots: they fail on every change, get regenerated on reflex, and assert nothing. Assert the specific text, role, or attribute that matters.
- The framework or library itself: do not re-test that TanStack Query caches or that Angular renders `@if`; test your configuration and your rendering of its states.
- CSS classes as behavior proxies; assert visible outcome (`toBeVisible`, computed accessible state) instead.
- Types: the compiler already checked them.

## Coverage expectations

Around 80% statement and branch coverage on changed code is the review bar, measured by Vitest's V8 provider and gated on new code, not retroactively. 100% is explicitly not a target: the last 20% buys assertion-free render tests that rot. Two hard rules outrank any percentage: every bug fix starts with a failing regression test, and every user-visible state (loading, error, empty, success) has an assertion somewhere in the pyramid.

## Common pitfalls

- `getByTestId` as the first query, hiding markup with no accessible role or name.
- `fireEvent` for typing and clicking, passing components that break under real events.
- Asserting absence with `getBy*` (throws before the assertion) instead of `queryBy*`.
- Ignored `act(...)` warnings: an un-awaited update is asserting mid-render.
- Mocking `fetch` or the API module instead of MSW, leaving the real request path untested.
- Fake timers without `advanceTimers` in `userEvent.setup`, deadlocking awaited input.
- E2E for every edge case: minutes-long flaky suites that invert the testing pyramid.
- Snapshot files nobody reads, regenerated with `-u` on every failure.

## Definition of done

- [ ] Failing test written before the implementation (TDD red) for every behavior change and bug fix.
- [ ] Component tests query by role/label first; `getByTestId` absent or justified inline.
- [ ] All interactions via `user-event` with `setup()`; async handled with `findBy*`/`queryBy*`; no `act` warnings in the run.
- [ ] Loading, error, empty, and success states each asserted; keyboard path covered for the primary interaction.
- [ ] Network mocked exclusively with MSW (`onUnhandledRequest: 'error'`); failure cases forced via per-test `server.use` overrides.
- [ ] Critical journeys covered in Playwright with role locators and web-first assertions; no `waitForTimeout`; traces on retry; axe scan included.
- [ ] No implementation-detail assertions or large-tree snapshots in the diff.
- [ ] Coverage on changed code >= 80% statements/branches, with the gate green in CI; suite deterministic and offline.
