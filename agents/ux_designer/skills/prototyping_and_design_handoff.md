# Prototyping and Design Handoff

Choose prototype fidelity by the question you are answering, then deliver an implementation-ready handoff so engineering builds the right thing without guessing. Match the cheapest fidelity to each question — low fidelity to validate a flow, high fidelity to validate visual design and run a realistic usability test — and hand the frontend agent a single, versioned, fully specified package that it can build against without inventing missing decisions.

## Match fidelity to the question, not to the calendar

A prototype is an instrument for answering one question. Polishing pixels on a flow nobody has validated burns the budget twice — once to build the polish, again to throw it away when the flow changes. Climb the fidelity ladder only as far as the open question requires:

- **Paper sketch / whiteboard.** Answers "does this concept and rough layout make sense at all?" Minutes of effort, disposable, used to compare several directions before any of them earns a screen. Stop here while the idea is still contested.
- **Wireframe (grayscale, no brand).** Answers "is the information architecture and the flow right?" Tests navigation, content hierarchy, and step order with no visual styling to distract reviewers or imply false precision. This is where flow problems are cheapest to fix. Validate the flow here before any color, type, or imagery is applied.
- **High-fidelity mockup (static).** Answers "is the visual design, hierarchy, and content right on a real screen?" Real type scale, color, spacing, and copy, but no interaction. This is the surface the redlines and specifications are cut from.
- **Interactive prototype.** Answers "can a real user complete the task, and where do they hesitate or fail?" Clickable flows with realistic states and transitions, suitable for moderated and unmoderated usability tests. Only worth the build cost once the flow has survived wireframe review, because a usability test on an unvalidated flow measures the wrong thing.

The rule that saves the most time: never raise fidelity to answer a question a lower fidelity already answers. If the flow is still in dispute, a high-fidelity mockup is premature and its polish is at risk. Record which question each prototype was built to answer, so a reviewer can tell whether the fidelity was justified.

## Prototyping and component organization in Figma

Build the file so the handoff is a by-product of how you worked, not a separate export chore:

- **Pages by purpose:** a `Cover` page with status and version, an `Explorations` page for discarded directions (kept, not deleted, so the rationale survives), a `Flows` page with the canonical screens, and a `Prototype` page that wires them.
- **Components, not copies.** Every repeated element is a component with named **variants** (state and type) and **properties** (boolean toggles, text, instance swaps). A button is one component with `variant=primary|secondary|ghost` and `state=default|hover|focus|active|disabled|loading`, not eight detached frames. Detached instances are the most common source of drift between the design and the build.
- **Auto layout and constraints** on every component so spacing and resize behavior are explicit and measurable, not eyeballed. The frontend agent reads padding and gap from auto layout; a hand-nudged frame gives it nothing to measure.
- **Figma variables** carry the token values (color, spacing, radius, type) and bind to the components, so a token change propagates through the file. Variable structure, the token tiers (primitive, semantic, component), and the DTCG export are defined in the sibling skill `design_systems_and_tokens.md`; this skill consumes that structure and does not redefine it.
- **Naming is an interface.** Layer, component, and variant names are read by the engineer and by code-generation tooling, so name them as the UI concept (`card/header/title`), never `Frame 217`.

## A complete handoff package

The package is complete when the frontend agent can build the screen without asking a clarifying question or guessing a value. Anything they would have to invent is a hole in the spec. A complete package contains:

- **Annotated specifications and redlines.** Spacing, sizing, and alignment measured against the grid, in the same unit the build uses (px or rem). Specify **every interface state**, not just the happy path: default, hover, focus, active, disabled, loading, empty, error, and the long-content / overflow case. A spec that shows only the populated state guarantees the empty and error states get improvised in code.
- **Design tokens in DTCG format.** The tokens the frontend agent consumes, exported in the DTCG (Design Tokens Community Group) JSON format per `design_systems_and_tokens.md`. Hand over token references (`color.action.primary`), never raw hex in the redlines, so the build binds to the system and a later token change does not silently desynchronize from the design.
- **Component specifications.** Each component with its full variant matrix and states, its properties, the tokens it consumes, and its responsive behavior (what reflows, what wraps, what truncates at each breakpoint). Note which existing system component this maps to so the engineer reuses rather than rebuilds.
- **Interaction and motion notes.** Trigger, the property animated, duration and easing as concrete values (for example 200 ms, `ease-out`), and the reduced-motion fallback. "Make it smooth" is not a spec; an engineer cannot build a feeling.
- **Accessibility annotations.** Focus order through the screen, the accessible name for every control (especially icon-only buttons), the foreground/background **contrast pairs** with their computed ratios (at least 4.5:1 for normal text, 3:1 for large text and for UI component and graphic boundaries), and target sizes (interactive targets at least 24x24 CSS px per WCAG 2.2 SC 2.5.8, or with adequate spacing). These belong in the spec because they are design decisions; the frontend agent implements them but does not get to choose the focus order.
- **Final content and copy.** Real, signed-off strings — labels, headings, empty-state and error messages, microcopy — not lorem ipsum. Placeholder copy ships to production more often than anyone admits, and length differences between placeholder and real copy break layouts late.

## Versioning and a single source of truth

There is exactly one frame the build tracks, and it is unambiguous which one. Without this, an engineer builds last week's layout and the discrepancy is discovered in design QA, after the cost is sunk.

