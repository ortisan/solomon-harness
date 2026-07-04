# Frontend Definition of Done

The completion gate for every React and Angular change: what must hold before UI work is called done. The pitfalls below name the ways frontend work gets marked done while failing this checklist; verify against them before ticking any box.

## Common pitfalls

- Tests added after the component and asserting implementation details (CSS classes, internal state) — the tests-first box is unverifiable and the suite survives broken interactions.
- "TypeScript strict" claimed while `as` casts or `@ts-ignore` hide `any` inside public props — the contract line requires explicitly typed props/inputs, not a compiler silenced by force.
- Accessibility ticked from a mouse-only spot check — without a keyboard pass and a clean `axe`/jsx-a11y run, focus order, labels, and roles regress silently.
- Contrast verified in light theme only — the 4.5:1 and 3:1 thresholds must also hold after the dark-mode token swap, or the checkbox is half true.
- "No leaking subscriptions/effects" checked without a mount-unmount test asserting teardown — leaks reproduce over navigation, never in a single-render test.
- Numeric guards declared but untested — with no test feeding `NaN`, zero denominators, or short arrays, the guard clause is dead code the first bad API row will find.
- "Profiled for regressions" and "no layout shift" marked with no measurement attached — a Profiler capture, bundle diff, or CLS check is the evidence; assertion is not.

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
