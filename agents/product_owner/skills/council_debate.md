---
name: council-debate
description: Governs the opt-in adversarial council debate — a four-phase structured debate among existing solomon specialists (software_engineer, software_architect, security, peer_reviewer, and product_owner itself) that stress-tests a high-ambiguity idea or a contested epic-scoping decision, never a default step of idea capture or refinement. Use when a dilemma shows genuine multi-stakeholder tension — two comparably plausible framings, a scope dispute across specialists, or an explicit user request to stress-test a proposal — and the user has opted in from an enumerated menu.
---

# Council Debate

This skill runs an opt-in adversarial council: a structured, four-phase debate among a small dynamic roster of solomon's own specialist agents, convened only when a dilemma is genuinely contested and only after the user has chosen it from an enumerated menu. It exists to surface real disagreement before a costly-to-reverse product or scope decision ships, not to add ceremony to ordinary work. Every idea passes the socratic_elicitation gate; only a fraction of those — the ones where elicitation's single-reading criterion fails with real stakes, where specialists would plausibly disagree, or where the user names the trigger explicitly — earn a council session. Treat the opt-in boundary as load-bearing: a council wired into every `/solomon-idea` or `/solomon-refine` run stops being a stress test and starts being theater, and it burns the time budget on decisions nobody was actually contesting.

## When to convene the council

Convene only when at least one holds:

- Elicitation's single-reading criterion failed and the two readings carry materially different scope, cost, or risk — not just different wording.
- Scoping an epic where two or more specialists would reasonably stake out opposing positions (for example, the fastest delivery path and the most defensible architecture disagree).
- The user explicitly asks to stress-test a proposal, get a second opinion, or names the council directly ("stress-test this with the council").
- A decision is expensive to reverse once shipped (an epic-level commitment, a public API shape, a scope cut that forecloses a V2 direction) and the current framing has not been challenged by anyone outside product_owner.

Do not convene for a routine idea, a well-formed story, or a demand that already passed all six socratic_elicitation criteria cleanly. When in doubt, offer it as an enumerated option rather than deciding unilaterally — the calling workflow presents "run the council" and "proceed without it" as sibling choices, recommended option first, and proceeds only on the user's pick.

## Roster: mapped onto existing solomon agents

The council never invents a bespoke advisor persona. Every seat is a real solomon specialist, dispatched through the Agent tool by its existing subagent name, arguing from the stance its profile already encodes:

| Seat (archetype)     | Solomon agent       | Stance it argues from                                                          |
| --------------------- | -------------------- | -------------------------------------------------------------------------------- |
| pragmatic-engineer    | `software_engineer`  | delivery cost, implementation complexity, maintainability, the TDD path to ship |
| architect             | `software_architect` | long-term structure, coupling, the ADR-worthy trade-off, cost of reversal        |
| security-advocate     | `security`           | trust boundaries, STRIDE-derived risk, what a breach or misuse looks like        |
| product-mind          | `product_owner` (self) | user value, scope boundary, the measurable outcome, JTBD framing                |
| devil's-advocate      | `peer_reviewer`       | refute-first stress test, via its own `adversarial_verification` stance          |

`product_owner` is the only seat that is never dispatched externally: it plays product-mind and facilitates in the same pass, because it already owns problem framing under `product_discovery_and_jtbd`. There is no separate framing-challenge agent to invent — if the framing itself looks like the constraint, that challenge is product_owner's own job as facilitator, folded into its opening statement and into how it interrogates the other seats' Key Points. Do not create a "the-thinker" role; the roster above is closed.

Size the roster to the dilemma: 3 seats for a narrow or binary trade-off (product-mind plus the two specialists whose stances actually diverge), 4 for a multi-factor decision with two or three competing concerns, 5 for a broad dilemma touching delivery, architecture, security, and scope at once. Always add `peer_reviewer` as the fifth seat — or swap it in for a seat whose position looks settled — whenever the opening statements converge too fast or the user asked for stress-testing explicitly; a council that reaches consensus in one round has not been tested.

## Phase 1: Opening statements

