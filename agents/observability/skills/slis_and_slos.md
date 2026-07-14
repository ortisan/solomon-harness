---
name: slis-and-slos
description: Governs how SLIs and SLOs are chosen, computed as good/valid event ratios, budgeted with an explicit error-budget policy, and wired into multiwindow multi-burn-rate alerts. Use when defining a new SLI, setting an SLO target, or configuring burn-rate alert thresholds and windows.
---

# SLIs and SLOs

This skill governs how service level indicators and objectives are chosen, computed, and wired into alerting. The stance: an SLI is a good/valid event ratio measured where the user is, the SLO's error budget is stated as a number with a written policy, and alerts fire on budget burn rate — the multiwindow multi-burn-rate scheme from the Google SRE workbook — not on raw error counts.

## Choosing SLIs per service type

Match the SLI menu to what the service is, and write the exact numerator and denominator plus the measurement point (load balancer logs, server-side, or real-user monitoring):

- Request/response services: availability (non-5xx responses / valid requests), latency (requests completed under the threshold / valid requests — state the threshold, for example 300 ms, and which percentile it encodes), and correctness or quality where responses can be degraded.
- Data pipelines and batch jobs: freshness (age of the newest fully processed record versus target), correctness (sampled outputs matching a golden source), coverage (records processed / records that should have been processed), and throughput.
- Storage systems: durability, availability, and read/write latency.

Base SLIs on user experience, never on internal proxies like CPU. For this harness, a memory-layer SLI would be "MCP writes acknowledged by SurrealDB within 500 ms / all MCP write attempts": the SQLite fallback keeps work unblocked, but a fallback write is not a good event for this SLI — the fallback engaging is precisely the degradation being measured.

## Targets and error budget math

Error budget = 1 - SLO. Monthly downtime budgets (calendar month, about 30.44 days): 99.9 percent allows about 43m 49s of full unavailability; 99.95 percent about 21m 54s; 99.99 percent about 4m 23s. For request-based SLIs the arithmetic is direct: 10 million valid requests in the window at a 99.9 percent target allows 10,000 bad events.

Pick the tier the product actually needs. Each extra nine multiplies engineering cost, and an over-tight SLO wastes budget on false pages while eroding trust in the alerting. The budget is the release governor: agree on the policy in writing before it is needed — when the budget for the window is exhausted, risky launches stop and the effort goes to reliability work until the budget recovers.

## Burn rate

Burn rate normalizes error spend against the SLO window: burn rate = observed bad-event ratio / (1 - SLO). Burn rate 1 means spending exactly the whole budget over the full window. For a 99.9 percent, 30-day SLO, a burn rate of 14.4 corresponds to a 1.44 percent error ratio; sustained for one hour it consumes 14.4 x (1h / 720h) = 2 percent of the monthly budget.

## Multiwindow multi-burn-rate alerts

The SRE workbook numbers, which this agent uses as the default for a 30-day SLO:

| Budget consumed | Long window | Short window | Burn rate | Action |
| --- | --- | --- | --- | --- |
| 2% in 1 hour | 1h | 5m | 14.4 | page |
| 5% in 6 hours | 6h | 30m | 6 | page |
| 10% in 3 days | 3d | 6h | 1 | ticket |

The short window is 1/12 of the long window, and both must exceed the threshold for the alert to fire: the long window provides confidence the burn is real, the short window stops the alert from staying red long after the incident ended and kills flapping. For a 99.9 percent SLO the fast-burn page condition is:

```
error_ratio_1h > 14.4 * 0.001 and error_ratio_5m > 14.4 * 0.001
```

Set expectations for detection time: at full outage, the 14.4x rule fires within a few minutes on a high-traffic service. Low-traffic services need guards — do not evaluate the expression below a minimum event count (for example fewer than 1 request/s or fewer than a few hundred events in the short window), or a single failed request produces a page.

## Common pitfalls

- SLIs defined on internal proxies (CPU, queue depth) instead of user-visible success and latency.
- No written numerator/denominator or measurement point, so two dashboards disagree about the same SLI.
- A latency SLI whose threshold is not a histogram bucket edge, making the ratio uncomputable from the emitted metric.
- Alerting on raw error rate or single-window burn, which either pages late or flaps.
- Burn-rate expressions with no minimum-traffic guard on low-volume services.
- An SLO with no error-budget policy attached, so an exhausted budget changes nothing about release behavior.
- Targets copied from another company's blog instead of derived from what users of this product tolerate.

## Definition of done

- [ ] Every critical user journey has an SLI written as good events / valid events with the exact numerator, denominator, threshold, and measurement point.
- [ ] SLI type is stated (availability, latency, freshness, correctness, coverage, throughput) and fits the service type.
- [ ] SLO target and window are explicit, with the error budget computed in minutes or events.
- [ ] A written error-budget policy exists and is agreed with the owners before the budget is first exhausted.
- [ ] Alerts implement multiwindow multi-burn-rate with the 14.4/6/1 defaults (or documented deviations), pages for fast burn, tickets for slow burn.
- [ ] Low-traffic guards are in place so burn alerts cannot fire on a handful of events.
- [ ] The latency SLO threshold exists as a histogram bucket edge in the underlying metric.
