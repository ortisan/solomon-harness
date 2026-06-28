# Dependency and Risk Management

Keep a live RAID log so that cross-team dependencies and risks are named, scored, owned, and escalated before they become spillover. The Scrum Master owns the log as a coordination artifact, not a compliance form: every entry has an owner, a date, a trigger, and a response, and every open risk or external dependency is mirrored as a tracked issue in project memory so the backlog and the RAID never drift apart.

## RAID log structure and ownership

RAID is four registers maintained together:

- **Risks** — uncertain future events that would hurt scope, schedule, cost, or quality. Threats and opportunities both qualify. Each has probability, impact, a response strategy, and an owner.
- **Assumptions** — things taken as true but not yet verified. An assumption that proves false becomes a risk or an issue, so each carries a validation owner and a check-by date. Unvalidated assumptions are the most common source of late surprises.
- **Issues** — risks that have already materialized, or blockers happening now. These need resolution, not mitigation. An issue with no owner and no due date is not being managed.
- **Dependencies** — work this team needs from another team (inbound) or another team needs from this team (outbound). Each records the predecessor, the successor, the agreed delivery date, and the interface contract.

Required fields per entry: id, type (R/A/I/D), title, description, owner (a named person or specialist, never "the team"), raised date, target/review date, status, and for risks the probability and impact. Review the whole log at sprint planning (see `sprint_planning`), and review red items and active issues at every standup (see `status_meetings_and_ceremonies`). Groom the log weekly alongside the backlog (see `backlog_management`): close stale entries, re-score, and confirm owners are still correct.

## Scoring risks and exposure

Use a 5x5 probability-impact matrix. Probability bands: 1 very low (<10%), 2 low (10-30%), 3 medium (30-50%), 4 high (50-70%), 5 very high (>70%). Impact 1-5 calibrated against the milestone: 1 is cosmetic, 3 costs roughly a sprint or a meaningful budget slice, 5 threatens the release date or a hard constraint.

Exposure = probability x impact (1-25). Act on the band, not the raw number:

- 1-4 (low): log and monitor; revisit at weekly grooming.
- 5-9 (medium): assign an owner and a written mitigation; review each sprint.
- 10-14 (high): active mitigation now, a named contingency, and a tracked issue via `log_issue`.
- 15-25 (critical): escalate immediately, fund the contingency, and put it on the standup agenda until the band drops.

For schedule and cost risks, also compute expected value: EMV = probability(%) x impact (in days or currency). A 40% chance of a 10-day slip is a 4-day expected hit; size contingency reserves against the summed EMV of open threats, not against the worst single case. Re-score on every status change; a risk whose probability is climbing toward its trigger is more urgent than its current band suggests.

## Dependency and critical-path mapping

Map dependencies before committing a milestone. Classify by direction (inbound vs outbound) and by relationship: finish-to-start (FS, the default), start-to-start (SS), finish-to-finish (FF), and the rare start-to-finish (SF). Flag every cross-team and external-vendor dependency explicitly; these are the ones that slip outside your control.

Run the Critical Path Method on the milestone's task network. For each task compute early start/finish and late start/finish; total float = late start - early start = late finish - early finish. Tasks with total float = 0 form the critical path: any slip there slips the release one-for-one. Track near-critical paths too: any chain whose float is at or below one sprint of buffer is one bad estimate away from becoming critical, so it gets the same attention.

For chains with shared resources or deep external dependencies, apply Critical Chain buffers (CCPM): a project buffer of roughly 50% of the aggregated safety stripped from the critical chain, plus feeding buffers where non-critical chains merge into it. Manage by buffer consumption, not by task-level dates: if buffer burn outpaces critical-chain completion (red on the fever chart), act before the deadline is at risk. The `software_architect` agent owns the technical contract at a dependency boundary; the Scrum Master owns the date, the owner, and the escalation.

## Mitigation, contingency, and reserves

Separate the two, because they are different decisions:

- **Mitigation** is proactive: reduce probability or impact now. For threats use avoid, transfer, mitigate, or accept; for opportunities use exploit, share, enhance, or accept (PMI risk-response taxonomy). Spend mitigation effort where exposure x cost-to-fix is worst.
- **Contingency** is the pre-agreed plan you execute *if* the risk triggers. Every medium-or-higher risk needs a written trigger condition (the observable event that fires the plan) and the contingency itself. A contingency with no trigger never gets invoked in time.

Hold two reserve types and do not blur them: a contingency reserve for known risks (inside the milestone baseline, drawn down by the Scrum Master as triggers fire), and a management reserve for unknown-unknowns (outside the baseline, released only by the sponsor or product owner). Record every drawdown against an issue so reserve burn is auditable. Accepting a risk rather than mitigating it is a legitimate choice, but record it with `save_decision` including the rationale and who approved it.

