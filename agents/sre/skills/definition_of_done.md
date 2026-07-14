---
name: definition-of-done
description: Defines the exit gate for reliability work, naming how SLO, alerting, failover, backup, and postmortem checklist items get falsely marked done on paper. Use when closing out a reliability change or deciding whether a service is ready to ship against the SRE definition of done.
---

# SRE Definition of Done

The exit gate for reliability work: a change ships only when every item below holds, from SLOs and burn-rate alerts to a drilled DR path. The pitfalls name the usual ways this checklist gets ticked on paper while the production risk remains.

## Common pitfalls

- SLOs declared done with one global target or a calendar-month window — a broken critical journey hides behind healthy traffic and the budget resets on the 1st, so the per-journey error-budget item is unmet.
- Alerts that page on raw error counts instead of multiwindow burn rates, or that link to no runbook — they fire on harmless blips, miss slow budget drains, and strand the responder without a mitigation path.
- Failover or rollback marked verified because the topology exists on paper — an N+1 multi-AZ design or a canary rollback that has never been exercised is a hypothesis, not a control.
- Backups counted as done without a timed, verified restore — an unrestored backup can be unreadable during the real disaster, which is exactly when the 3-2-1 item is supposed to pay off.
- RTO/RPO recorded while asynchronous replication lag silently exceeds the RPO — the design is compliant on paper and loses more data than allowed; lag must alert before the objective is breached.
- Runbooks written but never exercised in a game day, or stored away from the alert that triggers them — responders cannot find or trust them mid-incident, so the runbook item is decorative.
- Postmortem action items closed as discussed, with no owner or due date — the same failure recurs, failing the owned, dated action-items clause.

## Definition of done


- [ ] Every critical user journey has an SLI, an SLO with an explicit rolling window, and a documented error-budget policy.
- [ ] Multiwindow burn-rate alerts page on fast burn and ticket on slow burn; every alert links to a runbook.
- [ ] No single points of failure; N+1 capacity and at least two AZs verified by an actual failover test.
- [ ] Outbound calls have timeouts, backoff-with-jitter retries, and a circuit breaker or load-shedding fallback.
- [ ] Infrastructure is in version-controlled IaC with remote locked state; no manual production changes.
- [ ] Deploys are canary or blue/green with automated rollback that completes in minutes; rollback has been exercised.
- [ ] Schema migrations are backward-compatible (expand/contract).
- [ ] Load test with defined RPS and p95/p99 latency and error-rate thresholds passes at 2x expected peak; a soak test ran clean.
- [ ] Severity levels, on-call escalation, and incident roles are documented; runbooks exist for known failure modes.
- [ ] RTO and RPO are defined per service; backups follow 3-2-1 with one immutable copy and a verified restore.
- [ ] A DR failover drill ran within the agreed cadence and met RTO/RPO.
- [ ] STRIDE threats reviewed (DoS mitigations in place); secrets in a manager, not git; error messages stripped of internals.
- [ ] New code has unit and integration tests with all external services mocked; TDD followed.
- [ ] Blameless postmortems for SEV1/SEV2 closed with owned, dated action items.
- [ ] Branch follows Git Flow; commits follow Conventional Commits with no emojis.
