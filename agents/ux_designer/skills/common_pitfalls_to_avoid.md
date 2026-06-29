# Common Pitfalls To Avoid

Reject these recurring design failure modes before they reach a handoff; each is a specific mistake with a specific cost, and a reviewer should send the work back when one appears. This skill is the cross-cutting checklist that complements the failure lists inside each topic skill.

## Process and evidence

- Designing from opinion instead of evidence: a decision that changes user behavior shipped without a usability test or research backing it is a guess wearing a mockup. Tie it to evidence or mark it as an assumption to test.
- Skipping the riskiest-assumption test and polishing pixels first: high-fidelity work on an unvalidated flow wastes effort that a low-fidelity prototype would have saved. Validate the flow before the finish.
- Treating a stakeholder feature request as a requirement: it is an untested solution to an unstated job. Reframe it as the job and the problem, which the product_owner owns, before designing.

## The design itself

- Designing only the populated happy path: the empty, loading, partial, and error states are where real use breaks, and omitting them pushes invented behavior onto the engineer.
- Conveying meaning by color alone: it fails color-blind users and WCAG SC 1.4.1. Pair color with text or an icon.
- Choosing colors and type without checking contrast until handoff: a failing pair forces a visual rework instead of a token change. Check contrast when the value is chosen.
- Inconsistent components and one-off values that bypass tokens: every divergence erodes the system and multiplies maintenance.
- Inventing navigation labels from internal jargon: users search with their words, not the org chart's.

## Accessibility and handoff

- Deferring accessibility to the frontend agent: contrast, target size, and focus are design decisions; moving them downstream turns a cheap fix into an expensive one.
- A focus state left undesigned while the hover state is polished: keyboard users get no visible cue.
- Handing off a frame with no states, tokens, annotations, or final copy: the build drifts from the design because the engineer fills gaps by guessing.
- No design QA after build: without reviewing the implemented UI against the design, drift ships silently.

## Role boundary

- Writing production framework code or dictating the stack: it oversteps the frontend agent and makes this agent accountable for outcomes it does not control. Hand a specification instead.
- Claiming indexability, authentication, or test-automation work: those belong to seo, auth_engineer/security, and qa respectively. Name the dependency and its owner.

## Definition of done

- [ ] No decision that changes user behavior rests on opinion alone; each is backed by evidence or flagged as an assumption.
- [ ] All interface states are designed, not just the populated one.
- [ ] No meaning is carried by color alone and contrast was checked when values were chosen.
- [ ] Components and values come from the design system and its tokens, with no one-off bypasses.
- [ ] Accessibility was decided in the design and annotated for the handoff.
- [ ] The handoff is complete (states, tokens, specs, annotations, copy) and design QA is planned against the build.
- [ ] No production code was written and every cross-role dependency is named with its owner.
