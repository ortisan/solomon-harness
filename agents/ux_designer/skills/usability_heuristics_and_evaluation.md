# Usability Heuristics and Heuristic Evaluation

Evaluate an interface against Jakob Nielsen's 10 usability heuristics (1994, still the field baseline) and convert the findings into a severity-ranked fix list, using 3-5 independent evaluators instead of a single opinion. The output is a design-time findings report and a fix priority; implementation belongs to the frontend agent and automated test suites belong to the qa agent.

## The 10 heuristics, with a violation each

Inspect every screen and flow against all ten. Each finding names the heuristic it breaks so reviewers can group and compare across sessions.

1. **Visibility of system status** — keep users informed about what is happening through timely feedback. Violation: a "Submit" button that shows no spinner or confirmation, so the user clicks three times and creates duplicate orders.
2. **Match between system and the real world** — speak the users' language with familiar words, phrases, and conventions, not internal jargon. Violation: an error reading "Exception 0x80004005" instead of "We could not save your file because the disk is full."
3. **User control and freedom** — provide a clearly marked emergency exit (undo and redo) when users pick something by mistake. Violation: a multi-step wizard with no Back button, forcing a full restart after a wrong selection on step 2.
4. **Consistency and standards** — the same words, situations, and actions mean the same thing throughout, and platform conventions are honored. Violation: "Delete," "Remove," and "Trash" used interchangeably for the identical action across three screens.
5. **Error prevention** — eliminate error-prone conditions or confirm before committing, which beats even a good error message. Violation: a date field that accepts "31/02/2026" and only fails server-side, where a constrained date picker would have blocked it.
6. **Recognition rather than recall** — make objects, actions, and options visible so users need not remember information from one part of the interface to another. Violation: a transfer flow that shows an account number on screen 1 and asks the user to retype it from memory on screen 3.
7. **Flexibility and efficiency of use** — accelerators (shortcuts, saved defaults, bulk actions) speed expert users without obstructing novices. Violation: a data-entry tool with no keyboard shortcut and no bulk action, forcing power users to mouse-click each of 200 rows.
8. **Aesthetic and minimalist design** — interfaces hold no irrelevant or rarely needed information that competes with what matters. Violation: a checkout page with five promotional banners that push the "Pay now" button below the fold.
9. **Help users recognize, diagnose, and recover from errors** — error messages in plain language that state the problem and suggest a remedy. Violation: "Invalid input" with no indication of which of 12 fields is wrong or how to correct it.
10. **Help and documentation** — even a system that should need no explanation provides searchable, task-focused help anchored where the question arises. Violation: a tax-filing app whose only help is a 90-page PDF with no search and no link from the screen where the user is stuck.

## Run the inspection with 3-5 independent evaluators

A single evaluator finds roughly 35 percent of an interface's usability problems; 3-5 evaluators find roughly 75 percent. One person is not enough because every evaluator has blind spots and the overlap between any two is only partial — different evaluators catch different problems, so coverage climbs past 70 percent only when several independent passes are aggregated. Beyond about five, the marginal find rate falls while cost keeps rising, which is why 3-5 is the value point, not "as many as possible."

Each evaluator inspects the interface alone, with no discussion, before any findings are pooled. Independence is the whole mechanism: if evaluators talk first, they anchor on the first voice and their lists collapse toward one another, erasing the diversity that produces the 75 percent. Two passes per evaluator works well — a first pass to learn the flow and scope, a second to check each element against each of the ten heuristics. Evaluate against a defined set of representative tasks and scenarios, not a free roam, so high-traffic flows are guaranteed coverage instead of accidental coverage.

## Score every finding 0-4 and clear 3-4 first

Apply Nielsen's severity scale to each finding:

- **0** — not a usability problem at all.
- **1** — cosmetic; fix only if spare time allows.
- **2** — minor; low fix priority.
- **3** — major; high priority, fix soon.
- **4** — catastrophe; imperative to fix before release.

Severity is not one number from intuition. It combines three factors: **frequency** (how often the problem occurs), **impact** (how hard it is to overcome when it does occur), and **persistence** (whether users keep hitting it or learn to route around it after one encounter). A rare action that destroys unsaved data scores 4 on impact and persistence even though its frequency is low — frequency alone would have buried it. Have each evaluator rate severity independently and average, or let one analyst assign ratings at the debrief after seeing every finding.

Fix order follows severity, not discovery order: resolve all 3s and 4s before touching any 1s and 2s. A backlog of cosmetic 1s is never worth one unaddressed 4. Record deferred 1s and 2s explicitly rather than dropping them, so they are a decision and not an omission.

