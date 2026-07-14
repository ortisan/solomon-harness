---
name: accessibility-target-wcag-22-aa
description: Sets WCAG 2.2 AA as the accessibility conformance floor for every interface, covering SPA-specific obligations such as focus management, page-load announcements, target size, and semantic HTML before ARIA. Use when building or reviewing any React or Angular component, page, or interaction for accessibility compliance.
---

# Accessibility (Target: WCAG 2.2 AA)

This skill sets WCAG 2.2 AA as the conformance floor for every interface shipped here, with the SPA-specific obligations spelled out: single-page apps defeat the browser behaviors (focus reset, page-load announcement) that static pages get for free, so the app must recreate them deliberately. Semantic HTML first; ARIA only when no native element fits.

## WCAG 2.2 criteria that bite in SPAs

WCAG 2.2 (W3C Recommendation, October 2023) added nine success criteria; these are the AA ones that routinely fail in component work:

- 2.5.8 Target Size (Minimum): interactive targets at least 24x24 CSS px, or equivalent spacing to neighbors. Icon buttons, table-row actions, and close buttons are the usual offenders; 24 px is the floor, 44 px is the comfortable default for primary touch targets.
- 2.4.11 Focus Not Obscured (Minimum): the focused element must not be fully hidden by sticky headers, footers, or cookie banners. Tab through every page with the sticky chrome present; `scroll-padding-top` on the scroll container is the usual fix.
- 3.3.7 Redundant Entry: within a flow, never ask for the same information twice; carry values forward across wizard steps and keep fields autofill-friendly (`autocomplete` attributes).
- 3.3.8 Accessible Authentication (Minimum): no cognitive test to log in. Never block paste in password fields; support password managers and WebAuthn.
- 2.5.7 Dragging Movements: any drag interaction (reorder, slider, kanban) needs a single-pointer alternative such as move-up/move-down buttons.
- 3.2.6 Consistent Help: if a help mechanism exists, it appears in the same relative place on every page.

The long-standing AA criteria still carry the routine work: 1.4.3 contrast (4.5:1 text, 3:1 large text and UI boundaries, re-checked per theme), 2.4.7 visible focus, 1.4.10 reflow at 320 px width, 2.1.1 keyboard operability.

## SPA focus management

Client-side routing swaps the DOM without a page load, so a screen reader hears nothing and keyboard focus is stranded on a removed node.

- On route change, move focus to the new view's `<h1>` (given `tabindex="-1"`) or a labeled main region, and let that announce the navigation. Neither React Router, Next.js, nor the Angular Router does this adequately by default; it is application code, written once in the router integration.
- Dialogs: focus enters the dialog on open, stays trapped while open, and returns to the triggering element on close. Prefer native `<dialog>` with `showModal()`, which supplies the trap, `Esc` dismissal, and top-layer rendering for free; otherwise use a vetted trap (Angular CDK `FocusTrap`, `focus-trap-react`). A trap must always be escapable via keyboard (2.1.2 No Keyboard Trap).
- When an element is deleted (list row, toast), move focus to a sensible neighbor before removal; focus falling to `<body>` silently strands keyboard users.
- Async updates that matter (save confirmed, results loaded) are announced through a single polite `aria-live` region; do not scatter live regions or announce every keystroke.

## ARIA only when native fails

The first rule of ARIA: do not use it if a native element does the job. `<button>`, `<a href>`, `<label>` + `<input>`, `<select>`, `<details>`, `<dialog>` ship keyboard behavior, focusability, and semantics that a `<div role="button">` must reimplement by hand.

- When a custom widget is genuinely required (combobox, tree, tabs), implement the full ARIA Authoring Practices Guide pattern: roles, states (`aria-expanded`, `aria-selected`), and the complete keyboard map (arrow keys, Home/End, roving tabindex) — half a pattern is worse than none, because it promises behavior it does not deliver.
- Accessible names come from visible labels first (1.3.5 / label-in-name); `aria-label` is the fallback, never a decoration on non-interactive containers.

## Automated checks in CI

- axe-core runs in CI and violations fail the build: `vitest-axe` (or `jest-axe`) at component level, `@axe-core/playwright` against rendered pages in E2E.
- Static lint: `eslint-plugin-jsx-a11y` for React; `angular-eslint` template accessibility rules for Angular.
- Calibration: automated tooling finds roughly a third to a half of real-world issues. A green axe run is a floor, not conformance.

## Manual test checklist

Run per feature, before review:

- Keyboard-only pass of the whole flow: reachable, operable, visible focus, logical order, no traps, skip link works.
- Screen reader smoke test of the primary path (VoiceOver + Safari or NVDA + Chrome): route changes and async results are announced, form errors are read.
- 200% zoom and 320 px-wide reflow: no lost content or horizontal scroll.
- Contrast spot-check in both light and dark themes.
- Forms: every control labeled, errors linked via `aria-describedby` and announced, nothing asked twice.
- `prefers-reduced-motion` verified against animations.

## Common pitfalls

- `div`/`span` with a click handler: no keyboard, no role, no focus; use `<button>`.
- Route change with no focus management: screen-reader silence, focus on a dead node.
- Focus not returned to the trigger when a dialog closes, or a trap without `Esc`.
- Placeholder text used as the only label; it vanishes on input and is not a name.
- Toast-only error feedback that is never announced to assistive tech.
- `aria-hidden="true"` on content that still contains focusable elements.
- Positive `tabindex` values fighting the natural order.
- A custom dropdown with `role="listbox"` but no arrow-key or type-ahead support.
- Sticky header covering the focused element after tabbing (2.4.11).

## Definition of done

- [ ] Semantic HTML first; every ARIA attribute justified by a missing native capability and matching a complete APG pattern.
- [ ] Full flow operable keyboard-only with visible focus, logical order, and no traps; skip link present.
- [ ] Route changes move focus and announce the new view; dialogs trap, restore, and dismiss with `Esc`; deletions relocate focus.
- [ ] Interactive targets >= 24x24 CSS px; focused elements never fully obscured by sticky chrome.
- [ ] Contrast >= 4.5:1 (text) and >= 3:1 (UI) in every theme; reflow holds at 320 px and 200% zoom.
- [ ] Forms: labels, linked and announced errors, `autocomplete` set, no redundant entry, paste never blocked.
- [ ] axe-core (component and E2E) plus a11y lint rules run in CI and fail on violations.
- [ ] Manual checklist executed and noted in the PR, including one screen-reader pass of the primary path.
