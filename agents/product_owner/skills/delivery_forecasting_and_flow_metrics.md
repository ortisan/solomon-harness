# Delivery Forecasting and Flow Metrics

Forecast delivery from how work actually flows instead of from a wished-for single date: measure cycle time, throughput, and work-in-progress, run a Monte Carlo simulation over historical throughput, and publish a probabilistic range (50th/85th/95th percentile) the business can plan against and trade against scope. As Product Owner you own the external commitment and the scope decisions that follow from it; the team's flow discipline, board hygiene, and chart maintenance belong to the scrum_master skill `flow_metrics_and_forecasting`. Pull their data, do not reproduce their process.

## The four flow metrics and Little's Law

Define every metric against explicit board gates and use the same gates every time, or the numbers are not comparable.

- Cycle time: elapsed time from when an item enters an active "in progress" column to when it reaches "done". This is the engineering signal you forecast with.
- Lead time: elapsed time from when the customer's request is committed (enters the backlog as accepted) to "done". This is the number you quote the stakeholder; it is always >= cycle time because it includes queue time before work starts.
- Throughput: count of items completed per unit time (per day or per week). Count items, not story points. Counts are what Monte Carlo samples.
- Work-in-progress (WIP): number of items between the start and end gates at a point in time.

Little's Law, operational form:

```
Average Cycle Time = Average WIP / Average Throughput
```

Use it as a sanity check and a lever, not a point predictor. It holds only when the system is roughly stable over the window: arrivals approximate departures, WIP is not trending up or down, every started item eventually finishes (no silent abandonment), and units are consistent. The actionable consequence: to cut cycle time you lower WIP, because throughput is bounded by team capacity. A team carrying 20 items at a throughput of 4/week averages a 5-week cycle time by arithmetic; cutting WIP to 8 roughly halves it. This is the data behind any "stop starting, start finishing" scope argument you make.

## Cumulative flow diagram (CFD)

A CFD stacks the cumulative item count in each board status over time. Read it to confirm the "stable system" assumption your forecast depends on before you trust the forecast.

- Vertical gap between the top arrival band and the "done" band at any date = current WIP. A widening gap means WIP is growing and cycle time is about to rise; your forecast is now optimistic.
- Horizontal distance between the arrival line and the done line = approximate lead time for work finishing then.
- A band that stops climbing (flat top) = a stage being starved; a band bulging wider = a bottleneck accumulating queue.
- Bands climbing in clean parallel = a stable system and a trustworthy forecast.

If the CFD shows WIP inflation or a bottleneck, raise it with `log_issue` and discount the forecast confidence rather than publishing a tighter range than the data supports.

## Monte Carlo forecasting

Replace velocity-times-sprints math with simulation. Two questions, both answered by sampling historical throughput with replacement over thousands of trials.

- "When will it be done?" Given a backlog of N items, sample daily (or weekly) throughput from the last 8-12 weeks, accumulate until N items are complete, record the elapsed days. Repeat 10,000 times and read percentiles off the resulting distribution.
- "How much by date D?" For each trial, sum sampled throughput across the D days to D and record the total; the distribution tells you how many items you will likely have done.

```python
import random

def forecast_when(backlog_items, daily_throughput_samples, trials=10000):
    results = []
    for _ in range(trials):
        done, days = 0, 0
        while done < backlog_items:
            done += random.choice(daily_throughput_samples)  # sample with replacement
            days += 1
        results.append(days)
    results.sort()
    return {p: results[int(trials * p / 100)] for p in (50, 85, 95)}

# daily_throughput_samples = items closed per working day over the trailing window
# e.g. {50: 18, 85: 24, 95: 28}  => 50% chance within 18 days, 85% within 24, 95% within 28
```

Decision rules:

