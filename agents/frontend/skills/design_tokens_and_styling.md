## Design tokens and styling


- Single source of truth for design decisions. Define tokens once (CSS custom properties and/or `tailwind.config` `theme.extend`) and consume them everywhere. No raw hex colors, pixel magic numbers, or one-off spacing in components.
- Use semantic tokens, not raw values: `--color-surface`, `--color-text-primary`, `--space-4`, not `#1a1a1a` or `16px` inline.
- Respect a spacing scale (e.g. 4px base) and a typographic scale. Tailwind utilities must map to the token theme, not arbitrary `[13px]` values except where unavoidable.
- Theming through tokens: support light/dark via `prefers-color-scheme` plus a manual override, switching token values, not rewriting component styles.
- Honor `prefers-reduced-motion`: gate non-essential animation and transitions behind it.
- Keep styles co-located and scoped (CSS Modules, Tailwind, or Angular component styles). Avoid global selectors that leak.