- Tag the handed-off version explicitly (Figma branch merged to main, or a dated, named version in version history), and put that version identifier in the handoff contract. The contract points at a version, not a live "latest" link that has already moved on.
- Changes after handoff go through an explicit change note appended to the contract, with the changed frames called out — never a silent edit to the same frame the engineer is already building from. A silent edit is indistinguishable from no change, so it never gets built.
- The contract is the seam: the frontend agent treats the referenced version as frozen for the slice it is building and pulls a new version only when a change note tells it to.

## Design QA: review the build against the design

The build is not done because it compiles. Before sign-off, review the implemented UI against the specification and file specific, reproducible discrepancies. This review — the design-QA verdict — is owned by this agent; the frontend agent owns the fix.

- Compare the running UI to the spec state by state across breakpoints: spacing and sizing against the redlines, token usage (is it the token or a hardcoded near-miss?), every interface state, motion timing, and the accessibility annotations (tab order, accessible names, contrast as built, target sizes as built).
- File each discrepancy as a concrete defect: the element, the expected value from the spec, the observed value in the build, and a screenshot or frame reference. "Spacing looks off" is not actionable; "card padding is 12px, spec is `space.4` = 16px" is. Vague QA notes bounce back as questions and stall the slice.
- Separate a spec defect (the build diverges from the spec) from a spec gap (the spec did not cover this case). A gap is the designer's bug to fix in the spec and re-hand-off, not the engineer's to guess at.
- Sign off only when the open defects are resolved or explicitly accepted with a recorded reason. The verdict — pass, or pass-with-listed-exceptions, or fail — is the artifact, recorded in project memory so the release stage can see it.

## The handoff as a bounded contract

The handoff to the frontend agent is a bounded handoff contract, consistent with the project convention in `docs/solomon-workflow.md`: a compact summary plus pointers, recorded in project memory, so the receiving stage reads the contract first and opens the heavy artifacts (the Figma file, the token export) only through its pointers.

- Write the contract to `.solomon/handoffs/issue-<N>-ux_designer-to-frontend.md` using the project's contract template, then record it with `log_handoff(sender="ux_designer", recipient="frontend", contract_type="design_handoff", contract_path=..., status=...)`.
- Keep the contract short on purpose. It states what the design stage decided, the frozen version identifier, and the bounded input the frontend agent needs to start; the full detail lives in the linked Figma version, the DTCG token export, and the annotated specs. The contract carries pointers, not pasted redlines.
- The boundary is firm: this agent owns the specification and the design-QA verdict; the frontend agent owns the code that satisfies the spec. Implementation choices (framework, component internals, state management) are the frontend agent's call; the design contract constrains the observable result, not how it is built.

## Common pitfalls

- High-fidelity mockup built before the flow was validated at wireframe fidelity: the polish is at risk the moment the flow changes, so the effort is spent twice. Validate the flow at the cheapest fidelity first.
- A usability test run on an unvalidated flow: it measures reactions to the wrong design and produces confident, misleading findings. Settle the flow before testing the surface.
- Spec covers only the populated happy path: empty, loading, error, and overflow states get improvised in code and diverge across the app. Every interface state is part of the spec.
- Raw hex values in the redlines instead of token references: the build hardcodes them, drifts from the system, and a later token change silently desynchronizes. Spec token references, defer structure to `design_systems_and_tokens.md`.
- Detached Figma instances and hand-nudged spacing: there is nothing precise for the engineer to measure, so values get approximated. Components with variants and auto layout make the spec measurable.
- The contract links a live "latest" file instead of a frozen version: the engineer builds a moving target and the mismatch surfaces only in design QA. Pin a version identifier in the contract.
- Placeholder copy handed off as if final: real strings differ in length and break the layout late, and lorem ipsum reaches production. Final copy is part of the package.
- Design-QA notes written as impressions ("feels cramped") rather than measured discrepancies: they bounce back as questions and stall sign-off. State expected versus observed with a reference.
- The handoff dumps the whole Figma file into the contract instead of pointers: it defeats the bounded-context convention and overflows the next stage. Summary plus pointers, detail in the artifacts.

## Definition of done

- [ ] Each prototype records the question it was built to answer, and its fidelity is the cheapest that answers that question.
- [ ] The flow was validated at wireframe fidelity before any high-fidelity mockup or usability test was built on it.
- [ ] Every interface state (default, hover, focus, active, disabled, loading, empty, error, overflow) is specified, not only the happy path.
- [ ] Redlines use token references exported in DTCG format per `design_systems_and_tokens.md`; no raw hex or hardcoded spacing in the spec.
- [ ] Component specs include the full variant matrix, properties, consumed tokens, and responsive behavior, and map to existing system components where they exist.
- [ ] Interaction and motion notes give concrete duration, easing, and the reduced-motion fallback.
- [ ] Accessibility annotations cover focus order, accessible names, contrast pairs with ratios (>=4.5:1 normal text, >=3:1 large text and UI boundaries), and target sizes (>=24x24 CSS px or adequate spacing).
- [ ] Final, signed-off content and copy are in the package; no placeholder text.
- [ ] A single frozen version identifier is named in the contract, and post-handoff changes go through an explicit change note.
- [ ] The handoff contract is written to `.solomon/handoffs/issue-<N>-ux_designer-to-frontend.md` and recorded with `log_handoff`, as a summary plus pointers.
- [ ] Design QA compared the built UI to the spec state by state, discrepancies are filed as expected-versus-observed defects, and the verdict (pass / pass-with-exceptions / fail) is recorded in project memory before sign-off.
