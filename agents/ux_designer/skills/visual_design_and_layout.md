# Visual Design and Layout

Govern visual hierarchy, typography, color, spacing, and layout so an interface is legible, scannable, and consistent, and so a viewer's eye lands on the primary action before anything else. Decide these properties as named values that become design tokens and component specs handed to the `frontend` agent; the output of this work is a visual spec, never a stylesheet.

## Build one visual hierarchy and point it at the primary action

Every screen has exactly one primary action (the thing the user came to do) and a hierarchy that ranks the rest below it. Rank by combining the four levers, not by relying on one:

- Size and weight: the primary action and the page's first-level heading are the largest, heaviest elements in view. A common, defensible split is a `2:1` area ratio between the primary button and a secondary button, or simply a filled primary against an outline/ghost secondary at the same size.
- Color and contrast: reserve the highest-saturation brand color for the single primary action so it reads as the one "hot" element. Contrast is also a hierarchy tool, not only a legibility floor: a heading at near-black `#1A1A1A` on white reads as more important than supporting text dropped to a mid-gray, even when both pass the legibility minimum. For the exact contrast ratios that legibility requires, reference the sibling skill `accessibility_by_design_wcag_22.md`; do not re-specify ratios here.
- Whitespace: isolation signals importance. Give the primary action and section headings more surrounding space than dense body content so they separate from the noise.

The concrete test in a mockup: squint until the screen blurs, or drop it to grayscale. If the primary action is no longer the first thing you notice, the hierarchy has failed and you fix it by changing size, weight, or spacing before you reach for a brighter color. Specify the result as a small set of named roles (display, heading levels, body, caption, primary/secondary action) rather than per-element one-offs, so the `frontend` agent maps roles to components.

## Typographic scale on a modular ratio

Pick one modular ratio and derive every type size from a single base, so sizes relate by multiplication instead of arbitrary choices. Use `1.2` (minor third) for dense, information-heavy UI where many sizes must coexist without large jumps, and `1.25` (major third) when you want more dramatic separation between headings and body. From a `16px` base:

| Ratio | Base | Step +1 | +2 | +3 | +4 |
|---|---|---|---|---|---|
| 1.2 | 16 | 19.2 | 23.04 | 27.65 | 33.18 |
| 1.25 | 16 | 20 | 25 | 31.25 | 39.06 |

Round to whole or half pixels when you record the token values. Hold the body text at `16px` minimum on the web so it is comfortable without zoom.

- Line length (measure): keep body copy between `45` and `75` characters per line, targeting `66`. Below 45 the eye returns too often and rhythm breaks; above 75 it loses the start of the next line. In a mockup this is a constraint on the content column's max width, not on the viewport.
- Line-height (leading): body text gets `1.4` to `1.6` (use `1.5` as the default). Tighten headings toward `1.1`-`1.25` because large type needs less leading to feel connected. Long line lengths need more line-height; a 70-character measure reads better at 1.6 than at 1.4.
- Weight and case: limit a screen to two or three weights (for example 400 body, 600 headings, 700 for the rare emphasis). Avoid all-caps for anything longer than a short label; it slows reading because word shapes flatten.

## Spacing on an 8pt grid with 4pt for fine adjustment

Put every margin, padding, and gap on an `8pt` grid (`8, 16, 24, 32, 40, 48, 64`), and allow `4pt` only for fine adjustment inside small components (icon-to-label gaps, tight input padding). A predictable rhythm is the reason: when all spacing is a multiple of 8, elements align across unrelated components without per-screen tuning, and the `frontend` agent can implement spacing from a token scale instead of guessing.

Apply space to express relationship, which is where spacing meets hierarchy: the gap between a label and its own field is smaller (`4`-`8`) than the gap between one field group and the next (`24`-`32`). When two elements are closer to each other than to their neighbors, you have already told the user they belong together before any border or background is drawn. Record spacing as a named scale (for example `space-1` = 4, `space-2` = 8, and so on); the tier structure and the DTCG token format live in the sibling skill `design_systems_and_tokens.md`, so reference it rather than re-specifying token structure here.

## Color organized by semantic role

Define color by the job it does, not by its hue, so the same token survives a rebrand or a theme switch:

- Brand / primary: the one accent that marks the primary action and key interactive states. Used sparingly so it keeps its signaling power; if half the screen is brand color, nothing stands out.
- Neutral / surface: the grays for backgrounds, surfaces, borders, and the full text range from primary to disabled. This is most of the pixels on a screen. Specify a ramp (for example `neutral-0` through `neutral-900`) so you can build elevation and text hierarchy from one consistent set.
- Feedback: distinct, conventional hues for `success` (green), `warning` (amber), `error` (red), and `info` (blue). Define each as a small set (a strong foreground and a tinted background) so a designer can specify a complete alert or inline-validation state from tokens.