- Commit externally at the 85th percentile; plan internally to the 50th and hold the gap as buffer. Quoting the 50th to a stakeholder is committing to a coin flip.
- Forecast in item counts, so right-size work first. Split any story whose expected cycle time exceeds your 85th-percentile cycle time (the Service Level Expectation, e.g. "85% of items finish within 9 days") so the throughput sample stays meaningful. This is the forecasting reason behind the INVEST "small" rule in `user_stories_invest`.
- Use a trailing window of roughly 8-12 weeks, or about twice the forecast horizon, so the sample reflects the current team and process. Discard data from before a major team or workflow change; old throughput forecasts a team that no longer exists.
- Account for scope growth: backlogs grow as work proceeds. Either forecast a count inflated by the historical split rate, or re-run the simulation each sprint and watch the date move. A forecast is a living number, not a one-time stamp.

## Communicating and persisting the forecast

- Publish a range, never a single date: "50% by Mar 10, 85% by Mar 24, 95% by Apr 2." A lone date hides the risk and you will be held to the optimistic end of a distribution you never disclosed.
- Record the committed forecast with `save_decision`: the target percentile, the date, the backlog count at forecast time, and the throughput window used. This makes the commitment auditable and lets you defend it when scope or staffing later changes the result.
- Snapshot the throughput series and Monte Carlo configuration with `save_memory`; refresh inputs from `get_latest_activity` (recent closures) before each re-forecast so you simulate on current data.
- When you hand the forecast to the scrum_master for sprint shaping or to stakeholders for planning, log it with `log_handoff` so the receiving party gets the assumptions, not just the date.
- When a re-forecast pushes the 85th percentile past a committed milestone, raise it with `log_issue` immediately and bring a scope-trade option (see `scope_boundaries` and `prioritization`) rather than letting the date slip silently.

## Tooling

Native control/throughput charts in Jira and GitHub Projects insights give cycle time and throughput; Actionable Agile and Nave produce CFDs, cycle-time scatterplots, and Monte Carlo directly. For ad hoc forecasts the ~15-line simulation above over a CSV of closed-item timestamps is enough and keeps the math inspectable. Whatever the tool, validate that its start/end gates match the ones the scrum_master keeps the board on.

## Common pitfalls

- Quoting a single date with no percentile. It conceals the distribution and silently commits to the optimistic tail; reject any roadmap date without a stated confidence.
- Forecasting with story-point velocity and "remaining points / average velocity". Estimation noise and point inflation make it fragile; count-based Monte Carlo is more robust and removes the estimation theater.
- Committing externally at the 50th percentile. That is a 50/50 bet sold as a plan.
- Using throughput from before a team or process change. The sample no longer represents the system you are forecasting.
- Inconsistent start/end gates between cycle-time, lead-time, and the board, so metrics are not comparable across items or sprints.
- Treating Little's Law as a predictor while WIP is trending up. The CFD will show the instability; the law only holds for a stable system.
- Mixing wildly different item sizes in one throughput sample without right-sizing, so the simulation's per-item assumption is meaningless.
- Forecasting the current backlog count and ignoring scope growth, then being surprised when discovered work moves the date.
- Stamping a forecast once and never refreshing it as throughput and scope move.

## Definition of done

- [ ] Cycle time, lead time, throughput, and WIP are each defined against explicit, consistent board gates aligned with the scrum_master's board.
- [ ] The forecast is produced by Monte Carlo over a trailing 8-12 week (or ~2x horizon) throughput sample, using item counts, not point velocity.
- [ ] Work is right-sized below the 85th-percentile cycle time (the stated SLE) before counts are used to forecast.
- [ ] The system's stability is checked on the CFD; an unstable system (rising WIP, visible bottleneck) lowers the published confidence and is logged via `log_issue`.
- [ ] The commitment is published as a percentile range (50/85/95), committed externally at the 85th and planned internally at the 50th.
- [ ] Scope growth is accounted for, and the forecast is re-run each sprint on refreshed data from `get_latest_activity`.
- [ ] The committed forecast, its percentile, backlog count, and throughput window are persisted with `save_decision`; the handoff to the team or stakeholders is recorded with `log_handoff`.
- [ ] A forecast that breaches a committed milestone is raised with `log_issue` together with a concrete scope-trade option.
