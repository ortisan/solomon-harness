## Accessibility (target: WCAG 2.2 AA)


- Semantic HTML first. Use `<button>`, `<a>`, `<nav>`, `<main>`, `<label>`, headings in order. Reach for ARIA only when no native element fits, and follow the ARIA Authoring Practices for the pattern.
- Keyboard: every interactive element is reachable and operable by keyboard, in a logical tab order, with a visible focus indicator. No keyboard traps. Provide a skip-to-content link.
- Forms: every control has an associated `<label>`; errors are programmatically linked (`aria-describedby`) and announced.
- Contrast: at least 4.5:1 for normal text, 3:1 for large text and for UI component/graphic boundaries.
- Target size (WCAG 2.2 SC 2.5.8): interactive targets at least 24x24 CSS px, or with adequate spacing.
- Manage focus on route changes, dialog open/close, and dynamic content; return focus to the trigger when a dialog closes. Use a focus trap for modals (Angular CDK `FocusTrap` or a vetted React library).
- Announce async updates with a polite live region where appropriate; do not over-announce.
- Test it: run `axe-core` (jest-axe / `@axe-core/playwright`) in CI and fail on violations. Lint with `eslint-plugin-jsx-a11y`. Automated checks catch roughly 30-40 percent of issues, so add at least one keyboard-only and one screen-reader smoke pass for key flows.