| Heuristic | Finding | Frequency | Impact | Severity | Order |
|---|---|---|---|---|---|
| Error prevention | Date field accepts impossible dates, fails only at server | High | High | 4 | Fix first |
| Visibility of status | No feedback on Submit; duplicate orders created | Med | High | 3 | Fix first |
| Aesthetic/minimalist | Pay button pushed below the fold by banners | High | Med | 3 | Fix first |
| Consistency | "Delete" vs "Remove" vs "Trash" for one action | Med | Low | 2 | Defer |
| Help/documentation | Help PDF not searchable | Low | Low | 1 | Defer |

## Use a cognitive walkthrough as the task-based complement

Where heuristic evaluation scans the whole interface broadly, a cognitive walkthrough drills one task deeply, which makes it the right tool for learnability and first-time use. Pick a target task, write down the correct action sequence, then at each step ask the four standard questions:

1. Will the user try to achieve the right effect at this step (do they have the right goal)?
2. Will the user notice that the correct action is available?
3. Will the user connect that action to the effect they want?
4. After acting, will the user see that progress was made toward the goal?

A "no" to any question at any step is a finding, scored on the same 0-4 scale. Run a walkthrough for each onboarding flow and each infrequent high-stakes task — account recovery, irreversible deletes, payment — where "will the user know what to do next" decides success more than raw aesthetics do.

## Heuristic evaluation versus user testing: pick the right tool

- **Expert inspection (heuristic evaluation and cognitive walkthrough)** is cheap, fast, needs no recruiting, and runs on mockups or prototypes before any code exists. Run it early and often. It surfaces many problems, including ones real users would hit but could not put into words. Its limit: experts *predict* problems, they do not *observe* behavior, so they over-report some issues and miss domain-specific ones tied to the users' actual mental model.
- **User testing** observes what real users actually do, catching domain and mental-model gaps that inspection cannot, and it settles disputes between evaluators about whether something is truly a problem. Nielsen's discount-usability work argues that a small panel of about five participants surfaces the large majority of problems in a single design. Its cost is recruiting and session time.

Sequence them: inspect first to clear the cheap, obvious 3s and 4s for free, then put the cleaned-up design in front of users so their session is not spent rediscovering problems an expert would have flagged. Use user testing specifically to confirm severity-3 and severity-4 findings before committing to a costly redesign, and to break evaluator disagreements. This skill produces the design-time findings and the fix priority that feed those decisions; it does not author or run automated test suites.

## Common pitfalls

- Relying on a single evaluator: coverage caps near 35 percent, so two-thirds of problems are missed while the report still reads as authoritative.
- Letting evaluators discuss before their independent passes: anchoring collapses their lists toward the first speaker and destroys the diversity that drives the 75 percent figure.
- Reporting findings with no severity: the fix list has no order, so teams spend effort on cosmetic 1s while a severity-4 ships.
- Scoring severity on frequency alone: a rare catastrophe such as data loss gets underrated; severity must combine frequency, impact, and persistence.
- Treating heuristic violations as confirmed facts about real users: experts predict rather than observe, so an unvalidated severity-3 claim should be checked by user testing before an expensive redesign.
- Free-roaming the interface instead of evaluating against representative tasks: coverage becomes accidental and the highest-traffic flows can go uninspected.
- Logging a violation without its heuristic, location, and a screenshot or repro: developers cannot act on it and it gets dropped from the handoff to the frontend agent.
- Inventing private heuristics or stretching the count: drift from the shared ten makes findings non-comparable across reviews; keep to the baseline unless an agreed domain set is added explicitly.

## Definition of done

- [ ] All 10 heuristics are inspected against a defined set of representative tasks, not a free roam.
- [ ] 3-5 independent evaluators ran the inspection alone before any joint debrief, and their findings are aggregated.
- [ ] Every finding records the heuristic violated, the location or step, a concrete description, and a repro or screenshot.
- [ ] Every finding carries a 0-4 severity that combines frequency, impact, and persistence.
- [ ] Severity 3 and 4 findings are listed as fix-first; severity 1 and 2 are recorded as explicitly deferred, not dropped.
- [ ] At least one cognitive walkthrough covers each first-use and high-stakes task, answering the four step questions.
- [ ] The report names which findings need user testing to confirm before a costly fix is committed.
- [ ] The findings report and fix priority are recorded in project memory and handed to the frontend agent for implementation; this skill writes no automated tests, which the qa agent owns.
