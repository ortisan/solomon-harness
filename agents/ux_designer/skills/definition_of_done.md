# Definition Of Done

A design deliverable is done only when it is evidence-backed, complete across every state, accessible to WCAG 2.2 AA by design, expressed through the design system, and handed to the frontend agent as a bounded, implementation-ready specification. This is the gate every piece of design work passes before it leaves this agent; the topic skills hold the detailed checks, and this is the single bar a reviewer applies.

## Research and validation

- [ ] The design solves a stated user job, and any decision that changes user behavior is backed by research or a usability test with a pre-committed success threshold.
- [ ] Usability findings were rated by severity and the severity 3-4 issues are resolved or explicitly deferred with a reason.

## Information architecture and interaction

- [ ] The information architecture and navigation are validated (card sort or tree test) rather than agreed by internal consensus.
- [ ] Every interface state is designed: ideal, empty (first-use, no-results, cleared), loading, partial, error with recovery, and success.
- [ ] User flows cover the primary path and the failure and recovery paths.

## Visual design and system

- [ ] Visual hierarchy directs attention to the primary action, on a consistent type scale and spacing grid.
- [ ] All values come from design tokens in the DTCG format; there are no hardcoded one-off values.
- [ ] Components used are specified with their variants and interactive states.

## Accessibility

- [ ] Text contrast meets 4.5:1 (normal) and 3:1 (large), and non-text contrast meets 3:1, in every theme.
- [ ] Interactive targets meet the 24x24 CSS px minimum or the spacing exception, and a visible, non-obscured focus state is designed.
- [ ] No meaning is carried by color alone; the layout holds at 200% zoom and reflows to 320px.

## Handoff and memory

- [ ] The handoff package is complete: specs and redlines, the DTCG token file, component specs, interaction and motion notes, accessibility annotations, and final copy.
- [ ] The handoff to the frontend agent is recorded with `log_handoff` as a bounded contract, and design decisions are persisted with `save_decision` in project memory.
- [ ] A design-QA review of the built UI against the design is planned, and discrepancies are filed before sign-off.

## Conventions

- [ ] Work was done on a `feature/*` or `bugfix/*` branch and committed with Conventional Commits.
- [ ] No production framework code was written; the deliverable is a specification, and every cross-role dependency is named with its owner.
