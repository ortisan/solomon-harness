## Incident response and runbooks


Reduce time-to-mitigation. Roles and runbooks are decided before the incident, not during it.

- **Severity levels** with explicit response targets: SEV1 (full outage or data loss, immediate page, all-hands), SEV2 (major degradation, page on-call), SEV3 (minor, business-hours ticket), SEV4/5 (low impact). Define each in writing so paging is unambiguous.
- **Roles**: Incident Commander (owns the response, makes decisions, does not debug), Operations/Ops Lead (executes the fixes), Communications Lead (status page and stakeholder updates), Scribe (timeline). For small incidents one person may hold several, but the IC role is always explicit.
- **Track the operational metrics**: MTTD (detect), MTTA (acknowledge), MTTR (resolve), MTBF (between failures). Drive MTTA and MTTR down with better alerts and runbooks.
- **On-call**: PagerDuty or Opsgenie with a tiered escalation policy and a documented secondary. Cap pages per shift; sustained pager fatigue is an incident in itself. Every page must be actionable.
- **Runbook structure**, one per known failure mode: symptoms and the alert that fires, dashboards/queries to confirm, step-by-step mitigation, escalation path, and post-mitigation verification. Keep them next to the alert that triggers them.
- **Alerts**: symptom-based (user-facing SLO burn), not cause-based noise. Every alert links to a runbook. Delete alerts nobody acts on.
- **Blameless postmortem** within 5 business days for every SEV1/SEV2: timeline, contributing factors, what went well, action items with owners and due dates tracked to closure. Blame the system and the gaps, never the engineer.
