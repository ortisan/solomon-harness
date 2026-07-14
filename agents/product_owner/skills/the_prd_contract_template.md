---
name: the-prd-contract-template
description: Defines the ten mandatory PRD sections from problem statement through rollout and acceptance, the Definition of Ready for a sprint-bound story, and the freeze protocol that assigns requirement IDs and seeds the RTM. Use when drafting, reviewing, or freezing a PRD.
---

# The PRD Contract Template

A PRD is a contract between product and engineering: it states the problem, the measurable bar for success, and the verifiable scope, so the team builds the right thing once and can prove it later. Treat every section below as mandatory; mark a section "N/A" with a one-line reason rather than deleting it, because a missing section reads as an unanswered question, not a settled one.

## The ten required sections

Every PRD you publish contains these sections in this order. Each carries a short rule and a worked fragment so the intent is unambiguous.

1. **Problem statement.** The user pain in one paragraph: who hurts, when, how often, and what it costs them. No solution language. *Worked:* "Returning shoppers abandon checkout when their saved card is expired. They hit a generic decline with no path to update the card, so 9 percent of repeat-purchase attempts fail and the user contacts support or leaves." If you cannot name the cost, you are not ready to write the rest.

2. **Goals and non-goals.** Three to five measurable goals, plus an explicit non-goals list so reviewers see what you deliberately excluded. *Worked goal:* "Let a shopper update an expired card inline during checkout without losing the cart." *Worked non-goal:* "Adding new payment methods (PayPal, Apple Pay) is out; this PRD only repairs the existing card path." The non-goals list is what stops scope creep in review.

3. **Success metrics.** One primary metric (the north star for this change) plus one to three guardrail metrics that must not regress. Each metric needs a baseline, a target, and a measurement window. *Worked:* "Checkout completion for repeat buyers 71 percent -> 78 percent within 4 weeks; guardrail: p95 checkout latency stays under 400 ms; guardrail: payment-fraud rate does not rise above its trailing-30-day mean." Numbers, not adjectives.

4. **Personas and context.** The specific user(s) and the trigger situation; link to research or prior decisions in project memory (`get_decision`, `get_memory`) so the PRD inherits known context instead of re-litigating it. *Worked:* "Persona: returning customer with one saved card, on mobile web, triggered when the saved card's expiry has passed since last purchase. See decision `DEC-checkout-pci-scope`."

5. **User stories.** The backlog for this PRD, one INVEST story per slice in the standard `As a / I want / so that` form (see `user_stories_invest`). Each story gets a stable `US-<NN>` ID here, because traceability links to it (see `requirements_traceability`).

6. **Acceptance criteria.** Per story, in Given-When-Then covering happy, boundary, and failure paths (see `acceptance_criteria_given_when_then`). Each scenario gets an `AC-<story>.<n>` ID. *Worked:* "AC-14.2 — Given a shopper with an expired saved card, When they enter a valid replacement card, Then the order completes and the new card is saved for next time."

7. **Scope boundaries.** An in-scope list, an out-of-scope list, and explicit assumptions and dependencies, each dependency with an owner (see `scope_boundaries`). *Worked dependency:* "Depends on the tokenization service exposing an update-card endpoint — owner: payments team, confirmed available in v2.3."

8. **Constraints and non-functional requirements.** Performance budgets, security, compliance, accessibility, and data retention, stated as numbers. *Worked:* "PCI-DSS SAQ-A: card data never touches our servers, only the tokenization iframe; inline update flow is WCAG 2.2 AA; the new card form responds within 200 ms p95."

9. **Open questions and risks.** Each with an owner and a needed-by date, so an open question is a tracked blocker, not a footnote. *Worked:* "Q: Do we re-run fraud scoring on the updated card? Owner: risk team. Needed by: sprint planning, 2026-07-05."

