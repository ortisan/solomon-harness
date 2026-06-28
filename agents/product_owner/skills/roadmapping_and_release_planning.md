# Roadmapping and Release Planning

Build a roadmap that commits to outcomes and problems, not to a dated list of features, and a release plan that ships value in thin vertical slices on a probabilistic schedule. Treat the roadmap as a statement of intent under uncertainty: it tells stakeholders what problems you will attack and roughly when, while leaving the team free to discover the cheapest solution. Dates are forecasts with a confidence interval, never promises pulled from a Gantt chart.

## Outcome-based roadmaps (now/next/later)

A roadmap is organized by outcome, not by output. Each item names a measurable change in user or business behavior (activation rate, time-to-first-value, churn, revenue per account) and the problem behind it, so the team owns the "how" and can swap solutions without renegotiating the roadmap.

- Structure with **now / next / later** horizons (popularized by ProductPlan and the GV/Roman Pichler school), not calendar quarters. "Now" is in-build and high-confidence; "next" is the validated queue; "later" is directional and deliberately vague. Confidence and detail decay as you move right; do not pretend "later" is estimable.
- Group work into a hierarchy: **theme** (a strategic bet, e.g. "reduce onboarding friction") -> **epic** (a shippable body of work serving the theme) -> **story** (an INVEST-sized increment, owned by `user_stories_invest`). A theme lives for one or more quarters; an epic for weeks; a story for days.
- Attach a target metric and a baseline to every theme. "Improve onboarding" is not a roadmap item; "raise day-7 activation from 38% to 50%" is. Without a baseline you cannot tell when the theme is done or whether it worked.
- Keep the roadmap to a single page per audience. The executive view shows themes and outcomes; the delivery view shows epics and rough sequencing. They are projections of the same data, not separate documents that drift.
- Record the strategic bet behind each theme with `save_decision` (the hypothesis, the metric, the alternatives rejected) so a later reader sees why it was prioritized, and re-link the theme to the epics that serve it.

A minimal delivery view:

```text
NOW (in build, high confidence)
  Theme: Reduce onboarding friction  -> day-7 activation 38% -> 50%
    Epic: One-tap social sign-in            (slices 1-3, in sprint)
    Epic: Skippable setup wizard            (slice 1 demoed, rest queued)
NEXT (validated, sequenced)
  Theme: Recover abandoning users    -> trial->paid 12% -> 18%
    Epic: Re-engagement email on day 3
LATER (directional, not estimated)
  Theme: Self-serve team plans       -> expansion revenue (baseline TBD)
```

## Prioritization: MoSCoW and where it fits

