---
name: alerting
description: Governs alert design covering symptom-based paging over cause-based noise, the P1-P4 severity ladder, numeric pager-hygiene targets, mandatory runbooks, and the weekly alert review loop. Use when defining, reviewing, or pruning alert rules, assigning severities, or investigating pager fatigue and alert precision.
---

# Alerting

This skill sets the alerting standard: page on symptoms that map to user pain, keep a strict severity ladder, protect the pager with numeric hygiene targets, require a runbook on every alert, and run a review loop that deletes alerts as readily as it adds them. An alert is a product with a user — the responder at 3 a.m. — and it is designed to that user's needs.

## Symptom versus cause

Alert on symptoms (SLO burn, user-visible error rate, user-visible latency), not causes. A CPU-at-80-percent alert that does not map to user pain is noise; "availability SLO burning at 14.4x" is signal. Cause signals — disk filling, replica lag, pod restarts — belong on dashboards and as inhibited context, not as independent pages. The burn-rate thresholds and windows come from the slis_and_slos skill; this skill governs everything wrapped around them. One symptom, one page: use grouping, deduplication, and inhibition (in Alertmanager: `group_by`, and inhibition rules that mute cause alerts while the symptom alert is firing) so a single root cause cannot produce fifty notifications.

## Severity ladder

Every alert declares exactly one severity; anything unclassified defaults to ticket, never page.

- P1 — users are hurting now: fast SLO burn, hard down, data loss in progress. Page 24/7, acknowledge within 5 minutes, incident process starts immediately.
- P2 — users will be hurting soon: slow burn that will exhaust budget, redundancy lost (N+1 gone), certificate expiring inside the response window. Page during business hours or ticket with a next-business-day SLA, acknowledge within 1 hour.
- P3 — needs engineering attention this sprint: error-budget policy triggers, capacity trends, recurring self-recovering faults. Ticket only.
- P4 — informational: dashboard annotation or log, no notification at all. Most cause signals live here.

Severity encodes response, not embarrassment: if nobody would act differently within an hour, it is not a P1.

## Paging hygiene

A page must pass all four tests: user-impacting, urgent, actionable, and requiring human judgment. Fail any one and it is a ticket. Numeric targets this agent holds the system to:

- At most 2 paging incidents per 12-hour on-call shift, sustained. Above that, on-call does no project work and alert quality collapses into ack-and-ignore.
- Alert precision at or above 90 percent: track the fraction of pages that led to real action, and prune or demote anything below the bar.
- Threshold alerts hold a `for:` duration of 2 to 5 minutes so a single scrape blip cannot page; multiwindow burn-rate alerts get this behavior from their short window.
- Silences always carry an expiry and a reason during maintenance; the rule itself is never edited to shut it up.

## Runbooks and required metadata

Every alert ships with: severity, owning team, `runbook_url`, a link to the relevant dashboard, and a one-line statement of what the user is experiencing. An alert without a runbook is an incomplete deliverable and is rejected in review. The runbook states how to confirm the alert is real, the mitigation actions in order (rollback, drain traffic, disable the flag) before any diagnosis, and the escalation path. Mitigation first: the responder's job is to stop user pain, then find the cause. In this repo, alert rules and their runbook links are versioned files reviewed like code, with the annotations (severity, owner, runbook_url) validated in CI so a rule cannot merge without them.

## Alert review loop

Alerts rot: services change, thresholds drift, and last quarter's page becomes this quarter's noise. The loop that keeps them honest:

- Weekly, at on-call handoff: walk every page from the shift and give each a disposition — actioned (fine), needs tuning (threshold, window, or severity adjusted now), or delete. No page leaves the meeting without one.
- Rule of three: an alert that fires three consecutive times without human action is demoted or deleted; keeping it "just in case" trains responders to ignore the pager.
- Monthly: review pages per shift, precision, and time-to-acknowledge trends against the targets above.
- New alerts state, in the PR that adds them: which SLO or failure mode they protect, the expected frequency, and what the responder is supposed to do. If the answer to the last is "look around", it is a dashboard, not an alert.

## Common pitfalls

- Cause-based pages (CPU, disk, restarts) generating fatigue while an actual SLO burn goes unnoticed.
- Alerts with no runbook, no owner, or no severity, forcing the responder to reverse-engineer intent mid-incident.
- Paging for conditions with no human action available — the automation should have handled it.
- Editing a rule to silence it during maintenance instead of using an expiring silence, then forgetting to restore it.
- No grouping or inhibition, so one root cause floods the pager and buries the real signal.
- Precision never measured, so the pager degrades into background noise nobody trusts.

## Definition of done

- [ ] Every page maps to a symptom: an SLO burn or a directly user-visible failure; cause signals are dashboards or inhibited context.
- [ ] Every alert declares severity, owner, runbook_url, dashboard link, and a user-impact statement, enforced by CI validation.
- [ ] The runbook exists, leads with mitigation, and has been exercised at least once by someone other than its author.
- [ ] Paging load and precision are tracked against the targets: at most 2 pages per shift, at least 90 percent precision.
- [ ] Grouping, deduplication, and inhibition are configured so one root cause produces one page.
- [ ] The weekly disposition review and rule-of-three pruning are operating, with deletions recorded.
- [ ] Every new alert's PR states the protected SLO or failure mode and the expected responder action.
