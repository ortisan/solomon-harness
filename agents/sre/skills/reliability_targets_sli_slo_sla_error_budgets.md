# SRE Best Practices

Operational standard for running production services in solomon-harness: how to set reliability targets, build deployment pipelines, test under load, respond to incidents, and recover from disasters.

## Reliability targets: SLI, SLO, SLA, error budgets


Define reliability before you defend it. Pick SLIs that reflect user pain, set SLOs against them, and treat the gap to perfection as a budget you are allowed to spend.

- **SLI**: a ratio of good events to valid events, measured as close to the user as possible (load balancer or client RUM, not server-side only). Standard categories: availability, latency, throughput, correctness, freshness, durability. Example latency SLI: "proportion of valid requests served faster than 300 ms".
- **SLO**: target for an SLI over a rolling window (use 28 or 30 days, not calendar months). State the window explicitly. Example: "99.9% of requests succeed over 28 days".
- **SLA**: the externally contracted, penalty-bearing promise. Always set the SLA looser than the internal SLO so you breach the SLO and react before you breach the contract.
- **Error budget** = 1 − SLO. This is the permitted unreliability. Spend it on releases and experiments; stop spending when it runs out.

Error budget per 30-day window (downtime equivalent):

| SLO | Budget (% requests) | ~Downtime / 30 days |
| --- | --- | --- |
| 99% | 1% | 7h 12m |
| 99.9% | 0.1% | 43m 12s |
| 99.95% | 0.05% | 21m 36s |
| 99.99% | 0.01% | 4m 19s |
| 99.999% | 0.001% | 26s |

- **Error budget policy** (write it down, get sign-off from product): when the budget is exhausted, freeze feature deploys and redirect the team to reliability work until the budget recovers. When the budget is healthy, ship faster and take more risk. The policy is the contract that makes the SLO real.
- **Burn-rate alerting**, multiwindow multi-burn-rate (Google SRE workbook pattern). Alert on budget consumption rate, not raw thresholds:
  - Fast burn, page: 14.4x burn over a 1h window (with a 5m short window to confirm) — consumes 2% of a 30-day budget in one hour.
  - Medium burn, page: 6x over 6h (with a 30m short window) — 5% of budget in six hours.
  - Slow burn, ticket: 1x over 3 days (with a 6h short window) — 10% of budget over the window.
- Pitfalls: chasing 100% (the right target is below 100%, leaving room to ship); averaging away tail latency (alert on p95/p99, not the mean); measuring success server-side while users see failures at the edge; one giant 99.99% SLO for everything instead of per-critical-journey SLOs.
