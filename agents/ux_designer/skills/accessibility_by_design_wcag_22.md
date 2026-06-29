# Accessibility By Design (WCAG 2.2 AA)

Decide accessibility in the design, against WCAG 2.2 Level AA, so the build inherits an accessible specification instead of retrofitting fixes. WCAG 2.2 has been a W3C Recommendation since 2023-10-05; this skill is the design-time half of accessibility, and the frontend agent's `accessibility_target_wcag_22_aa` is the implementation-time half (semantic markup, ARIA, keyboard wiring). Contrast, target size, focus, content order, and motion are mockup decisions and travel as annotations in the handoff.

## Contrast, decided in the mockup

- Text contrast (SC 1.4.3, AA): at least 4.5:1 for normal text and 3:1 for large text. Large text is 18.66px bold or 24px regular and larger. Check every text-on-surface pairing in the design, including text over images and in every theme.
- Non-text contrast (SC 1.4.11, AA): at least 3:1 for interactive component boundaries, focus indicators, icons, and meaningful graphics against their adjacent color. A 1px hairline border at 1.5:1 fails.
- Color is never the only signal (SC 1.4.1): pair color with text, an icon, or a pattern. A red/green status that reads identically in grayscale fails for color-blind users.

## Target size and pointer input

- Target size minimum (SC 2.5.8, AA, new in WCAG 2.2): interactive targets are at least 24x24 CSS px, or have 24px of clear spacing to neighboring targets. Exceptions are inline links in text, an equivalent control elsewhere, and user-agent-default controls. Design touch-first controls larger (44x44 px is the comfortable mobile target).
- Dragging movements (SC 2.5.7, AA, new in 2.2): any drag interaction has a single-pointer alternative (tap, click, or buttons). Do not design a reorder or slider that can only be dragged.

## Focus, decided in the design

- Focus order (SC 2.4.3): the design specifies a logical focus order that follows reading and meaning, not source-order accident. Annotate it on the handoff.
- Focus visible and not obscured (SC 2.4.7 AA, and SC 2.4.11 Focus Not Obscured (Minimum), new in 2.2): every interactive element has a designed, visible focus indicator that meets 3:1 non-text contrast, and a sticky header, toolbar, or cookie banner must not fully hide the focused element. Design the focus state as deliberately as the hover state.

## Text, zoom, and layout

- Resize text (SC 1.4.4): the layout works at 200% text zoom without loss of content or function. Design with relative units in mind; do not fix text in a box that clips when enlarged.
- Reflow (SC 1.4.10): content reflows to a 320px-wide viewport with no two-dimensional scrolling for the main flow. The responsive design must include the narrow case.
- Text spacing (SC 1.4.12): the design tolerates increased line-height, paragraph, letter, and word spacing without clipping. Do not pack text into a box with no slack.

## Forms, errors, and help

- Labels and instructions (SC 3.3.2) and error identification (SC 3.3.1): every field has a visible, persistent label and a specific, in-context error message that names the problem and the fix. Placeholder-only labels fail because they vanish on input.
- Redundant entry (SC 3.3.7, new in 2.2): do not ask the user to re-enter information already provided in the same process; auto-populate or offer it.
- Accessible authentication (SC 3.3.8, AA, new in 2.2): do not require a cognitive test (solving a puzzle, transcribing characters, memorizing) to log in; allow paste, password managers, and copy from another step.
- Consistent help (SC 3.2.6, new in 2.2): if a help affordance exists, place it in the same relative location across pages.

## Motion and timing

- Animation from interactions: honor a reduced-motion preference in the design by specifying a reduced or no-motion variant for non-essential animation.
- Three flashes (SC 2.3.1): nothing flashes more than three times per second.

## Annotating the handoff

Accessibility decisions are part of the design specification, not a verbal note. The handoff carries focus order, accessible names for icon-only controls, the contrast pairs used, target sizes, and reduced-motion variants. See `prototyping_and_design_handoff`. The frontend agent implements them; this agent verifies them at design QA.

## Common pitfalls

- Choosing a brand palette and only checking contrast at handoff: failing pairs force a rework of the visual design instead of a token tweak. Check at the moment colors are chosen.
- Designing a hover state but no focus state: keyboard users get no visible indication, failing SC 2.4.7.
- Placeholder text used as the only label: it disappears on focus and fails labeling and contrast.
- Targets below 24x24 px with no spacing exception: a new WCAG 2.2 failure that is invisible until tested.
- Status conveyed by color alone: fails 1.4.1 for color-blind users; add text or an icon.
- A drag-only interaction with no single-pointer alternative: fails SC 2.5.7, added in 2.2.
- Treating accessibility as the frontend agent's problem: contrast and target size are design decisions, and deferring them moves a cheap fix into an expensive one.

## Definition of done

- [ ] Every text and non-text contrast pair meets 4.5:1 / 3:1 (text) and 3:1 (non-text) in every theme.
- [ ] No information is conveyed by color alone.
- [ ] Interactive targets meet 24x24 CSS px or the spacing exception; touch targets are designed comfortably larger.
- [ ] A logical focus order and a visible, non-obscured focus indicator are designed and annotated.
- [ ] The layout holds at 200% text zoom and reflows to 320px without loss of content or function.
- [ ] Forms have visible labels, specific recoverable errors, no redundant entry, and no cognitive-test login.
- [ ] Non-essential motion has a reduced-motion variant and nothing flashes more than three times per second.
- [ ] Accessibility annotations (focus order, accessible names, contrast pairs, target sizes) are included in the handoff to the frontend agent.