MoSCoW (Must / Should / Could / Won't) scopes a single release; it answers "what is in this train" once you already know relative value. Use a scoring method to rank the backlog, then MoSCoW to draw the line for a specific delivery.

- **Must**: the release fails to meet its goal without it. If everything is a Must, you have not prioritized. Cap Musts at roughly 60% of release capacity (DSDM guidance) so the plan has slack to absorb estimation error.
- **Should**: important but the release still delivers value if it slips. **Could**: desirable, the first to drop under pressure, your contingency buffer. **Won't (this time)**: explicitly out of scope for this release, recorded so it is a decision and not an oversight; feed it into `scope_boundaries`.
- MoSCoW ranks within a release. For ranking the whole backlog, use a quantified method from `prioritization` (RICE, WSJF) and show the numbers; MoSCoW alone has no value model and degrades into opinion.
- Re-apply MoSCoW each release, not once. A Could that keeps slipping is signaling that its parent theme is mis-ranked; escalate it, do not silently carry it forward.

## Slicing into thin vertical increments

A release is a sequence of the smallest changes that each deliver observable user value end to end. Slice vertically (a complete capability through every layer) rather than horizontally (a whole layer with no user-facing behavior).

- Each slice must cross the full stack: UI, logic, persistence, and an observable outcome. "Build the database schema" is a horizontal slice that ships nothing; "a user saves one draft and reloads it" is vertical and demoable.
- Apply SPIDR (Spike, Path, Interface, Data, Rules) or the story-splitting patterns when an epic is too big: split by workflow step, by happy-path-then-edge-cases, by data variation, or by business rule. The first slice is usually the thin happy path with everything else deferred.
- Target a slice that fits inside one sprint with margin; if it cannot be demoed at the review, it is too big. Vertical slices keep `acceptance_criteria_given_when_then` testable and let QA verify behavior each iteration instead of at the end.
- Sequence slices to retire the biggest risk or unlock the biggest learning first (walking-skeleton first), not the easiest work first. The earliest slices should validate the theme's hypothesis cheaply.
- The team owns story-level decomposition during refinement; you own that each slice maps to a roadmap epic and carries its outcome. Hand the sliced, Ready set to `scrum_master` for sprint planning and milestone creation.

## Release trains versus continuous delivery

Choose a cadence model deliberately; it shapes how the roadmap is read and how dates are framed.

- **Release train**: fixed-cadence, date-driven releases (e.g. every two weeks or, in SAFe, a Program Increment of 8-12 weeks). The train leaves on schedule; unfinished work waits for the next one. Scope flexes, the date does not. Use this when multiple teams or external partners must synchronize, or when downstream (marketing, compliance, app-store review) needs a predictable window.
- **Continuous delivery**: each increment ships when it passes the pipeline; there is no release event. Decouple deploy from release with feature flags and trunk-based development so code reaches production dark and is exposed by a flag flip. Use this when one team owns the surface and can release independently. Coordinate the technical enablement with `sre` and the flag-driven exposure plan with the delivery team.
- The roadmap is cadence-agnostic, but the release plan is not: a train roadmap shows which themes land in which PI; a continuous roadmap shows themes flowing through now/next/later with flag-gated rollout. State which model you are on so "when will it ship" has a consistent meaning.
- Under continuous delivery, separate **feature-complete** from **generally available**. A flag at 5% is shipped but not released; the roadmap "done" marker is GA plus the outcome metric moving, not the merge.

## Probabilistic plans, not fixed dates

Commit to a confidence range, never a single date you cannot defend. Forecasts come from measured throughput, not from summing optimistic estimates.

- Forecast with **Monte Carlo simulation** over historical throughput (stories completed per week) rather than story-point summation. Run 5,000+ trials against the remaining backlog and report a distribution: "85% likely by week 9, 50% by week 7." Tools: Actionable Agile, the Nave/FlowViz simulators, or a short script over the team's cycle-time history. A bare-bones simulation samples past weekly throughput to drain the backlog:

```python
import random
def weeks_to_finish(backlog, history, trials=10000):
    results = []
    for _ in range(trials):
        remaining, weeks = backlog, 0
        while remaining > 0:
            remaining -= random.choice(history)  # sample an observed week
            weeks += 1
        results.append(weeks)
    results.sort()
    return {"p50": results[trials // 2], "p85": results[int(trials * 0.85)]}
# weeks_to_finish(backlog=40, history=[6, 4, 7, 5, 3, 8, 5]) -> e.g. {"p50": 8, "p85": 9}
```
- Quote forecasts at named confidence levels. Plan internal commitments at P85; never communicate the P50 (the coin-flip date) as a deadline. If a hard external date exists, flex scope (MoSCoW Coulds drop first), not quality or the date.
- Track empirical flow metrics and let them drive the forecast: throughput, cycle time, work-in-progress, and aging work items. A rising cycle time or aging item invalidates the current forecast; re-run it rather than reassuring stakeholders from the old number.
- Re-forecast every iteration and publish the change with its cause. Persist each forecast snapshot with `save_memory` and the decision to re-scope or hold the date with `save_decision`, so the trail of "what we believed and when" survives. When a forecast crosses a threshold that endangers a milestone, raise it with `log_issue` and hand the context to the next stage with `log_handoff`.
- Reflect dates on the roadmap as ranges or horizons (now/next/later, or "targeting Q3, P70"), never as a single pinned day in the "later" column. Precision you do not have is a lie stakeholders will hold you to.

## Common pitfalls

- A feature-list roadmap with no outcomes or baselines: every item is an output, so you can never tell whether shipping it worked. Reject; demand a metric and baseline per theme.
- Dated quarters treated as commitments. A roadmap that promises specific features on specific dates beyond "now" is fiction; it must degrade to ranges and horizons as confidence drops.
- Everything marked Must in MoSCoW. That is the absence of prioritization; cap Musts near 60% of capacity and force real Should/Could/Won't splits.
- Horizontal slices ("build the API", "build the schema") presented as roadmap increments. They ship no user value and hide integration risk to the end. Require vertical, demoable slices.
- A single forecast date with no confidence level, derived from summed estimates instead of measured throughput. Reject; require a Monte Carlo range at a stated percentile.
- Communicating the P50 as the deadline, then treating the inevitable slip as a failure. Commit at P85 and flex scope.
- Confusing deploy with release under continuous delivery: calling a feature "done" at merge when it is dark behind a flag and the outcome metric has not moved.
- A "Won't this time" item that quietly reappears in scope without a recorded decision, eroding the scope boundary.
- Slices sequenced easiest-first, leaving the theme's core hypothesis untested until late. Sequence by risk and learning.

## Definition of done

- [ ] The roadmap is organized by outcome with now/next/later horizons; every theme has a target metric and a baseline, and detail decays toward "later".
- [ ] Work is structured theme -> epic -> story, and each epic links to the theme outcome it serves.
- [ ] Release scope is set with MoSCoW, Musts are capped near 60% of capacity, and "Won't this time" items are recorded in the scope boundary.
- [ ] Backlog ranking uses a quantified method (RICE/WSJF) with the numbers shown; MoSCoW is applied per release, not once.
- [ ] Every increment is a thin vertical slice that crosses the full stack, fits in one sprint, and is demoable with testable acceptance criteria.
- [ ] The cadence model (release train vs continuous delivery) is stated, and feature-complete is distinguished from generally available.
- [ ] Dates are expressed as probabilistic forecasts from measured throughput (Monte Carlo), quoted at named confidence levels, with internal commitments at P85.
- [ ] Forecasts are re-run each iteration; the strategic bet, forecast snapshots, and re-scope decisions are persisted via `save_decision` / `save_memory`, and milestone-threatening slips raised via `log_issue` and `log_handoff`.
