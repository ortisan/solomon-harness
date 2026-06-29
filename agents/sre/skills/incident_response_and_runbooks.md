# Incident Response and Runbooks

Reduce time-to-mitigation by deciding roles, severities, and runbooks before the incident, not during it.

An incident is any unplanned disruption or degradation that needs a coordinated response. The goal during one is to mitigate first and diagnose second: stop the customer pain, then find the cause. Everything that makes that fast is decided in advance. The blameless postmortem afterward is what turns one incident into a permanent improvement.

## Incident command roles

Adapt the Incident Command System. For anything above a minor incident, assign these explicitly, even if one person holds several at the start:

- **Incident Commander (IC):** owns the response and makes decisions. The IC coordinates and does not debug; a commander with their head in a terminal stops commanding.
- **Operations / Ops Lead:** the hands on keyboard who executes mitigations and changes, directed by the IC.
- **Communications Lead:** owns the status page and stakeholder and customer updates on a fixed cadence, freeing the IC to run the response.
- **Scribe:** maintains the timeline in real time (UTC timestamps, decisions, actions, hypotheses). The scribe's notes become the postmortem.

## Severity matrix

Define severity in writing so paging is unambiguous and nobody negotiates it mid-incident:

| Sev | Definition | Example | Response | Page | Comms cadence |
| --- | --- | --- | --- | --- | --- |
| SEV1 | Full outage, data loss, or security breach | Checkout down globally | Immediate, all-hands, IC named | 24/7 | Every 30 min + public status page |
| SEV2 | Major degradation, SLO at risk | One region down, p99 at 2x | Page on-call, IC named | 24/7 | Hourly |
| SEV3 | Minor, single feature, workaround exists | Non-critical job failing | Business-hours ticket | No | Daily |
| SEV4/5 | Cosmetic or low impact | UI typo, slow non-critical report | Backlog | No | None |

## Operational metrics

Track and drive these down:

- **MTTD** (mean time to detect): instrument-quality problem; good symptom alerts shrink it.
- **MTTA** (mean time to acknowledge): paging-quality problem; target SEV1 MTTA < 5 min.
- **MTTR** (mean time to resolve/mitigate): runbook- and rollback-quality problem; target SEV1 MTTR < 60 min.
- **MTBF** (mean time between failures): reliability of the underlying system.

MTTR and change-failure rate are also two of the DORA stability metrics (see `dora_metrics_and_change_management`). On-call uses a tiered escalation policy (PagerDuty or Opsgenie) with a documented secondary; cap pages per shift, because sustained pager fatigue is itself an incident. Every alert is symptom-based, links to a runbook, and is actionable, or it gets deleted.

## Runbook anatomy

One runbook per known failure mode, stored next to the alert that triggers it:

1. **Trigger:** the exact alert and its query.
2. **Symptoms and impact:** what users see and which SLO is burning.
3. **Verify:** dashboards and queries to confirm the diagnosis.
4. **Mitigate:** numbered, copy-pasteable steps; prefer rollback or flag-off over a hot fix.
5. **Rollback:** the one-command revert path.
6. **Escalate:** who and when, if mitigation fails.
7. **Verify recovery:** how to confirm the SLO has stopped burning.
8. **Metadata:** owner and last-reviewed date.

Exercise runbooks during game days (see `load_and_resilience_testing`); a runbook nobody has run is untested.

## Blameless postmortem

Within 5 business days for every SEV1 and SEV2, write a blameless postmortem. Blame the system and the gaps, never the engineer; the test is whether someone can say "I made the change that triggered this" without fear. Track action items to closure as backlog issues, each with an owner, a due date, and a type (prevent, detect, or mitigate). A template skeleton:

```markdown
# Postmortem: <title> (<date>, SEVx)
Status: draft | reviewed | actions-tracked
Authors / IC:
Impact: users affected, duration, SLO/error-budget burned, SLA/revenue
Detection: alert vs customer report; MTTD / MTTA

## Timeline (UTC)
- 14:02 first error spike on /checkout
- 14:07 on-call paged, acknowledged (MTTA 5m)
- 14:21 mitigated by rolling back deploy abc123

## Contributing factors (5 Whys; no single root cause)

## What went well

## What went poorly / where we got lucky

## Action items
| # | Action | Owner | Due | Tracking | Type |
| 1 | Add canary check on /checkout error rate | @a | 2026-07-10 | #123 | detect |
```

## Common pitfalls

- No named IC on a SEV1: decisions stall and several people debug the same thing. Reviewers reject a major-incident process without an explicit commander role.
- The IC also debugging: coordination collapses. Keep the IC hands-off the keyboard.
- Cause-based alerts instead of symptom-based: noisy pages that do not map to user pain, driving fatigue and missed real alerts. Alert on SLO burn, link each to a runbook.
- Runbooks not stored with the alert, or never exercised: responders cannot find them at 3am or they are stale. Co-locate and test them in game days.
- Diagnosing before mitigating: the outage runs longer while the team chases root cause. Mitigate first, diagnose in the postmortem.
- Postmortems that name and shame, or that ship with untracked action items: people hide incidents and the same failure recurs. Keep them blameless and track items to closure.
- Treating MTTA as fine because someone eventually looked: unacknowledged pages mean the escalation policy is broken. Measure and alert on MTTA.

## Definition of done

- [ ] A written severity matrix defines each level, its paging rule, and its comms cadence.
- [ ] Incident command roles (IC, Comms, Ops, Scribe) are defined and assignable, with the IC explicit on every SEV1/SEV2.
- [ ] On-call uses tiered escalation with a documented secondary and a per-shift page cap.
- [ ] Every alert is symptom-based, actionable, and links to a runbook stored next to it.
- [ ] Runbooks follow the standard anatomy and are exercised in game days.
- [ ] MTTD, MTTA, MTTR, and MTBF are measured, with targets set per severity.
- [ ] A blameless postmortem is written within 5 business days for every SEV1/SEV2, with action items tracked to closure as backlog issues.
- [ ] Runbooks, postmortems, and alert definitions are committed as code, reviewed, and version-controlled per Git Flow and Conventional Commits.
