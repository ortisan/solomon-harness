# Operational Docs: Runbooks and User Guides

This skill governs operational documentation: incident runbooks with a fixed anatomy (preconditions, steps, verification, rollback), the alert-to-runbook link that makes them reachable at 3 a.m., task-oriented user guides, and user-facing changelogs. The stance: a runbook is executed under stress by someone who did not write it, so every ambiguity in it is an incident-time delay you chose in advance.

## Runbook anatomy

Write for an on-call engineer woken at 3 a.m. who has never touched this service. Every runbook has the same eight sections, in this order:

1. **Title and trigger**: the runbook title matches the alert name exactly, so search works during an incident. State the symptom as the operator sees it.
2. **Impact and severity**: who or what is affected, the default severity, and whether this pages or waits for morning.
3. **Preconditions**: everything needed before step one — VPN, the right kubectl context, database read access, break-glass roles, CLI tools with versions. Listing these up front converts "step 6 failed with permission denied at 3:20 a.m." into a 30-second pre-check.
4. **Diagnosis**: links to the exact dashboard panels and log queries, with the queries written out so they can be pasted, and what a healthy versus unhealthy result looks like.
5. **Remediation**: numbered steps, one action per step, every command copy-pasteable with placeholders defined, and the expected output stated after each step that produces output. Flag destructive commands explicitly and state what they destroy.
6. **Verification**: the specific metric, probe, or query that proves recovery, and how long to watch it before standing down. "It seems fine" is not a verification step.
7. **Rollback**: how to undo the remediation if it makes things worse, and the signal that says to trigger it.
8. **Escalation**: who to page next, with a concrete threshold — for example, escalate after 20 minutes without progress — and what context to hand over.

Keep the executable part of a runbook under roughly two pages; background and architecture belong in linked explanation pages, not between steps 4 and 5.

## Alert-linked runbooks

- Every paging alert carries a `runbook_url` annotation (Alertmanager annotations, PagerDuty runbook field, or the equivalent in your alerting stack) pointing at exactly one runbook. The mapping is one-to-one: an alert that fires without a runbook link is itself a bug — file it and fix it like one.
- Runbooks are drilled, not trusted. Exercise each critical runbook in a scheduled game day at least quarterly, in staging or a controlled window, and record `last_drilled` in the page front matter. A runbook undrilled for two quarters is stale and gets flagged in the staleness report like any other page.
- Drills are where copy-paste errors, permission gaps, and renamed dashboards surface cheaply. Update the runbook in the same PR that closes the drill.

## User guides: task orientation

User guides are organized by what the user wants to accomplish, never by the product's feature tree or menu structure:

- Title each guide with the task ("Export a monthly report"), not the feature ("The Reports module").
- Open with prerequisites, then numbered steps with the expected result after any step that changes what the user sees, then a verification step that confirms the goal was reached.
- Close with a troubleshooting section covering the top failures — sourced from real support tickets and search logs, not from the author's guesses about what might go wrong.
- Route feature-by-feature detail to reference pages and link them; a guide that tours every option stops being followable.

## Changelogs

Follow Keep a Changelog 1.1 with Semantic Versioning 2.0.0. Group entries under Added, Changed, Deprecated, Removed, Fixed, and Security. Write each entry for the user who upgrades — what changed for them and what they must do — not as a relabeled commit log. Breaking changes and required migration steps lead the release entry, never hide mid-list.

## Common pitfalls

- Runbooks that begin with architecture background; the operator needs step one, and theory belongs in a linked page.
- Prerequisites discovered mid-procedure — a missing role or tool found at step 6 costs the outage its quickest path to recovery.
- Commands that were never run as written: wrong flags, renamed resources, or output that no longer matches. Only drills catch these before an incident does.
- No rollback section, forcing the operator to improvise the undo of a half-applied fix under pressure.
- Escalation as a name with no threshold, so engineers grind alone for an hour before paging the person who knows.
- Alerts without `runbook_url`, leaving the on-call engineer searching a wiki while the error budget burns.
- User guides organized by menu structure, which forces users to already know which feature solves their problem.
- Changelog entries like "misc fixes and improvements" that tell an upgrading user nothing.

## Definition of done

- [ ] The runbook contains all eight sections in order: title/trigger, impact and severity, preconditions, diagnosis, remediation, verification, rollback, escalation.
- [ ] Every command is copy-pasteable, placeholders are defined, expected output is stated, and destructive commands are flagged.
- [ ] Verification names a concrete metric or probe and a watch duration; rollback states its trigger signal.
- [ ] Escalation names the next responder and a time-based threshold.
- [ ] Every paging alert links exactly one runbook via `runbook_url`; the title matches the alert name.
- [ ] The runbook has been drilled, `last_drilled` is recorded, and drill findings are folded back into the page.
- [ ] User guides are task-titled, carry prerequisites, numbered steps with expected results, a verification step, and troubleshooting sourced from real failures.
- [ ] The changelog follows Keep a Changelog categories, is written for users, and leads with breaking changes and migration steps.
