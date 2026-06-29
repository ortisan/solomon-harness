# User Research and Usability Testing

Decide what to design by studying how real users behave, and validate a design by watching people attempt real tasks with it, always weighting observed behavior over stated opinion. Pick the method from the question, pre-commit a pass/fail threshold and a minimum sample before the first session, and report findings on an evidence ladder so a confident claim from weak evidence gets challenged.

## Choose the method by the question

- Generative interview when the question is "what problem, in what context, with what current workaround." Run it with Mom Test discipline: ask about concrete past episodes, never pitch the idea. Bad question (predicts nothing): "Would you use a feature that auto-categorizes receipts?" Good question (recovers behavior): "Walk me through the last time you sorted your receipts. What did you do, what did it cost you in time, and what did you reach for instead?" Talk less than 30 percent of the session; the participant should be narrating their own past.
- Evaluative usability test when the question is "can a user accomplish this task with this design." Give a realistic goal-scenario and watch; do not ask whether they like it. Likeability is not usability.
- Quantitative benchmark when the question is "what is the completion rate / how does design A compare to design B." This is a measurement, not problem discovery, and it needs a real sample (below).

The split with product_owner: the PO owns problem framing, scope, and primary JTBD discovery. This agent runs research to inform design decisions and owns the design-validation evidence (did the design let users do the job) and the usability outcomes (success rate, errors, SUS). When generative interviews overlap, coordinate recruiting and share findings rather than running two parallel studies on the same users.

## Moderated vs unmoderated

| | Moderated | Unmoderated |
|---|---|---|
| Best for | Generative, complex flows, the "why," follow-up probing | Well-defined tasks, scale, benchmark metrics |
| Typical n | 5-8 sessions, 45-60 min each | 15-50+ participants |
| Strength | Real-time probing of unexpected behavior | Speed, lower cost, natural environment, no scheduling |
| Weakness | Scheduling cost, facilitator can bias | No probing; misunderstood tasks and satisficing go undetected |

Use moderated when you do not yet know what you will see and need to ask "why did you do that." Use unmoderated when the task is unambiguous and you need numbers or many participants. Never read a single unmoderated number as truth without watching at least a few session recordings to confirm participants understood the task.

## Sample size: 5 finds problems, 20 measures rates

For qualitative problem discovery, the expected share of usability problems found is 1 − (1 − L)^n, with L ≈ 0.31 problems detected per user. Five users surface ~85 percent; reaching ~100 percent needs ~15. Do not spend 15 in one round — run three iterative rounds of 5, fixing between rounds, because each fix changes what the next users hit.

A qualitative sample cannot produce a defensible rate. With n=5, a binary completion rate carries a 95 percent confidence interval near ±40 points, so "80 percent succeeded" means "somewhere between 40 and 100 percent." To report a rate or compare two designs you need a benchmark sample, roughly n≥20 per cell for a usable interval (around ±15 points) and more to detect a small difference. State the sample basis next to every percentage.

## Think-aloud and timing

Concurrent think-aloud (narrate while doing) is the default for finding problems: it exposes the mental model and the moment of confusion. But verbalizing slows people 20-40 percent and alters behavior, so time-on-task collected during concurrent think-aloud is invalid. When time-on-task is a target metric, use retrospective think-aloud: the user does the task silently while you record timing, then narrates against the replay. Pick one and state which, because the choice decides whether your timing numbers are usable.

## Task scenarios and success metrics

Write each task as a realistic goal with a trigger and context, never as instructions that name the UI element. "You just got paid and want to move 200 to savings before rent" tests discoverability; "Tap the Transfer button, then Savings" tests nothing, because it telegraphs the path and inflates success. Define success, partial, and failure criteria before the session so no result is reclassified afterward.

Capture, per task:
- Task success rate: binary or with partial credit; the primary outcome.
- Error rate: errors per task opportunity; counts slips and wrong paths even on eventually-successful tasks.
- Time-on-task: only when not running concurrent think-aloud (see above).
- Single Ease Question (SEQ): one 1-7 rating right after each task; fast perceived-difficulty signal.

For perceived usability across the product, use the System Usability Scale (SUS): 10 items, scored 0-100. The benchmark mean is ~68 (the 50th percentile, not a "pass" — many ship below it); ~80+ is good (roughly top quartile); below ~51 is poor. SUS needs ~12-15 respondents for a stable mean and is a relative gauge over releases, not an absolute grade. For navigation-heavy flows, lostness L = sqrt[(N/S − 1)^2 + (R/N − 1)^2] under 0.4 is acceptable; above 0.5 flags a structural problem.

