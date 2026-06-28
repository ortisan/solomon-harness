# Flow Metrics and Forecasting

Run the team's delivery system as a flow system: measure how long work takes and how reliably it moves, find where it stalls, and forecast sprint and release dates from data instead of from gut feel or story-point velocity. Every metric here is a property of the system and the queue, not of a person; use them to fix the workflow and to set honest expectations, never to rank or pace individuals. For the requirements and stakeholder-commitment side of these same numbers, cross-reference the product_owner `delivery_forecasting_and_flow_metrics` skill; for how forecasts feed capacity, see the sibling `sprint_planning` skill.

## The four flow metrics (the Kanban guide baseline)

The 2025 Kanban Guide names four core metrics. Define them once, the same way for every board, or comparisons are meaningless.

- WIP (work in progress): the count of items started but not finished at a point in time. The leading indicator; everything else follows from it.
- Cycle time: elapsed time from when an item starts (enters the first active, committed column) to when it is done. Measured in calendar days, not working hours, because queues do not pause for weekends.
- Lead time: from request/commitment to done. Be explicit about the start point: "customer lead time" runs from the moment a stakeholder asked; "system/flow lead time" runs from commitment. State which one a chart shows.
- Throughput: items completed per unit time (per sprint, per week). Count items, not points; point-weighted throughput reintroduces estimation noise into a metric whose whole value is that it does not need estimates.

Little's Law ties them together at steady state: `average cycle time = average WIP / average throughput`. The operational lesson is not the algebra, it is the lever: to cut cycle time you cut WIP, because throughput is bounded by the team's actual capacity. This is why pulling less in parallel makes things finish sooner. The law holds only at steady state over a window where arrivals roughly match departures and little work is abandoned; do not apply it to a single day or a board that is filling up faster than it drains.

A concrete read: a team holding 12 items in progress and completing 4 per week has an average cycle time of `12 / 4 = 3` weeks. Halve WIP to 6 with the same capacity and average cycle time falls to about `6 / 4 = 1.5` weeks. Nothing about the people changed; only the queue did.

## WIP limits

WIP limits are the one control that makes every other metric move; set them explicitly per column and per specialist and enforce them by pulling, not pushing.

- Start from the team size, not from ambition. A common starting limit is one to two items in progress per specialist; lower it until items start finishing, then hold. The point of a limit is to make the team feel the pull signal when a column is full, forcing it to finish before starting.
- A blocked item still counts against WIP. Do not "park" it off the limit and start something new; that is exactly how aging work accumulates invisibly. Mark it blocked, keep it in the count, and swarm it.
- When a column hits its limit, the upstream column stops feeding it. That backpressure is the mechanism; without it a board accumulates WIP, cycle time climbs per Little's Law, and the CFD bands widen.
- Tune limits from data, not opinion. If a column is chronically full while the next is starved, the limit is too high upstream or capacity is misallocated downstream. Re-balance, then observe the cycle-time percentiles for a few weeks.
- Lowering WIP is the cheapest cycle-time improvement available and needs no new headcount; it is usually the first countermeasure for a slow team.

## Percentiles, not averages

Cycle-time distributions are right-skewed (a long tail of items that got stuck), so the mean lies and the standard deviation is undefined-in-practice. Report percentiles.

- Use the 50th (median), 85th, and 95th percentiles. A Service Level Expectation (SLE) is a percentile plus a range: "85% of items finish within 9 days." That is a forecast the team can stand behind, not a deadline per item.
- Plot a cycle-time scatterplot (one dot per completed item, x = completion date, y = cycle time) with percentile lines. It exposes trend, outliers, and whether the SLE is holding far faster than any average.
- Derive the SLE from history; do not invent it. Recompute it each quarter or after a workflow change.
- Read the p50/p85 gap as a variability signal: a median of 3 days with an 85th percentile of 14 days means the system is unpredictable even though "typical" looks fast. Stakeholders feel the 85th, so commit on it.

## Cumulative flow diagram (CFD)

A CFD stacks the count of items in each workflow state over time. Read it for system health, not for celebration:

