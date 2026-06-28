# Product Discovery and Jobs-to-be-Done

Run discovery as a continuous activity that decides what is worth building before delivery commits to how it is built. Anchor every initiative to a customer job and a target outcome, map the assumptions the idea depends on, and spend your evidence budget killing the riskiest ones first. Discovery produces validated problems and bets; the_prd_contract_template, user_stories_invest, and acceptance_criteria_given_when_then turn those bets into delivery. Keep the two tracks distinct so an unvalidated assumption never reaches a sprint as a committed requirement.

## Dual-track: separate discovery from delivery

Discovery and delivery run in parallel, not in sequence. Discovery answers "is this the right thing and will it work?"; delivery answers "build it correctly." The hand-off point is explicit: an opportunity moves from discovery to delivery only once its riskiest assumptions are validated and it carries a target outcome, acceptance criteria, and a scope boundary.

- Maintain two backlogs: a discovery backlog of opportunities and open questions, and a delivery backlog of validated, ready stories (see deliverables_and_definition_of_ready).
- Never let an idea skip the discovery track because a stakeholder is confident. Confidence is not evidence. Record the stakeholder's claim as an assumption to be tested.
- Time-box discovery per opportunity. Open-ended discovery is procrastination; a discovery spike has a question, a method, and a decision date.
- Record the discovery-to-delivery transition with `log_handoff` so the software_architect, qa, and engineering specialists inherit the evidence and the target outcome, not just a feature title.

## Jobs-to-be-Done

People hire a product to make progress in a situation. Frame demand around the job, not the demographic or the feature, so you do not over-fit to a persona and miss the real competitor (which is often a spreadsheet, a workaround, or doing nothing).

- Job statement format: "When <situation>, I want to <motivation>, so I can <expected outcome>." Keep it solution-free. "When a backtest finishes, I want to know if the result is trustworthy, so I can decide whether to allocate" is a job; "add a Sharpe badge" is a solution.
- Forces of progress: push of the current situation and pull of the new solution drive switching; habit and anxiety resist it. An idea that only adds pull/pull but ignores the anxiety of switching will under-adopt. Address all four.
- Outcome-Driven Innovation: decompose a job into desired outcomes expressed as "<direction> the <metric> it takes to <step>" (for example, "minimize the time it takes to detect data leakage in a feature set"). These outcome statements are measurable and become your opportunity candidates.
- Opportunity score (ODI): `importance + max(importance - satisfaction, 0)`, each rated 1-10 from customer surveys. Scores above 10-12 are underserved (high importance, low satisfaction) and are where to invest; scores below 10 are served or overserved. This is the input to prioritization, not a replacement for it.
- Distinguish the core functional job from related and emotional jobs. Build for the functional job; the emotional job ("look competent to my PM") shapes the experience, not the spec.

## Opportunity Solution Tree

Make the path from outcome to shipped solution visible and falsifiable. The tree (Teresa Torres) has four levels and forces you to compare opportunities before comparing solutions.

```
Outcome (one measurable business/product result)
  └─ Opportunity (an unmet need, pain, or desire — phrased as the customer's words)
       └─ Solution (a way to address that opportunity)
            └─ Assumption test / experiment (evidence for or against the solution)
```

- Exactly one target outcome per tree at a time. Multiple outcomes fragment focus and make prioritization incoherent.
- Opportunities are needs, never solutions. If a node names a feature, it belongs one level down. Sourcing opportunities from continuous interviews keeps the tree grounded in evidence rather than internal opinion.
- Generate at least two or three candidate solutions per chosen opportunity before committing. A single-solution branch means you stopped thinking, not that the solution is right.
- Persist the active tree and each weekly revision with `save_memory` so the rationale survives staff changes; record the chosen opportunity and the bet with `save_decision` (and revisit with `get_decision` when the outcome stalls).

## Outcome over output

Commit teams to outcomes (a change in customer or business behavior), not outputs (features shipped). A roadmap of features with dates is an output roadmap and hides whether anything improved.

- Pick a North Star outcome and express it as a measurable shift in a leading indicator, with a baseline and a target window: "raise the share of new strategies that pass out-of-sample validation from 40% to 60% within the quarter." A number with no baseline is a wish.
- Prefer leading indicators (activation, weekly active use of the core job, time-to-first-value) over lagging ones (revenue, churn) for steering, because you can still act on them inside the cycle.
- Tie the outcome to the quant/ML reality when relevant: for quant_trader and ml_engineer work the outcome may be a model-quality metric (target Sharpe, drawdown limit, leakage rate), not a usage metric. Let the owning specialist define the threshold; you own that an outcome exists and is measured.
- Track outcome movement against the baseline each cycle and log it with `save_session`; if the metric does not move after the bet ships, that is a discovery signal, not a delivery failure.