10. **Rollout and acceptance.** Release gating, the feature-flag plan, and the single sentence that defines "done shipped." *Worked:* "Ship behind flag `checkout_inline_card_update`, ramp 5 -> 25 -> 100 percent over 3 days watching the latency guardrail; done shipped = flag at 100 percent with completion metric trending to target and no guardrail regression."

## Deliverables and Definition of Ready

The PRD's output is a set of Ready stories, not prose. A story is **Ready** to be pulled into a sprint only when all of the following hold:

- It follows the user-story format and passes INVEST.
- It has Given-When-Then acceptance criteria covering happy, boundary, and failure paths.
- Dependencies and assumptions are listed with owners.
- Non-functional constraints that apply to it are stated with numbers.
- It is sized by engineering.

If a story is not Ready, it does not enter the sprint. This is non-negotiable and prevents mid-sprint thrash: an unsized story with vague criteria becomes a mid-sprint negotiation that derails the whole iteration. The Definition of Ready is the gate the `solomon-refine` workflow drives a backlog item through. Record the Ready transition so the board and memory agree on state, and so a later session can see which stories were accepted into the sprint and on what basis.

## Sizing, freezing, and recording the PRD

Keep the PRD to the smallest size that removes ambiguity. A 2-page PRD engineering can build beats a 20-page one they skim; length is a cost, not a virtue. Once stories and acceptance criteria are agreed, **freeze** the PRD: assign the `PRD-<AREA>-<NN>` requirement IDs, seed the Requirements Traceability Matrix from them (see `requirements_traceability`), and persist the decision with `save_decision` so any post-freeze change is an explicit, traceable scope change rather than a silent edit. *Worked freeze note:* "PRD-CHECKOUT frozen at 6 stories, 17 ACs; RTM seeded under memory key `rtm:PRD-CHECKOUT`; handed to QA via `log_handoff`." The freeze is what makes the contract enforceable: before it, the PRD is a draft; after it, every change costs a recorded decision.

## Common pitfalls

- Writing solution language in the problem statement ("add an inline form"), which biases the design before the pain is even agreed and hides whether the problem is worth solving.
- Goals without numbers or without a non-goals list, so review cannot tell success from activity and scope expands unchecked.
- A success metric with no baseline or window, making the launch unfalsifiable: you can never say whether it worked.
- Acceptance criteria that cover only the happy path, so boundary and failure behavior is decided ad hoc by whoever writes the code.
- Dependencies and open questions with no owner or date, which silently become the reason the sprint slips.
- Pulling a story into a sprint before it is Ready (unsized, vague criteria), guaranteeing mid-sprint renegotiation.
- Editing the PRD after freeze without a `save_decision`, desynchronizing it from the RTM and from what QA is testing.
- A 20-page PRD that restates obvious context; the team skims it and misses the three lines that actually constrain the build.

## Definition of done

- [ ] All ten sections are present and in order; any "N/A" carries a one-line reason.
- [ ] The problem statement names who, when, how often, and the cost, with no solution language.
- [ ] Three to five measurable goals and an explicit non-goals list are stated.
- [ ] One primary metric and one to three guardrails each have a baseline, target, and measurement window.
- [ ] Every story is INVEST-clean with a stable `US-<NN>` ID and Given-When-Then ACs (happy, boundary, failure), each with an `AC-<story>.<n>` ID.
- [ ] Scope boundaries, dependencies (with owners), and non-functional constraints (with numbers) are listed.
- [ ] Open questions and risks each have an owner and a needed-by date.
- [ ] Rollout, feature-flag plan, and the one-sentence "done shipped" definition are written.
- [ ] Every story entering the sprint meets the Definition of Ready (INVEST, GWT criteria, owned dependencies, numeric NFRs, engineering-sized).
- [ ] The PRD is frozen: `PRD-<AREA>-<NN>` IDs assigned, RTM seeded under `rtm:PRD-<name>`, and the freeze recorded with `save_decision`.