## Escalation paths

Define the ladder before you need it. Each rung has an owner and a decision SLA:

1. Within the team: the Scrum Master and the owning specialist resolve it. Blockers raised at standup get an owner within the same day.
2. Cross-team: if a dependency owner cannot commit to the agreed date, escalate to the peer team's lead within 24 hours.
3. Product owner / sponsor: scope, budget, or release-date trade-offs, and any management-reserve draw.

Escalation triggers are objective, not mood-based: a critical-band risk (>=15), an issue blocking a critical-path task, a dependency that will miss its date, or buffer burn in the red. Time-box every escalation: if the rung above does not decide within its SLA (48 hours is a sane default for cross-team), escalate one level higher rather than waiting. Encode owner and accountable party with a RACI on the dependency so "who decides" is never the bottleneck. Use `log_handoff` to record the cross-team transfer and the agreed contract so the next team has the context without a meeting.

## Persisting RAID in project memory

The RAID log lives in project memory, not a side spreadsheet, so it survives sessions and is visible to every agent:

- `log_issue` — open one tracked issue for each medium-or-higher risk and each external/cross-team dependency, labelled `risk` or `dependency`, with owner, target date, and trigger in the body. Created through `scripts/scrum-master.sh` so it is templated (see `tooling_scriptsscrum_mastersh`). A materialized risk (an Issue in RAID terms) is logged the same way and linked to the originating risk.
- `get_open_issues` — this is the live RAID query. Pull it at sprint planning to size capacity against open exposure, and at standup to drive the red list. If an open risk is not returned here, it is not being managed.
- `save_decision` — record risk acceptances, chosen response strategies, and reserve drawdowns with rationale and approver, so the audit trail outlives the conversation.
- `log_handoff` — capture every cross-team dependency transfer with its interface contract and agreed date.
- `create_milestone` — tie contingency dates and dependency deadlines to the release scope (see `milestones`); a dependency due after the milestone's due date is a planning error, surface it immediately.
- `get_latest_activity` — reconcile the RAID against what actually shipped before closing the milestone.

## Common pitfalls

- An entry with no named owner or no date: it is a note, not a managed risk, and nobody will act on it. Reject it.
- Risks scored once at kickoff and never re-scored. Probability and impact move; a stale score hides a risk climbing toward its trigger.
- Conflating risk and issue: writing a materialized blocker in the risk register means it gets a mitigation plan instead of the resolution it needs now.
- Mitigation with no contingency, or contingency with no trigger condition. The plan exists but never fires because nobody defined the observable event that starts it.
- Internal dependencies tracked but external/vendor ones left implicit. The dependencies outside your control are exactly the ones that slip.
- Treating only the zero-float critical path and ignoring near-critical chains; a chain with one sprint of float flips to critical after a single missed estimate.
- Open risks and dependencies kept in a doc that `get_open_issues` does not return, so the backlog and the RAID diverge and the standup works from stale data.
- Escalation with no SLA: a blocker sits unowned for days because no rule says when to push it up.
- Padding every task estimate privately instead of pooling safety into an explicit, managed buffer (CCPM); the schedule lies and the slack is invisible.
- Accepting a high-exposure risk without recording the decision and approver via `save_decision`, leaving no accountability when it materializes.

## Definition of done

- [ ] A RAID log exists for the milestone with every entry carrying type, owner, raised date, review date, and status.
- [ ] Every risk is scored on the 5x5 matrix; exposure band drives the response, and EMV is computed for schedule/cost risks.
- [ ] Each medium-or-higher risk has a written mitigation, a contingency, and an explicit trigger condition.
- [ ] Dependencies are classified (direction and FS/SS/FF/SF), cross-team and external ones flagged, and mapped onto the critical path with total float computed.
- [ ] Near-critical chains (float at or below one sprint) are tracked, and CCPM buffers are sized and monitored by consumption where applicable.
- [ ] Contingency and management reserves are separated; every drawdown is recorded against an issue.
- [ ] Every open medium-or-higher risk and every external dependency is a tracked issue via `log_issue` and appears in `get_open_issues`.
- [ ] Cross-team transfers are recorded with `log_handoff`; risk acceptances and reserve draws with `save_decision`.
- [ ] An escalation ladder with named owners and decision SLAs is documented, and red-band items are on the standup agenda until they clear.
- [ ] The log is reviewed at sprint planning, red items at every standup, and the full register at weekly grooming.