## Pre-commit the threshold and sample

Write the hypothesis, the target metric, the pass/fail threshold, and the minimum sample before recruiting. Without a pre-committed gate, every result is rationalized and the team ships the design it already preferred. Examples:
- Qualitative round: "Ship gate: ≥80 percent unassisted success on the checkout task across n=5; if below, redesign the step responsible for the majority of failures and re-run."
- Benchmark: "n=20, target completion ≥90 percent with the lower bound of the 95 percent CI ≥75 percent; SUS ≥70."

Record the gate where it cannot be quietly edited after results land.

## Synthesis

- Affinity mapping (KJ method): one observation per note, cluster bottom-up, label the emergent themes. Do it within 24-48 hours while sessions are fresh. Convergence is the bar: a behavior seen in ≥3 of 5 participants is a pattern; an n-of-1 is a hypothesis to watch, not a finding to fund.
- Journey map: stages, actions, thoughts, emotion, and pain points across the end-to-end experience, anchored to research data rather than assumption, to locate the moments that matter and the drop-off points.
- Jobs-to-be-done: frame the job as "When [situation], I want to [motivation], so I can [outcome]." The PO leads JTBD discovery; this agent reuses the job to write validation tasks and to define what "done the job" means as a success outcome.

## Evidence-strength ladder

Rank every claim, strongest first, and label which rung it sits on:
1. Behavior with real stakes — production analytics, an A/B test on live traffic, real money or data on the line.
2. Behavior in a realistic prototype task — a usability test on a clickable high-fidelity prototype.
3. Reported past behavior — concrete episodes recovered in a Mom Test interview.
4. Hypothetical claims — what someone says they would do in the future.
5. Stated opinion — survey preference, feature requests, "I would love it if."

A design decision backed by rung 5 must yield to one backed by rung 1 or 2. Stated preference predicts behavior poorly, so a feature request never outranks a watched task.

## Common pitfalls

- Pitching or asking about the future in interviews ("Would you use...?"): elicits polite agreement, not evidence. Reject any question about the idea or the future; ask about a specific past episode.
- Measuring time-on-task during concurrent think-aloud: verbalization inflates time 20-40 percent, so the number is invalid. Drop the metric or switch to retrospective think-aloud.
- Reporting a completion-rate percentage from n=5: the interval is roughly ±40 points, so the rate is meaningless. n=5 finds problems; it does not measure rates.
- Task wording that names the button: it reveals the path, inflates success, and hides the discoverability problem under test.
- No pre-committed threshold or sample: results get rationalized after the fact and the team ships its prior preference. Set the gate before session one.
- Treating one participant's complaint as a finding: n-of-1 is noise until it converges (≥3 of N). Acting on it pollutes the backlog.
- Ranking survey or feature-request opinion above observed behavior: stated preference is the weakest rung; placing it above watched behavior inverts the evidence ladder.
- Facilitator rescuing a stuck user: the stuck moment is the finding. Stay silent within ethical limits; help erases the signal you came for.
- Recruiting colleagues or power users as stand-ins: they carry the jargon and the intended mental model, so they pass tasks real users fail, producing false confidence.

## Definition of done

- [ ] Research question stated, with the method chosen to fit it (generative vs evaluative; moderated vs unmoderated) and the reason recorded.
- [ ] Sample size justified: ~5 per round for qualitative problem discovery, n≥20 for any rate, benchmark, or comparison claim.
- [ ] Pass/fail threshold, target metric, and minimum sample pre-committed in writing before the first session.
- [ ] Task scenarios written as realistic goals that do not name UI elements; success, partial, and failure criteria defined up front.
- [ ] Metrics captured correctly: success rate and error rate always; time-on-task only when not using concurrent think-aloud; SEQ per task; SUS for perceived usability with the benchmark cited (~68 average, ~80+ good).
- [ ] Findings synthesized via affinity map or journey map, with convergence noted (seen in ≥3 of N) and ranked by severity.
- [ ] Every design decision traces to a labeled rung on the evidence ladder, and behavior outweighs opinion where they conflict.
- [ ] Boundary respected: problem and JTBD discovery coordinated with product_owner; this agent reports design-validation evidence and usability outcomes.
- [ ] Results and the resulting decision recorded in project memory so the next session inherits the evidence.
