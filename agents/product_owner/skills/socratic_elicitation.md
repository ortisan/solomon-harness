# Socratic Elicitation

Run a bounded Socratic elicitation before shaping any feature/story: evaluate the demand against the six readiness criteria, question only what is missing — at most 3 rounds of at most 4 questions, presented as enumerated options — and skip questioning entirely when the demand already passes all six. The gate exists to stop guessed intent from becoming an issue; it must never become an interrogation that stalls a well-formed request, and it never replaces the confirm-before-create step.

## The readiness checklist

A demand is ready when all six criteria hold. Judge each against the demand text as written, not against what you could plausibly infer:

1. **Problem** — the pain or trigger is stated. "Reviews keep missing scope drift" passes; "improve reviews" fails.
2. **Persona** — a real user type is identifiable. "An engineer filing work mid-sprint" passes; "the user" or an unstated subject fails.
3. **Outcome** — the observable change that means success is stated. "So refine stops re-deriving intent" passes; "make it better" fails.
4. **Boundary** — at least one scope limit or constraint appears. "Only the feature command, bugs later" passes; a demand with no edge at all fails.
5. **Single reading** — the text supports one interpretation. If two readings of comparable plausibility exist ("faster issues" — authoring speed or delivery speed?), the criterion fails and the question presents both readings as options.
6. **Job behind the solution** — a solution-phrased demand ("add a dropdown") also states the underlying need. A request is an untested solution to an unstated job; ask for the job, not a defense of the feature.

## The question ladder

One question archetype per criterion, always as enumerated options (2-4 plausible answers, recommended first; the host adds "Other" automatically):

- Problem: "What breaks or hurts today without this?" — options drawn from the likeliest pains in context.
- Persona: "Who hits this first?" — options are the real user types of this project, never generic roles.
- Outcome: "What would you observe when this works?" — options are measurable or at least checkable states.
- Boundary: "What is explicitly out for the first slice?" — options propose concrete exclusions.
- Single reading: state both interpretations verbatim as the options; do not pick one silently.
- Job: "If we could not build <the named solution>, what need would still exist?" — options are candidate jobs-to-be-done.

Derive options from the project context (memory, open issues, the codebase) so each is genuinely plausible; a question whose options are filler pushes the user to "Other" and wastes the round.

## Bounds and exit conditions

- At most 4 questions per round (the AskUserQuestion cap), one per failed criterion, only for failed criteria. Never re-ask a criterion the demand or a prior answer already satisfied.
- At most 3 rounds, then shape with what you have. A criterion still unanswered after the bounds is recorded, not chased.
- An empty demand enters at round 1 with the job-to-be-done question first, because the job usually answers problem and outcome in the same breath.
- Decline is an exit, not an obstacle: when the user answers "Other" with the equivalent of "just file it", stop immediately and record every unanswered criterion under an `Assumptions (unelicited)` heading in the issue body.
- Non-interactive runs never block: ask nothing, print `Elicitation: skipped (non-interactive)`, and record unmet criteria as assumptions exactly as in the decline path.
- A demand that passes all six carries `Elicitation: skipped — all 6 readiness criteria met` in the issue body, so a skipped gate is auditable, not invisible.

## Folding answers into the story

Every elicited answer lands in a template field, never in a side note: Problem feeds the problem statement; Persona and Outcome feed the user story ("As a <persona>, I want <capability> so that <outcome>"); Boundary feeds Scope and Out of scope; Single-reading resolutions rewrite the demand sentence itself; the Job reframes a solution-shaped demand per product_discovery_and_jtbd. The elicitation line (skipped or ran, and which criteria failed) stays in the body so refine can see what was asked versus assumed.

## Common pitfalls

- Re-asking a criterion the demand already satisfies: it signals the checklist was not actually evaluated, and it burns the round budget. Evaluate first, then ask only the gaps.
- Open prose questions ("Can you tell me more?"): they violate the enumerable-decisions rule and disperse the user's focus. Every question carries 2-4 concrete options.
- Pitching a solution inside a question ("Should we add a dropdown for this?"): it contaminates the answer (Mom Test discipline — ask about the need and past pain, never pitch).
- Unbounded interrogation: a fourth round, or five questions in a round, is a defect even if gaps remain. Record assumptions and move on.
- Treating a decline as a blocker: the user saying "just file it" is an answered decision. Stop, record `Assumptions (unelicited)`, and proceed to the confirm step.
- Silently absorbing an ambiguous reading: when two interpretations exist, choosing one without presenting both fabricates intent — the exact failure the gate exists to prevent.
- Dropping the trace line on the skip path: an unlogged skip makes the gate unauditable and indistinguishable from the gate not running.
- Using the gate to weaken outward-action safety: elicitation changes how the demand is understood; the confirm-before-create approval stays exactly as it is.

## Definition of done

- [ ] The six criteria were each evaluated against the demand text before any question was asked.
- [ ] Questions were asked only for failed criteria, one per criterion, as enumerated options with a recommended first choice.
- [ ] The bounds held: at most 3 rounds, at most 4 questions per round, and no re-asked criterion.
- [ ] The issue body carries the elicitation trace: the skip line, or the ran line naming the failed criteria.
- [ ] Declined or unreachable answers are recorded under `Assumptions (unelicited)` in the issue body.
- [ ] Non-interactive runs asked nothing and printed `Elicitation: skipped (non-interactive)`.
- [ ] Every elicited answer is folded into a template field (problem statement, user story, scope), not left as an aside.
- [ ] The confirm-before-create step ran unchanged after the gate.
