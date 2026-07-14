---
name: backlog-management
description: Governs how an item moves from a raw request to a Ready slice, covering refinement cadence and the INVEST/DEEP backlog properties, with the Scrum Master owning flow and readiness while product_owner owns order and value. Use when refining a backlog item toward Ready, planning refinement cadence, or reviewing backlog health against DEEP.
---

# Backlog Management

Keep the backlog a single ordered list of small, ready, valuable items, refined continuously so the top is always sprint-ready and the bottom is allowed to stay vague. The Scrum Master owns flow and readiness; the product_owner owns order and value. This skill governs how an item moves from a raw request to a Ready slice the team can pull, and how the two roles hand off cleanly.

## Refinement cadence and INVEST/DEEP

Refinement is continuous, not a single ceremony. Spend roughly 5-10 percent of team capacity on it (about two to four hours per two-week sprint) and keep two sprints' worth of items at the top meeting Definition of Ready, so a planning session never stalls waiting for clarification.

The backlog as a whole should be DEEP:

- Detailed appropriately: top items fine-grained and small; deeper items coarse and cheap to discard. Do not gold-plate an item you may never build.
- Estimated: top items carry a story-point estimate; lower items may be t-shirt sized or unestimated.
- Emergent: the list changes every sprint as you learn. A backlog that has not moved in a month is not being refined.
- Prioritized: one strict order, no ties. If two items are "both top priority," they are not ordered.

Each item should be INVEST:

- Independent: minimal coupling to other items, so it can ship alone.
- Negotiable: a placeholder for a conversation, not a frozen contract.
- Valuable: delivers observable value to a user or the system; reject "technical task with no stated outcome."
- Estimable: the team can size it; if not, it needs a spike first.
- Small: fits comfortably in one sprint. Story points on the Fibonacci scale (1, 2, 3, 5, 8, 13); anything at 13 is too big, split it before it enters a sprint.
- Testable: has acceptance criteria you can write a failing test against (Given/When/Then).

Operating rules that hold every week:

- Every backlog item is a tracked issue created from a template. No work without an issue.
- Groom weekly: re-rank by priority, kill stale `future` items, split oversized stories, and confirm top-of-backlog items meet Definition of Ready for the next two sprints.
- Label and route: triage each new issue to the owning specialist (quant_trader, ml_engineer, qa, security, software_engineer, etc.) and log the handoff with `log_handoff` so the routing is auditable.

## Ordering and the product_owner handoff

Order is a value decision, so it belongs to the product_owner; readiness is a flow decision, so it belongs to the Scrum Master. Keep the seam explicit.

- The product_owner sets the rank using a stated model (Weighted Shortest Job First, value-vs-effort, or RICE: Reach, Impact, Confidence, Effort). The Scrum Master does not silently re-order to optimize throughput; if flow argues for a different order (a blocking dependency, an item aging past its SLE), raise it and let the product_owner decide.
- WSJF is the default tiebreaker: `WSJF = Cost of Delay / job size`, where Cost of Delay sums business value, time criticality, and risk-reduction/opportunity-enablement. The smallest, most-urgent, highest-value item rises. It makes "why is this above that" a number, not an opinion.
- Record the decision. When the order changes for a non-obvious reason, the product_owner captures it with `save_decision` so the next session does not relitigate it.
- One backlog, one order. Resist parallel "priority" lists per stakeholder; merge them into the single ranked list or the seam leaks.

## Ready vs Done

These are two different gates and conflating them is how half-baked work enters a sprint or unfinished work gets demoed.

Definition of Ready (the entry gate, before an item enters a sprint): clear title, problem statement, acceptance criteria in Given/When/Then form, story-point estimate, dependencies named, and for quant work the hypothesis fields filled in (target Sharpe, drawdown limit, dataset, features, model architecture). If any field is missing, the item stays in refinement; it is not eligible for planning.

Definition of Done (the exit gate, before an item counts as delivered): acceptance criteria demonstrably met, tests written and passing, code reviewed, and the change verified against the original problem statement. An item that "works on the branch" but is unreviewed is not done.

The asymmetry matters: Ready protects the sprint from ambiguity; Done protects the increment from regression. An item can be Ready and still fail, but an item that is not Ready should never be committed.

## Worked refinement example

Raw request, not ready:

> "Users want faster portfolio loads."

Refined to a Ready slice:

```
Title: Cache portfolio valuation so the dashboard loads under 1s at p95
Problem: The dashboard recomputes every position's valuation on each load;
         p95 load time is 4.2s, above the 1s target, and users abandon.
Acceptance criteria:
  Given a portfolio whose valuation was computed within the last 60s
  When the user opens the dashboard
  Then the cached valuation is served and p95 load time is <= 1s
  And when the cache is older than 60s the valuation is recomputed and re-cached
Out of scope: real-time tick-level revaluation (separate item, ranked lower)
Dependencies: valuation service exposes a cache-key by (portfolio_id, as_of)
Estimate: 5 points
Owner: software_engineer; perf assertion reviewed by qa
RAID: Risk - stale cache during fast market moves; mitigation - 60s TTL + manual refresh
```

The original 13-point "make it faster" epic was split: this 5-point caching slice ships value now; tick-level revaluation and a load-test harness became two separate lower-ranked items. Each is independently shippable, estimable, and testable. The product_owner ranked the caching slice top via WSJF (high time-criticality, small job size); the Scrum Master confirmed Definition of Ready and routed it.

## Common pitfalls

- Treating refinement as a one-off meeting instead of a continuous activity, so planning sessions burn their timebox clarifying scope that should already be Ready.
- Carrying 13-point or unestimable items into a sprint; they overrun and hide the real cause (the item was never small enough to finish).
- The Scrum Master silently re-ordering the backlog for throughput, which strips the product_owner's value decision and erodes trust; raise the flow concern, do not override the order.
- Conflating Ready and Done, so unrefined items get committed or unreviewed work gets demoed as complete.
- A backlog with ties in priority. "Both are top" means neither is ordered and planning will pull the wrong one.
- Refining the whole backlog to the same fine grain, wasting effort detailing items that may be discarded; keep depth proportional to proximity.
- Acceptance criteria written as prose instead of Given/When/Then, leaving no testable boundary for the failing test the implementer must write first.
- Routing an issue without logging the handoff, so the owning specialist and the reason are lost by the next session.

## Definition of done

- [ ] Every item is a tracked issue from a template; the backlog is one strictly ordered list with no ties.
- [ ] Top two sprints of items meet Definition of Ready: title, problem, Given/When/Then acceptance criteria, estimate, named dependencies, and quant hypothesis fields where applicable.
- [ ] Items are INVEST and the backlog is DEEP; nothing at 13 points enters a sprint, oversized stories are split first.
- [ ] Order is set by the product_owner with a stated model (WSJF/RICE); non-obvious re-rankings are recorded via `save_decision`.
- [ ] Refinement runs continuously at ~5-10 percent of capacity; stale `future` items are killed each week.
- [ ] Definition of Ready (entry) and Definition of Done (exit) are documented and applied as separate gates.
- [ ] Each new issue is routed to the owning specialist and the handoff is logged with `log_handoff`.