- Bands should rise roughly in parallel. A widening band means WIP is accumulating in that state: a bottleneck upstream of it or starvation downstream.
- The vertical gap between the top of "done" and the bottom of "in progress" at a date is approximate WIP; the horizontal distance between the arrival and departure curves is approximate lead time. Both should be stable or shrinking.
- Flat top band (no completions) for several days is a flow stoppage; investigate before the standup, do not wait for the retro.
- A CFD that only ever climbs with no flattening bands and ever-widening WIP is the signature of a team committing faster than it finishes. Tie this back to the `sprint_planning` capacity decision.

## Aging work in progress

The single most actionable chart and the one a Scrum Master should look at daily. Aging WIP shows, for each item still in progress, how long it has been in progress, plotted against the cycle-time percentile lines.

- An item whose age has crossed the 85th percentile line but is not done is at risk; an item past the 95th is the day's priority. Swarm it, split it, or escalate the blocker.
- This is a pull signal, not a performance review. The question is "what does this item need," never "who is slow." Keep that framing explicit in standups so the metric stays trusted.
- Aging WIP catches problems while you can still act; cycle time only tells you after the item shipped. Lead with aging.

## Flow efficiency

`flow efficiency = active time / total cycle time x 100`. Active time is when someone is actually working the item; the rest is wait time (blocked, in a queue, waiting on review or a dependency).

- Most unoptimized knowledge-work teams land at 15-25%. Treat anything under ~40% as a queue problem, not a productivity problem: the fix is removing waits (review SLAs, dependency handoffs, environment access), not pushing people to work faster.
- You rarely need precise active-time tracking. Approximate from blocked-state durations and review-queue time; the trend matters more than the decimal.
- Log a recurring low-efficiency stage as an issue with `log_issue` and the root-cause decision with `save_decision`, so the bottleneck and the chosen countermeasure are auditable across sprints rather than rediscovered each retro.

## Monte Carlo forecasting

Replace "velocity x sprints" point estimates with a probabilistic forecast built by resampling the team's own throughput history. Two questions, both answered as a distribution with confidence levels.

- "When will N items be done?" Simulate: each trial, draw daily/weekly throughput samples from history and accumulate until N items are reached; record the elapsed time. Run 10,000 trials; read percentiles.
- "How many items by date D?" Each trial, sum sampled throughput across the days until D; record the count.
- Report the 50th, 85th, and 95th percentile dates/counts. Commit externally to the 85th percentile, not the 50th: the median is a coin flip you will miss half the time.

```python
import random

def forecast_when(backlog_items: int, throughput_history: list[int], trials: int = 10_000) -> dict:
    # throughput_history: items completed per period (e.g. per week), >= 8 recent periods.
    results = []
    for _ in range(trials):
        done, periods = 0, 0
        while done < backlog_items:
            done += random.choice(throughput_history)  # resample with replacement
            periods += 1
        results.append(periods)
    results.sort()
    pct = lambda p: results[int(p / 100 * trials)]
    return {"p50": pct(50), "p85": pct(85), "p95": pct(95)}
```

Worked example. A release needs 40 backlog items done. The last 10 weeks of throughput were:

```
throughput_history = [6, 4, 5, 7, 3, 6, 5, 4, 8, 5]   # items completed per week
forecast_when(40, throughput_history)
# -> {"p50": 8, "p85": 9, "p95": 10}   weeks (representative run)
```

Read it as a sentence the team can defend: "There is an 85% chance the 40 items finish within 9 weeks." If today is week 0, you commit the release date at week 9 (the p85), keep week 8 as the optimistic internal target, and treat week 10 (p95) as the worst credible case to flag risk against. Note the spread is only one to two weeks because the history is tight (3-8 items/week); a noisier history would widen p50-to-p95 and you would commit later. Re-run the forecast every sprint: as the 40 shrinks to 28 and throughput updates, the date sharpens and any drift surfaces immediately.

