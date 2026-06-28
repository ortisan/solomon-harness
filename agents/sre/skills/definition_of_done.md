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
