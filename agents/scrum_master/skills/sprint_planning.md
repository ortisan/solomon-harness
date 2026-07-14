---
name: sprint-planning
description: Governs how a sprint is planned by deciding what the team can credibly finish, covering capacity and commitment, buffer sizing, and protecting the sprint goal from mid-sprint churn. Use when planning a sprint, computing team capacity, or reviewing whether a sprint commitment is credible against velocity history.
---

# Sprint Planning

Plan a sprint by deciding what the team can credibly finish, not what it wishes it could start; commit to a single goal and a right-sized, Ready set of items, then protect that commitment from mid-sprint churn. The Scrum Master facilitates the mechanics (capacity, WIP, cadence); the product_owner owns the goal's value and the order of what gets pulled.

## Capacity and commitment

- Fixed two-week sprints. Do not vary length; stable cadence is what makes velocity and flow comparable across sprints.
- Timebox planning to two hours per week of sprint (four hours for a two-week sprint). End on time; an overrunning planning session is a signal the backlog was not Ready.
- Compute capacity from the rolling average velocity of the last three sprints, then reserve a 20 percent buffer for review churn, rework, and interruptions. Commit to capacity minus buffer. Where you have throughput history, cross-check the point-based commitment against a Monte Carlo "items by end-of-sprint" forecast (see the `flow_metrics_and_forecasting` skill); when the two disagree, trust the data-driven one and say why.
- Adjust raw capacity for known absences (PTO, on-call, holidays) before applying the buffer. A sprint with two engineers out is not an average sprint.
- Enforce WIP limits per specialist; a common rule is no more than two items in progress at once. Pull, do not push. Starting fewer items in parallel is what makes them finish sooner (Little's Law), so the WIP limit is a planning lever, not red tape.
- Each committed item must have its `PLAN.md` written during Planning before Execution starts: proposed changes, target files, edge cases, and verification criteria. No `PLAN.md`, not committed.
- Commitment is a forecast, not a promise. Track it honestly; pad nothing and round nothing up to look full.

## The sprint goal

The output of planning is a sprint goal in one sentence, the committed issue set tied to the active milestone, and owners assigned.

- One goal, one sentence, outcome-oriented: "Cut dashboard p95 load time under 1s for the top three portfolio views," not "do tickets 41, 42, 43." The goal is the why that lets the team renegotiate scope when reality bites while still delivering coherent value.
- Every committed item should serve the goal. Items that do not are either deferred or justify a second, smaller goal, never a list of unrelated work pretending to be a sprint.
- The goal is the unit you defend mid-sprint. If a stakeholder asks to add scope, the question is "does this serve the goal, and what comes out to make room," not "can we squeeze it in."

## Worked sprint-planning example

```
Team: 4 specialists. Last three sprints' velocity: 22, 26, 24 points.
  Rolling average            = (22 + 26 + 24) / 3 = 24 points
  One engineer out 4 days    -> raw capacity ~ 24 * (36/40) = 21.6 points
  Reserve 20% buffer         -> commit to 21.6 * 0.80 ≈ 17 points

Monte Carlo cross-check (items, not points): p85 forecast = 6 items by sprint end.

Sprint goal:
  "Serve cached portfolio valuations so the three busiest dashboards
   load under 1s at p95."

Committed set (tied to milestone 'Perf Q3', WIP cap 2 per owner):
  #41 Cache valuation by (portfolio_id, as_of), 60s TTL   5 pts  software_engineer
  #42 Wire dashboard to cached read path                  3 pts  software_engineer
  #43 p95 load-time assertion in the perf suite           3 pts  qa
  #44 Cache-staleness alert on >60s during market hours   3 pts  observability
  #45 Manual refresh control                              2 pts  frontend
                                                  total = 16 pts  (<= 17 cap)

Each item has PLAN.md and Given/When/Then acceptance criteria before Execution.
Owners assigned; nothing at 13 points; #46 (tick-level revaluation) left in
backlog as it does not serve this goal.
```

The team committed to 16 points against a 17-point cap, all five items serve the one goal, the Monte Carlo cross-check agreed (six items is within reach), and a sixth tempting item was left out because it did not serve the goal.

## Ceremonies and cadence

The sprint runs on a fixed rhythm of four events. Keep each timeboxed and outcome-driven; a ceremony that produces no decision or artifact is waste.

- Daily standup: 15-minute hard timebox. Three questions per owner: done since last, plan for today, blockers. Capture blockers as issues or handoffs; do not solve them in the meeting. Walk the board right-to-left (closest-to-done first) and lead with aging WIP, not with who is busy.
- Sprint review at sprint end: demo completed work against acceptance criteria. Only items that pass Verification and Code Review count as done; a branch that "works" but is unreviewed is not demoed as complete. The product_owner accepts or rejects against Definition of Done, and the increment, not the slideware, is the subject.
- Retrospective after review: one improvement action, owned and tracked as an issue. Carry it into the next sprint and check it closed before adding another; a retro that generates five actions and tracks none changes nothing.
- Refinement (continuous, ~5-10 percent of capacity): keep two sprints of items Ready so this planning session never stalls on clarification. Detailed in the `backlog_management` skill.

Throughout the sprint, track health with a burndown against committed points and flag scope creep the moment committed scope changes mid-sprint. Burndown answers "are we on track"; aging WIP (per the flow-metrics skill) answers "which item is in trouble" early enough to act. Watch both.

## Common pitfalls

- Committing to raw average velocity with no buffer, so every sprint overruns once review, rework, and interruptions land; reserve the 20 percent.
- Ignoring known absences before computing capacity, planning a depleted sprint as if it were average.
- A sprint goal that is a list of ticket numbers rather than one outcome sentence, leaving nothing to defend when scope pressure arrives mid-sprint.
- Committed items that do not serve the goal, so the sprint becomes a grab-bag and partial completion delivers no coherent value.
- Skipping `PLAN.md` to "save time," then discovering edge cases and target files mid-implementation, which is the expensive place to discover them.
- Letting WIP exceed the per-specialist limit; parallel starts inflate cycle time and nothing finishes (Little's Law), and the burndown stays flat until the last day.
- Treating the commitment as a promise and padding estimates to hit it; padded sprints destroy the velocity signal the next planning depends on.
- Ceremonies that run long or produce no artifact: a standup that debugs, a review with no accept/reject decision, a retro whose action is never tracked.
- Accepting mid-sprint scope additions without removing equivalent scope, silently breaking the commitment and the burndown.

## Definition of done

- [ ] Sprint length fixed at two weeks; planning timeboxed to four hours and ended on time.
- [ ] Capacity derived from the last three sprints' rolling velocity, adjusted for absences, with a 20 percent buffer; commitment is capacity minus buffer and cross-checked against a Monte Carlo item forecast where history exists.
- [ ] A one-sentence, outcome-oriented sprint goal is set; every committed item serves it.
- [ ] Committed set is tied to the active milestone, WIP limits per specialist are set, and owners are assigned.
- [ ] Every committed item has a `PLAN.md` and Given/When/Then acceptance criteria before Execution starts; nothing at 13 points is committed.
- [ ] The four ceremonies are scheduled and timeboxed: standup (15 min), review (accept/reject vs Definition of Done), retro (one tracked action), continuous refinement.
- [ ] Burndown against committed points and aging WIP are both tracked; mid-sprint scope changes are flagged and rebalanced, not silently absorbed.