- Use 8-15 recent periods of throughput; older data predates the current team or process and skews the forecast. Re-run after every sprint so the forecast tracks reality.
- Inputs require honesty: count only items that actually reached done, and split the backlog into items of comparable size (or let the right-skew absorb variation) rather than feeding point totals.
- Monte Carlo needs no estimates and no velocity ritual. Its only assumption is that the near future resembles the recent past; when the team or scope changes materially, say so and widen the range.
- Account for scope growth: if the backlog historically grows during delivery, add a split-rate multiplier (e.g. forecast 40 x 1.2 = 48 items) or sample the net throughput after new arrivals, so the forecast is not optimistic by construction.
- Persist the forecast and its inputs with `save_memory`, attach the committed date to the release with `create_milestone`, and record the chosen confidence level via `save_decision`. When a forecast is handed to the product_owner for a stakeholder commitment, use `log_handoff` so the assumptions travel with the number.

## Tooling

- Jira/Linear/Azure Boards export raw item start/done timestamps; compute metrics from those, not from the vendor's averaged dashboards.
- Actionable Agile, Nave, and KanbanZone render scatterplots, CFDs, aging WIP, and Monte Carlo directly. For this Python codebase, a small script over exported CSV plus the `forecast_when` pattern above is enough and keeps the math transparent.
- Whatever the tool, store the SLE, the active SLE percentile, and the latest forecast in project memory (`save_memory`) so successive sessions and the `get_latest_activity` view share one source of truth.

## Common pitfalls

- Using averages or velocity for forecasts; cycle time is right-skewed and points are estimates. Reviewers should reject any date built on `mean cycle time` or `avg velocity x sprints` and require percentiles or Monte Carlo.
- Throughput counted in story points rather than items, which smuggles estimation noise back into an estimate-free metric.
- Inconsistent start/done definitions between boards or over time, making cycle time and CFDs incomparable. Pin the definitions.
- Applying Little's Law to a board that is not at steady state (filling faster than it drains, or heavy abandonment), where the average relationship does not hold.
- Parking blocked items outside the WIP count so aging work accumulates invisibly and the limit stops meaning anything.
- Presenting any flow metric per person (individual cycle time, individual throughput). It is a system metric; per-person framing destroys trust and drives gaming. Reject it on sight.
- Committing to the 50th-percentile forecast date, then treating the inevitable overrun as a team failure. Commit at 85% or higher.
- Monte Carlo run on stale or tiny history (2-3 periods, or data from before a reorg), producing false precision.
- Forecasting a fixed backlog while ignoring scope growth, so the date is optimistic by construction.
- Watching cycle time (a lagging, post-hoc metric) while ignoring aging WIP (the leading one you can still act on).
- Reading flow efficiency as a call to make people work faster instead of as a queue/wait problem to remove.
- Forecasts produced once and never refreshed, so the committed date drifts from reality with no one noticing.

## Definition of done

- [ ] WIP, cycle time, lead time, and throughput are defined identically across boards, with explicit start/done points; throughput counts items, not points.
- [ ] WIP limits are set per column and per specialist, enforced by pull, with blocked items kept in the count; Little's Law is applied only at steady state.
- [ ] Cycle time is reported as 50th/85th/95th percentiles with a scatterplot; an SLE is derived from history, not invented.
- [ ] A CFD and a daily-reviewed aging WIP chart are in place; items past the 85th-percentile age are surfaced at standup as pull signals, framed around the item, never the person.
- [ ] Flow efficiency is tracked as a trend; stages under ~40% are logged as bottleneck issues with a recorded root-cause decision.
- [ ] Sprint and release forecasts use Monte Carlo over 8-15 recent throughput periods, report p50/p85/p95, account for scope growth, and external commitments use the 85th percentile or higher.
- [ ] Forecasts, inputs, and confidence level are persisted (`save_memory`, `save_decision`), the release date is set with `create_milestone`, and handoffs to product_owner use `log_handoff`.
- [ ] No flow metric is reported per individual; all are framed as properties of the workflow.
- [ ] Forecasts are re-run each sprint and after any material team or scope change, and the requirements-side view is reconciled with the product_owner `delivery_forecasting_and_flow_metrics` skill.
