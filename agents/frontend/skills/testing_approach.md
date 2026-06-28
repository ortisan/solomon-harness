## Testing approach


- Test behavior, not implementation. React Testing Library queries by role/label/text the way a user finds things; avoid testing internal state or snapshotting large opaque trees.
- Cover: rendering with required props, user interactions (click, type, keyboard), conditional/empty/error/loading states, and accessibility (roles, labels, focus).
- Mock all external services (MSW for HTTP, fake timers for time). No real network in unit/integration tests.
- E2E for critical user journeys with Playwright or Cypress, including a keyboard-only path for a primary flow.
- Use Storybook (or Angular stories) for component states and visual review where it adds value; pair with visual regression for design-token-sensitive UI.
- Angular: prefer Testing Library for Angular or `TestBed` with component harnesses; assert on rendered output and emitted outputs, not private methods.
