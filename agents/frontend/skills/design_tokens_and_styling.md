---
name: design-tokens-and-styling
description: Governs how visual decisions are encoded through design tokens as the single source of truth, so components never hardcode raw values and theming means swapping token values, not rewriting styles. Use when styling a component, adding a color or spacing value, or reviewing a diff for hardcoded values.
---

# Design Tokens and Styling

This skill governs how visual decisions are encoded and consumed: tokens are the single source of truth, components never touch raw values, and theming happens by swapping token values, not rewriting component styles. A raw hex color or magic pixel number in a component is a review rejection.

## Token tiers

Three tiers, referencing in one direction only (component -> semantic -> primitive):

- Primitive (option) tokens: the raw palette and scales, named by value, not by use. `blue-500: #3b82f6`, `space-4: 1rem`, `font-size-sm: 0.875rem`. Components never consume these directly.
- Semantic (decision) tokens: named by role, mapped to primitives. `--color-surface`, `--color-text-primary`, `--color-border-danger`, `--space-inset-md`. This is the tier components consume and the tier themes swap.
- Component tokens: optional third tier for widely reused components with variants (`--button-primary-bg`), referencing semantic tokens. Introduce them only when a component's variants genuinely need their own vocabulary; a component token pointing at a primitive is a smell.

Back edges (a semantic token hardcoding a hex, a component reading `blue-500`) break theming silently: the value looks right until the first dark-mode pass.

## CSS custom properties as the runtime

Custom properties are the delivery mechanism because they cascade, cross framework boundaries, and switch at runtime without recompilation.

```css
:root {
  color-scheme: light dark;
  --color-surface: #ffffff;
  --color-text-primary: #18181b;
}
:root[data-theme='dark'] {
  --color-surface: #18181b;
  --color-text-primary: #fafafa;
}
.card {
  background: var(--color-surface);
  color: var(--color-text-primary);
  padding: var(--space-inset-md);
}
```

Set `color-scheme` so native controls, scrollbars, and form elements follow the theme. For simple two-value cases, `light-dark(#fff, #18181b)` (Baseline 2024) collapses the pair into one declaration.

## Dark-mode strategy

- Theme switching happens exclusively on the semantic tier. If shipping dark mode requires touching component files, the token architecture has failed.
- Default to `prefers-color-scheme`, with an explicit user override (`data-theme` on `<html>`) that wins over the system preference and persists in `localStorage`. Apply the stored theme in an inline script before first paint to avoid the light-flash.
- Dark mode is not color inversion: reduce saturation, avoid pure black (`#18181b`-range surfaces reduce smearing on OLED), and re-verify contrast in both themes — 4.5:1 for text, 3:1 for UI boundaries, per the accessibility skill.
- Gate non-essential motion behind `prefers-reduced-motion: reduce`; motion preferences are theming too.

## W3C design tokens format

The Design Tokens Community Group (DTCG) format is the interchange standard: tokens as JSON with `$value`, `$type`, and `$description`, and aliases via `{color.blue.500}` references.

```json
{
  "color": {
    "surface": { "$type": "color", "$value": "{color.neutral.0}" }
  }
}
```

Keep one `tokens.json` as the source of truth and generate every platform output — CSS custom properties, a TypeScript constants module, Tailwind theme values — with Style Dictionary 4.x, which speaks DTCG natively. Design tools (Figma variables via Tokens Studio) sync against the same file. Two hand-maintained token sources (one in Figma, one in code) always drift; the generator is the fix.

## Tailwind vs CSS-in-JS in 2026

- Tailwind CSS 4 (what `ui/` uses) is CSS-first: the theme is declared with `@theme` in CSS, and every theme value is emitted as a CSS custom property, so Tailwind utilities and hand-written CSS share one token set. Utilities must map to the theme; arbitrary values like `p-[13px]` bypass the token system and are a review flag outside genuine one-offs.
- Runtime CSS-in-JS (styled-components, Emotion) is the wrong default in 2026: it cannot render inside React Server Components, adds per-render style computation, and styled-components entered maintenance mode in 2025. Do not start new work on it.
- Zero-runtime alternatives compile to static CSS and are RSC-safe: CSS Modules (simplest), vanilla-extract (typed styles), Panda CSS or StyleX (token-aware variants at scale). Choose one of these when a design-system component library needs typed variant APIs that utility classes express poorly.
- Decision rule: Tailwind 4 for product surfaces (velocity plus token enforcement through `@theme`); CSS Modules or vanilla-extract for the shared component library; Angular component styles stay scoped per component consuming the same custom properties. Never global selectors that leak across components.

## Common pitfalls

- Raw hex, rgb, or pixel values in components instead of semantic tokens: theming and consistency break one-off by one-off.
- Components consuming primitive tokens directly, so a palette change restyles the app unpredictably and dark mode requires component edits.
- Dark mode implemented as scattered `.dark .card { ... }` component overrides instead of a semantic-tier value swap.
- Theme applied after hydration, flashing light mode on every load.
- Tokens duplicated between Figma and code with no generator, drifting within a sprint.
- Tailwind arbitrary values (`text-[13px]`, `bg-[#1a1a1a]`) routing around the theme.
- New code on runtime CSS-in-JS inside an RSC app, forcing `'use client'` on styling grounds alone.

## Definition of done

- [ ] Every visual value in the change resolves to a semantic token; no raw hex, rgb, or magic pixel numbers in component code.
- [ ] Reference direction holds: component -> semantic -> primitive, with no back edges.
- [ ] Tokens defined once (DTCG `tokens.json` or Tailwind `@theme`) and generated outputs are not hand-edited.
- [ ] Dark mode works by token swap alone: `prefers-color-scheme` default, persistent `data-theme` override, no first-paint flash, `color-scheme` set.
- [ ] Contrast verified in both themes: >= 4.5:1 text, >= 3:1 UI component boundaries.
- [ ] `prefers-reduced-motion` gates non-essential animation.
- [ ] Styles are scoped (Tailwind theme utilities, CSS Modules, or Angular component styles); no leaking global selectors; arbitrary values justified inline or removed.
- [ ] Visual regression coverage exists for token-sensitive components in both light and dark themes.
