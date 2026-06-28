## Alerting


- Alert on symptoms (SLO burn), not causes. A CPU-at-80% alert that does not map to user pain is noise; a "latency SLO burning fast" alert is signal.
- Use multi-window, multi-burn-rate alerting (Google SRE model). For a 99.9% monthly SLO:
  - Page (fast burn): 14.4x burn rate over a 1h window confirmed by a 5m window (consumes ~2% of the monthly budget in 1h).
  - Page (medium burn): 6x burn rate over 6h confirmed by 30m (~5% of budget).
  - Ticket (slow burn): 1x-3x burn rate over 1d-3d (~10% of budget), no page.
  The short confirmation window kills flapping; the long window catches steady erosion.
- Every alert carries: a severity, an owner, a runbook link, and a clear "what the user is experiencing" statement. An alert with no runbook is an incomplete deliverable.
- Page only for user-facing, time-critical, SLO-threatening conditions. Everything else is a ticket. Track alert precision (fraction of pages that were actionable) and prune anything below ~90%.
- Configure deduplication, grouping, and inhibition so one root cause produces one page, not fifty.
