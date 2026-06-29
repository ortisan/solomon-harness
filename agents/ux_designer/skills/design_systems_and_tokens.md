# Design Systems And Design Tokens

Own the design system as the single source of truth for every design decision, and express those decisions as design tokens in the W3C DTCG format so the same values flow unchanged from design into the frontend agent's build. A design system is not a sticker sheet of components; it is the tiered set of decisions — foundations, tokens, components, patterns, and usage rules — that makes every new screen consistent and accessible by default.

## What a design system contains

- Foundations: the decided values for color, typography, spacing, sizing, elevation, radius, and motion.
- Tokens: those values named and structured so design and code reference the same source.
- Components: specified building blocks with their variants and states (default, hover, focus, active, disabled, loading, error).
- Patterns: how components combine to solve recurring problems (forms, tables, empty states, navigation).
- Usage guidance: when to use a component, when not to, and the accessibility rules baked in.

The system carries its own version (semantic versioning: a breaking token rename or component API change is a major bump). A component is only "in the system" when it has specified states, accessibility rules, and a token-only style definition.

## Token tiers

Structure tokens in three tiers so a brand change is one edit, not a thousand:

- Primitive (global) tokens: raw values, context-free. `color.blue.500 = #2563EB`, `space.4 = 16px`. Never referenced directly by a component.
- Semantic (alias) tokens: intent, referencing a primitive. `color.action.background = {color.blue.500}`, `color.text.default`, `space.inset.md`. Components reference these.
- Component tokens: the narrowest scope, referencing a semantic token. `button.primary.background = {color.action.background}`.

The reason for the indirection: theming, dark mode, and rebrands change the alias layer while components and primitives stay put. A component that hardcodes a primitive (or a hex value) breaks this and is rejected.

## The DTCG format

Express tokens in the Design Tokens Community Group format, which reached its first stable version (Design Tokens Format Module 2025.10) on 2025-10-28 and is supported by Figma, Style Dictionary, Tokens Studio, Penpot, Sketch, and others. The format is the vendor-neutral contract between this agent and the frontend agent.

- JSON interchange, with media type `application/design-tokens+json` and the `.tokens` or `.tokens.json` file extension.
- A token is an object with a `$value` and a `$type` (for example `color`, `dimension`, `fontFamily`, `duration`, `number`). Groups nest tokens; `$description` documents intent.
- Aliases reference another token by its dotted path in braces, for example `"$value": "{color.blue.500}"`.

```json
{
  "color": {
    "blue": { "500": { "$type": "color", "$value": "#2563EB" } },
    "action": {
      "background": { "$type": "color", "$value": "{color.blue.500}", "$description": "Primary action surface" }
    }
  },
  "space": { "4": { "$type": "dimension", "$value": "16px" } }
}
```

The frontend agent's token build (the `design_tokens_and_styling` skill) compiles this same file into CSS custom properties or platform code. This agent owns the token source; the frontend agent owns the compilation. Neither edits the other's side.

## Theming and modes

Model light/dark and brand variants by overriding the semantic tier only, keeping one set of components and primitives. State which token set is the default and how a mode is selected so the build is unambiguous. Verify that every theme still meets the contrast and non-text-contrast bars in `accessibility_by_design_wcag_22`; a dark theme that drops text contrast below 4.5:1 is not shippable.

## Governance and the handoff

- Naming is a fixed convention (category.concept.variant.state), documented once and enforced, because inconsistent token names are unusable downstream.
- A change to a shared token is a system change with a version bump and a changelog entry, not a local tweak.
- Hand the token file plus the component specs to the frontend agent as a bounded contract recorded with `log_handoff`; see `prototyping_and_design_handoff`.

## Common pitfalls

- Hardcoding hex values or pixel numbers in a component instead of referencing a semantic token: it defeats theming and makes a rebrand a manual sweep.
- A flat token set with no semantic tier: every theme or brand change edits hundreds of component values instead of one alias layer.
- Inventing a private token format instead of DTCG: it breaks the tool chain and the contract with the frontend agent, who can no longer import it.
- Components without specified states (focus, disabled, loading, error): the engineer invents them and consistency is lost.
- Treating the design system as a component gallery with no usage rules: teams misuse components and accessibility regresses screen by screen.
- Editing the frontend agent's compiled output instead of the token source: the two diverge and the next build overwrites the change.

## Definition of done

- [ ] Tokens are tiered primitive, semantic, and component, and components reference only semantic or component tokens, never raw values.
- [ ] Tokens are expressed in the DTCG format (`$value`/`$type`, alias references) and exportable as a `.tokens.json` file.
- [ ] Every component in the system specifies its variants and all interactive states.
- [ ] Each theme/mode overrides only the semantic tier and still meets the contrast bars in `accessibility_by_design_wcag_22`.
- [ ] Naming follows the documented convention, and any shared-token change carries a semantic version bump and a changelog entry.
- [ ] The token file and component specs are handed to the frontend agent as a bounded contract recorded with `log_handoff`.
