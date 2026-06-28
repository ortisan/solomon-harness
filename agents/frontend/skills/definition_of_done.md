## Definition of done


- [ ] Tests written first and passing; meaningful coverage of states, interactions, and accessibility; all external services mocked.
- [ ] TypeScript strict, no `any` in public contracts; props/inputs explicitly typed with documented defaults.
- [ ] Component is single-responsibility; container and presentation separated where it helps.
- [ ] Semantic HTML; keyboard operable; visible focus; labels and roles correct; `axe`/jsx-a11y clean.
- [ ] Contrast >= 4.5:1 (text) and >= 3:1 (large text and UI); interactive targets >= 24x24 CSS px.
- [ ] Styling uses design tokens only; no raw hex or magic numbers; dark mode and `prefers-reduced-motion` respected.
- [ ] State at the smallest viable scope; server data via a cache library; no leaking subscriptions/effects.
- [ ] No layout shift; lazy-loading and bundle budget respected; expensive handlers debounced; profiled for regressions.
- [ ] Numeric/external data guarded against `NaN`, `Infinity`, divide-by-zero, and null before render; responses shape-validated at the boundary.
- [ ] Security checks applied: no secrets in the bundle, untrusted HTML sanitized, inputs validated, permissions enforced server-side.
- [ ] Lint and type-check pass; Conventional Commit on a `feature/*` or `bugfix/*` branch.
