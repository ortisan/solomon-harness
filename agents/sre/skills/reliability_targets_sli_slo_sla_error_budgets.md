---
name: reliability-targets-sli-slo-sla-error-budgets
description: Governs SLI, SLO, and SLA definitions, error-budget math over a rolling window, the error-budget policy, and multi-window multi-burn-rate alerting thresholds. Use when defining a new reliability target, writing an error-budget policy, or configuring burn-rate alerts for a critical user journey.
---

# Reliability Targets: SLI, SLO, SLA, and Error Budgets

Define reliability before you defend it, then run the service against an error budget instead of chasing 100%.

Reliability is a product decision expressed as numbers: which user-facing signal counts, what target it must hold over what window, and how much failure you are allowed to spend. Get these three terms exactly right, because teams routinely conflate them and then argue past each other. This skill sets the targets; `resilience_and_load_shedding` consumes the burn-rate signal to protect the budget, `release_engineering_and_progressive_delivery` gates promotion on it, and `incident_response_and_runbooks` turns a burn alert into a response.

## SLI, SLO, SLA precisely

- **SLI (indicator):** a ratio of good events to valid events, measured as close to the user as possible (load balancer or client RUM, not server-side only, because the user feels edge failures the server never sees). Standard categories: availability, latency, throughput, correctness, freshness, durability. Example latency SLI: "proportion of valid requests served faster than 300 ms".
- **SLO (objective):** the target for an SLI over an explicit rolling window. Use a 28- or 30-day rolling window, not a calendar month, so the number does not reset on the 1st and hide a bad week. State the window every time. Example: "99.9% of requests succeed over 28 days". Set one SLO per critical journey, not a single global number that averages a broken checkout into a healthy homepage.
- **SLA (agreement):** the externally contracted, penalty-bearing promise. Always set the SLA looser than the internal SLO, so you breach the SLO and react well before you breach the contract. If the SLA is 99.9%, run the SLO at 99.95%.

## Error budget math

The **error budget = 1 - SLO**: the permitted unreliability over the window. You spend it on releases, experiments, and risk; when it runs out you stop spending. Downtime equivalents per 30-day window:

| SLO | Budget (% of requests) | ~Downtime / 30 days |
| --- | --- | --- |
| 99% | 1% | 7h 12m |
| 99.9% | 0.1% | 43m 12s |
| 99.95% | 0.05% | 21m 36s |
| 99.99% | 0.01% | 4m 19s |
| 99.999% | 0.001% | 26s |

A 99.9% monthly SLO gives a 43.2-minute budget. (The `high_availability` "nines" table quotes 43.8 min because it uses a 30.44-day average month; both are correct, they just use different window bases.)

## Error budget policy

Write the policy down and get product sign-off, because the policy is what makes the SLO real rather than decorative:

- **Budget exhausted:** freeze feature deploys and redirect the team to reliability work until the budget recovers.
- **Budget healthy:** ship faster, take more risk, run experiments. A consistently full budget means the SLO is too loose or you are shipping too slowly.

This is the contract between reliability and velocity, and it is the same input the pipeline reads to block or allow promotion.

## Multi-window, multi-burn-rate alerting

Alert on the **rate** at which you are spending the budget, not on a raw error threshold. The **burn rate** is how many times faster than sustainable you are consuming budget: `burn = error_rate / (1 - SLO)`. At burn rate 1 you would exhaust the whole window's budget exactly at the window's end; time-to-exhaustion is `window / burn`.

Use the Google SRE Workbook multi-window, multi-burn-rate config. Each alert pairs a long window (the trigger) with a short window (a recent-burn confirmation), so the alert clears quickly once the spike stops and does not fire on an already-recovered blip:

| Severity | Burn rate | Long window | Short window | Budget consumed when it fires | Action |
| --- | --- | --- | --- | --- | --- |
| Page (fast) | 14.4x | 1h | 5m | 2% in 1h | Page immediately |
| Page (medium) | 6x | 6h | 30m | 5% in 6h | Page |
| Ticket (slow) | 1x | 3d | 6h | 10% in 3d | Open a ticket |

**Worked burn-rate example.** SLO 99.9%, so the sustainable error rate is 0.1%. If the measured error rate over the last hour is 1.44%, the burn rate is `1.44% / 0.1% = 14.4`. That trips the fast-burn page, and at 14.4x you would exhaust a 30-day budget in `30d / 14.4 ≈ 2.1 days`, which is why it pages a human now rather than waiting. A 0.6% error rate over 6 hours is burn rate 6, the medium page. A steady 0.1% is burn rate 1, on track to spend exactly the budget, a ticket not a page.

Alert on tail percentiles (p95/p99), not the mean, so a long tail that hurts real users is not averaged away.

## Common pitfalls

- Chasing 100% reliability: it leaves no budget to ship and costs exponentially more per nine. The correct target is below 100%. Reviewers reject an SLO with no headroom to deploy.
- One global SLO for everything: a broken critical journey is hidden by healthy traffic elsewhere. Set per-journey SLOs.
- Measuring the SLI server-side only: users experience edge and client failures the server never records, so the number is optimistic. Measure at the load balancer or client.
- Calendar-month windows: the budget resets on the 1st and masks a bad end-of-month week. Use a rolling 28/30-day window and state it.
- SLA equal to or tighter than the SLO: you breach the contract the moment you breach your own target, with no reaction time. Keep the SLA looser.
- Alerting on a raw error count instead of burn rate: it pages on harmless brief spikes and misses slow burns that quietly drain the budget. Use multi-window multi-burn-rate.
- Alerting on the mean latency: a bad tail is averaged away and real user pain goes unpaged. Alert on p95/p99.
- An error budget with no written, signed-off policy: nobody changes behavior when it is spent, so the SLO is decorative. The policy is the contract.

## Definition of done

- [ ] Each critical user journey has an SLI defined as good/valid events, measured at or near the user.
- [ ] Each SLI has an SLO with an explicit rolling window (28 or 30 days), not a calendar month.
- [ ] The SLA, where one exists, is looser than the internal SLO.
- [ ] The error budget is computed as 1 - SLO and tracked against the window.
- [ ] A written error-budget policy is signed off by product and wired into the deploy pipeline (freeze on exhaustion).
- [ ] Multi-window, multi-burn-rate alerts (fast/medium page, slow ticket) are configured and link to runbooks.
- [ ] Latency SLOs and alerts use tail percentiles (p95/p99), not the mean.
- [ ] SLO definitions, alert rules, and the budget policy are committed as code, reviewed, and version-controlled per Git Flow and Conventional Commits.
