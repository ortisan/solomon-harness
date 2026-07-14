---
name: prioritization
description: Governs choosing and applying a named, repeatable prioritization method - MoSCoW for release scope, RICE for backlog ranking, WSJF for delay-sensitive sequencing, Kano for obligations versus delighters - with numeric inputs shown. Use when scoping a release or ranking the backlog.
---

# Backlog Prioritization

Prioritize with a named, repeatable method and show the numbers, never by opinion volume or the loudest stakeholder. The method you pick depends on the question: MoSCoW answers "what is in this release," RICE answers "what ranks highest in the backlog," WSJF answers "what do we sequence first when delay costs money," and Kano answers "which features are obligations versus delighters." Anchor every result to the success metric so a high score that moves nothing gets challenged.

## Choose the method by the decision you are making

- MoSCoW for release commitment: Must (the release is blocked without it), Should (important, not blocking), Could (nice if it is cheap), Won't (explicitly deferred this cycle, recorded so it is not silently dropped). Keep Must under roughly 60 percent of capacity so Should and Could absorb the estimate misses, scope creep, and incidents that always arrive.
- RICE for backlog ranking: score = (Reach x Impact x Confidence) / Effort. Reach is users (or events) per time period, Impact is a fixed scale (3 massive, 2 high, 1 medium, 0.5 low, 0.25 minimal), Confidence is a percentage that discounts thin evidence, and Effort is person-months. Pick one effort unit and hold it constant across the whole backlog, otherwise scores are not comparable. Always write the four inputs, not just the final number.
- WSJF for sequencing time-sensitive work: WSJF = Cost of Delay / Job Size. Cost of Delay (SAFe) sums user/business value, time criticality, and risk-reduction or opportunity-enablement. Use it where delay materially changes value: deadlines, regulatory dates, market windows, contract penalties.
- Kano to classify features as basic (expected, their absence angers users), performance (more is linearly better), or delighter (unexpected upside). Fund the basic must-haves before novelty; a missing basic sinks satisfaction no matter how many delighters ship.

## Worked RICE ranking

One quarter of demand, effort measured in person-months for the whole backlog. Confidence discounts a feature whose Impact is a guess.

| Feature | Reach (users/qtr) | Impact | Confidence | Effort (pm) | Score |
|---|---|---|---|---|---|
| CSV export of reports | 2000 | 1 (medium) | 80% | 2 | (2000 x 1 x 0.8) / 2 = **800** |
| Enterprise SAML SSO | 300 | 2 (high) | 100% | 3 | (300 x 2 x 1.0) / 3 = **200** |
| Dark mode | 5000 | 0.5 (low) | 50% | 1 | (5000 x 0.5 x 0.5) / 1 = **1250** |

Rank by score: Dark mode (1250) > CSV export (800) > SSO (200). The surprise is the point of RICE — it forces the dark-mode advocate and the SSO advocate to argue with the same inputs. Then sanity-check against strategy: if the quarter's metric is enterprise expansion revenue, SSO's low RICE score is a signal to revisit its Impact and Reach (a few high-value accounts), not to bury it. RICE ranks; strategy decides which ranking to trust.

## Worked MoSCoW capacity allocation

A release with 40 person-days of net capacity. Sum the estimates per bucket and check the Must ceiling before committing.

| Bucket | Items | Days | Share |
|---|---|---|---|
| Must | Checkout, payment capture, receipt email | 22 | 55% |
| Should | Saved addresses, order history | 12 | 30% |
| Could | Gift-message field | 6 | 15% |
| Won't (this cycle) | Multi-currency, loyalty points | 0 | deferred, logged |

Must is 22 of 40 days (55 percent), under the 60 percent ceiling, leaving 18 days of Should/Could to flex when an estimate slips. If Must had landed at 30 days (75 percent), the release has no buffer: either cut a Must to a Should or move the date, because a 75-percent Must plan ships late or broken.

## Worked WSJF sequencing

Relative Fibonacci scoring; WSJF = (value + time-criticality + risk/opportunity) / job size.

| Job | Value | Time crit. | Risk/opp | CoD | Size | WSJF |
|---|---|---|---|---|---|---|
| Fix tax-rate bug (regulatory) | 8 | 13 | 5 | 26 | 5 | **5.2** |
| Add product filter | 5 | 3 | 2 | 10 | 2 | **5.0** |
| Re-platform search | 13 | 8 | 8 | 29 | 13 | **2.2** |

Sequence: tax-rate fix (5.2) > filter (5.0) > re-platform (2.2). The largest, highest-value job (re-platform) goes last because its job size dilutes its high Cost of Delay — WSJF deliberately favors small, urgent work that unblocks value sooner.

## Common pitfalls

- Reporting only the RICE/WSJF score without the inputs: the number is unauditable and cannot be challenged or recomputed when evidence changes. Reject scores with no Reach/Impact/Confidence/Effort shown.
- Mixing effort units across the backlog (story points here, person-months there): scores stop being comparable, so the ranking is meaningless.
- Must bucket over ~60 percent of capacity: there is no buffer, so the release ships late, incomplete, or with quality cut. Treat it as an unfunded plan.
- Confidence pinned at 100 percent on a feature with no evidence: it inflates the score. Confidence is where unvalidated assumptions get their discount.
- WSJF applied to work with no time sensitivity: Cost of Delay is flat, so the method adds nothing over RICE. Use it only where delay changes value.
- A high-scoring item that moves no success metric and no guardrail: the score is a local optimum disconnected from strategy. Make the advocate justify its place in the release.
- Won't-bucket items deleted rather than recorded: they resurface as "why didn't we do this" later. Log them as explicitly deferred.

## Definition of done

- [ ] The prioritization method is named (MoSCoW / RICE / WSJF / Kano) and fits the decision being made.
- [ ] For RICE, all four inputs (Reach, Impact, Confidence, Effort) are written per item, in one consistent effort unit, with the score shown.
- [ ] For MoSCoW, the Must bucket is under ~60 percent of measured capacity, and Won't items are recorded as deferred, not deleted.
- [ ] For WSJF, Cost of Delay components and Job Size are shown, and the method is only used where delay changes value.
- [ ] Each prioritized item is tied to the primary success metric or a guardrail, or its inclusion is explicitly justified.
- [ ] Surprising rankings are sanity-checked against product strategy before they are committed.
- [ ] The ranking is recorded in project memory so the next session sees the decision and its inputs.