## Assumption and risk mapping

Every idea is a stack of assumptions. List them, then sort by risk so you test the ones that would sink the idea, not the ones that are comfortable to test.

- Classify each assumption by risk category: desirability (do they want it?), viability (does it work for the business?), feasibility (can we build it? — confirm with the software_architect and engineers), usability (can they use it?), and ethical/compliance (should we? — route to the security and auth_engineer specialists where relevant).
- Assumption map (2x2): plot each assumption on importance (how much the idea depends on it) against evidence (how much we already know). The top-left quadrant — high importance, low evidence — is the riskiest-assumption zone and sets the test order.
- A "leap-of-faith" assumption is one where, if false, the whole idea fails. There is usually one to three of them. Name them explicitly; everything else can wait.
- Log a validated problem or a falsified assumption as a tracked item with `log_issue`, and review open discovery questions with `get_open_issues` so nothing important stays unexamined.

## Validating the riskiest assumption first

Test the smallest, riskiest thing with the cheapest method that produces decisive evidence. The Riskiest Assumption Test (RAT) precedes any MVP: do not build a thin product to learn what a prototype, interview, or fake-door could have told you in a day.

- Match method to assumption. Desirability: customer interviews (Mom Test discipline — ask about past behavior, never pitch), fake-door/landing-page demand tests, Wizard-of-Oz. Usability: clickable prototype tests. Feasibility: technical spike. Viability: pricing/willingness-to-pay tests.
- Evidence strength ladder, weakest to strongest: opinions/surveys < what people say in interviews < what people do in a prototype < what people do with real stakes (paid, signed up, used). Weight conclusions by where on the ladder the evidence sits.
- Define the test before running it: the assumption, the metric, the pass/fail threshold, the minimum sample, and the decision (persevere, pivot, or kill). A test with no pre-committed threshold always "passes."
- Set sample expectations honestly. Five users surface roughly 80% of usability problems; demand and pricing tests need enough traffic for a stable rate, not five clicks. Interview continuously — a weekly cadence of one to three interviews beats a quarterly batch — and store evidence snapshots with `save_memory`.
- Convert a validated bet into delivery: define the target outcome and constraints, then hand to delivery via the_prd_contract_template, encoding_other_specialists_requirements_into_acceptance_criteria, and `log_handoff`. Record a `create_milestone` for the outcome so progress is tracked against the result, not the feature list.

## Common pitfalls

- Treating a feature request as a validated requirement. A request is an untested solution to an unstated job; reframe it as a job and an assumption first.
- Solution-first opportunity nodes ("add a dashboard") in the tree. Opportunities are needs; a solution masquerading as a need hides better alternatives. Reject and re-phrase.
- Multiple target outcomes on one tree, or an output (feature count, velocity) sold as an outcome. It makes prioritization arbitrary and hides whether anything improved.
- Testing the comfortable assumption instead of the riskiest one. Validating that the UI is usable while never checking whether anyone wants the thing is theater.
- Running an experiment with no pre-committed pass/fail threshold or sample size, so any result is rationalized as success.
- Pitching during a discovery interview, or asking "would you use this?" Hypotheticals and leading questions produce false positives; ask about real past behavior.
- Building an MVP to test a question an interview or prototype could answer in a day. The RAT comes before the build.
- Discovery findings that never reach delivery as evidence — a feature title is handed over with no outcome, assumptions, or `log_handoff` record, so engineers inherit a guess.
- Discovery with no decision date, running indefinitely. Time-box it to a question and a deadline.

## Definition of done

- [ ] The initiative is framed as a Job-to-be-Done (situation/motivation/outcome), solution-free, with the core functional job identified.
- [ ] An opportunity solution tree exists with exactly one measurable target outcome (baseline plus target window) and opportunities phrased as needs, not solutions.
- [ ] At least two or three candidate solutions were compared for the chosen opportunity before committing.
- [ ] Assumptions are listed and classified (desirability/viability/feasibility/usability/ethical), with the one to three leap-of-faith assumptions named and feasibility/ethical ones routed to the owning specialists.
- [ ] The riskiest assumptions were tested with a method matched to the risk, each test having a pre-committed metric, threshold, sample, and persevere/pivot/kill decision.
- [ ] Evidence is weighted by strength (behavior over opinion) and stored with `save_memory`; the bet and rationale are recorded with `save_decision`.
- [ ] Discovery and delivery are kept on separate backlogs; only validated opportunities, carrying their evidence and target outcome, cross into delivery.
- [ ] The discovery-to-delivery transition is recorded with `log_handoff`, a `create_milestone` tracks the outcome, and the result is fed into the_prd_contract_template and prioritization.