The non-negotiable rule: meaning must never be carried by color alone. A red field border without an error message, or a green dot without a "Connected" label, is invisible to a color-blind user and to anyone scanning quickly. Pair every color-coded state with text, an icon, or a shape. The mockup decision this drives: when you draw an error state, you draw the icon and the message in the same pass as the red, never the red on its own.

## Layout grids and responsive, mobile-first design

Design the smallest viewport first, then add columns and density as space appears; this forces a real content priority decision instead of cramming a desktop layout onto a phone. Lay content on a column grid with a defined gutter and outer margin so blocks align to shared edges.

- A 12-column grid is the workhorse because 12 divides into halves, thirds, quarters, and sixths, covering most layouts without a custom grid per screen.
- Common breakpoints: mobile up to `~600px`, tablet `~600-1024px`, desktop `1024px+`. Treat these as where the layout must change (columns added, navigation revealed), not as fixed device sizes.
- Fluid type and spacing between breakpoints: let the largest display sizes and section spacing scale with the viewport (a `clamp()`-style min/preferred/max range that the `frontend` agent implements) so a heading is not oversized on a phone or undersized on a wide monitor. Specify the min and max as values; keep body text fixed at its readable minimum.
- Cap the content measure independent of the viewport: a text column should hit its 45-75 character max width and then stop growing, even on a 1440px screen, with the extra space becoming margin.

## Gestalt grouping to structure relationships

Use the Gestalt principles to make structure visible before the user reads a word. Each maps to a concrete mockup move:

- Proximity: group related items by reducing the space between them and increasing space to other groups. This is the cheapest grouping tool and should be tried before borders or boxes.
- Similarity: items that share size, color, or shape read as the same kind of thing. Make every clickable chip look alike so the user learns one visual pattern.
- Common region: a shared background or border encloses items into one unit (a card). Use it when proximity alone is not enough, such as separating two equally dense groups.
- Closure: the eye completes implied shapes, so a layout does not need a full box or rule on every side; an aligned edge and consistent spacing imply the container. Removing unnecessary lines reduces visual noise without losing the grouping.

When two of these conflict (for example, similarity pulling items together while proximity pushes them apart), proximity usually wins for grouping; resolve the conflict deliberately rather than letting it sit.

## Common pitfalls

- More than one element competing to be the primary action: with two equally loud buttons the user hesitates and the conversion path blurs. Demote all but one to secondary or tertiary.
- Type sizes chosen ad hoc instead of from one ratio and base: the scale looks arbitrary, sizes nearly collide, and the `frontend` agent cannot derive a clean token set. Reject any size that is not on the declared scale.
- Body line length left to fill the viewport: full-width paragraphs on a wide screen run well past 75 characters and become hard to track. Cap the measure.
- Spacing values off the grid (`13px`, `27px`): rhythm breaks and elements fail to align across components. Every value must be a multiple of 8, or 4 for fine adjustment.
- Color as the only signal of state: red-only errors and green-only status are unreadable for color-blind users and easy to miss when scanning. Always pair color with text or an icon.
- One brand color used everywhere: when the accent is on every surface it stops signaling the primary action. Reserve it.
- Desktop-first layouts retrofitted to mobile: content priority was never decided, so the phone view is a cramped afterthought. Start at the smallest viewport.
- Boxes and rules added to group items that proximity would have grouped for free: the result is heavy and noisy. Try space first, enclose only when needed.
- Re-specifying contrast ratios or token structure inline: these belong in the sibling skills and will drift out of sync if duplicated. Reference `accessibility_by_design_wcag_22.md` and `design_systems_and_tokens.md`.

## Definition of done

- [ ] The screen has one named primary action, and a grayscale or squint test confirms it is the first element noticed.
- [ ] Type sizes all derive from a single base and one declared modular ratio (1.2 or 1.25), recorded as named roles.
- [ ] Body copy is 16px minimum, line length is constrained to 45-75 characters, and body line-height is 1.4-1.6.
- [ ] Every margin, padding, and gap is a multiple of 8pt, with 4pt used only for fine adjustment, and spacing expresses grouping (tighter within a group than between groups).
- [ ] Color is specified by semantic role (brand, neutral/surface, feedback success/warning/error/info), and no state relies on color alone — each is paired with text or an icon.
- [ ] The layout is defined mobile-first on a column grid with declared breakpoints, fluid display type and spacing ranges, and a capped content measure.
- [ ] Grouping is justified with a named Gestalt principle, and unnecessary borders or rules have been removed in favor of proximity and alignment.
- [ ] The deliverable is a visual spec plus token values for the `frontend` agent, not CSS or component code, and it references the accessibility and design-token sibling skills instead of restating them.