Dispatch every selected seat through the Agent tool in a single message with one Agent call per seat (not as a `fork` — a fork inherits product_owner's own reasoning and would just echo the facilitator, defeating the stance separation). Each dispatched seat receives: the refined dilemma and its explicit constraints, the list of other seats in the session, and the instruction to deliver an opening statement of two to three paragraphs ending in a one-line **Key Point**. Render:

```markdown
## Opening Statements

### [Seat] — [Solomon agent]

[Opening statement]

**Key Point:** [one-line summary]
```

## Phase 2: Tensions and rebuttals

Read the openings and name 2-4 genuine tensions — a real tension has a Side A, a Side B, and stakes that matter to the decision, not a wording difference. For each tension, re-dispatch the opposing seats with a fixed prompt shape: steel-man the opponent's position in one or two sentences first, then rebut in one paragraph, then state explicitly whether the seat concedes, partially concedes, or holds firm, and why. Steel-manning is mandatory before the rebuttal in every round; a rebuttal that skips it is invalid and must be redispatched. Render:

```markdown
## Core Tensions

| Tension | Side A (Seat) | Side B (Seat) | Facilitator Note |
| ------- | -------------- | -------------- | ----------------- |

### Key Concessions

- **[Seat]** concedes to **[Seat]** on [point] because [reason]
- **[Seat]** holds firm on [point] because [reason]
```

## Phase 3: Position evolution

Track how each seat's position moved after the rebuttal rounds — a concession that is asserted but never shown moving anything is not evidence of a real debate:

```markdown
## Position Evolution

| Seat | Initial Position | Final Position | Changed? |
| ---- | ------------------ | ----------------- | -------- |

**Key Shifts:**
- [who changed and why]
```

## Phase 4: Synthesis — no false consensus

Produce the synthesis in this fixed order. Preserve live disagreement rather than collapsing it: a synthesis with zero unresolved tensions after a genuine debate is a sign the tensions were softened, not resolved.

```markdown
## Council Synthesis

### Points of Consensus
- ...

### Unresolved Tensions

| Tension | Position A | Position B | Trade-off |
| ------- | ---------- | ---------- | --------- |

### Dissenting View
[Named seat], [the position it still holds], [why it is preserved rather than overridden]

### Risk Mitigation
- ...
```

The **Recommended Path Forward never appears as a prose paragraph.** It resolves through solomon's enumerable-decisions rule: convert the live options that survived the debate — including the dissenting view, when it is a real contender and not a footnote — into an `AskUserQuestion` menu, recommended option first, mutually exclusive, with "Other" appended automatically. The synthesis's job is to produce the menu's options and their one-line trade-offs; the user's pick, not the facilitator's preference, is the decision of record. Log the pick with `save_decision`, naming the council's Unresolved Tensions and Dissenting View in the rationale so the record shows what was traded away.

## Extraction into the calling workflow

The council returns material, not a final artifact; the calling stage extracts it:

- The winning option's scope becomes the idea's Opportunity/JTBD refinement, or the issue's Scope section.
- Options not chosen become explicit V1 exclusions or the issue's Out of scope list.
- Risk Mitigation entries and the Dissenting View's concern feed the Riskiest assumption (idea) or the RAID Risks block (refine), each with an owner.
- The Unresolved Tensions table is appended to the issue body under a `Council Debate (opt-in)` heading for traceability, so a later reader sees what was contested and why the pick won.

## Failure handling

- A seat returns content that abandons its stance (agrees with everything, drops its archetype): redispatch once with an explicit reminder of its assigned stance.
- If the failure repeats, record it in the synthesis as a degraded seat and proceed with the remaining seats rather than stalling the session.
- If fewer than two real tensions emerge after Phase 2, say so: the dilemma was likely lower-stakes than the trigger suggested. Offer a two-option menu — proceed with the thin consensus, or stop and reconsider whether the council was the right call — instead of forcing a full synthesis over non-existent disagreement.

## Common pitfalls

- Wiring the council into every `/solomon-idea` or `/solomon-refine` run instead of behind an explicit opt-in menu: this is the one failure mode that defeats the whole design.
- Collapsing a real tension into false consensus so the synthesis reads cleaner — the Unresolved Tensions table and the named Dissenting View exist specifically to prevent this.
- Skipping the steel-man requirement and going straight to rebuttal: a rebuttal without a steel-man is an assertion, not a debate.
- Ending the synthesis with a prose "we recommend X" paragraph instead of an `AskUserQuestion` menu — this violates the enumerable-decisions rule as much as any other unenumerated choice would.
- Inventing a new advisor persona (a "the-thinker" agent or any seat with no corresponding solomon specialist) instead of mapping the roster onto `software_engineer`, `software_architect`, `security`, `peer_reviewer`, and `product_owner` itself.
- Dispatching seats via `fork` instead of the named specialist subagents: a fork carries product_owner's own reasoning into every seat and produces five voices that agree with the facilitator by construction.
- Skipping Phase 3 (Position Evolution): without it, a "concession" in the synthesis is unverifiable — nothing shows the position actually moved.

## Definition of done

- [ ] The council was offered as an enumerated option (recommended first, "Other" last) and run only after the user picked it — never triggered automatically.
- [ ] The roster (3-5 seats) maps entirely onto existing solomon agents; no invented persona appears anywhere in the transcript.
- [ ] Every opening statement closes with a one-line Key Point.
- [ ] Every rebuttal steel-manned the opposing seat first, then stated concede, partially concede, or hold firm explicitly.
- [ ] Position Evolution shows at least one seat's initial versus final position, with Changed marked Yes or No.
- [ ] The synthesis carries an Unresolved Tensions table and a named Dissenting View — a synthesis with neither is rejected.
- [ ] The Recommended Path Forward was resolved through an `AskUserQuestion` menu, never a prose recommendation.
- [ ] The pick was logged with `save_decision`, naming the tensions traded away in the rationale.
- [ ] Extraction wrote the winning scope, the exclusions, and the risk items back into the calling workflow's own artifact (idea body or issue body), not left stranded in the council transcript alone.
