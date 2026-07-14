---
name: dependency-and-risk-management
description: Governs the live RAID log (risks, assumptions, issues, dependencies) so cross-team dependencies and risks are named, scored, owned, and escalated before they become spillover. Use when logging a new risk, assumption, or external dependency, or reviewing whether the RAID log and backlog have drifted apart.
---

# Dependency and Risk Management

Keep a live RAID log so cross-team dependencies and risks are named, scored, owned, and escalated before they become spillover. The Scrum Master owns the log as a coordination artifact, not a compliance form: every entry has an owner, a date, a trigger, and a response, and every open risk or external dependency is mirrored as a tracked issue in project memory so the backlog and the RAID never drift apart.

## RAID log structure and ownership

RAID is four registers maintained together:

- **Risks** — uncertain future events that would hurt scope, schedule, cost, or quality. Threats and opportunities both qualify. Each has probability, impact, a response strategy, and an owner.
- **Assumptions** — things taken as true but not yet verified. An assumption that proves false becomes a risk or an issue, so each carries a validation owner and a check-by date. Unvalidated assumptions are the most common source of late surprises.
- **Issues** — risks that have already materialized, or blockers happening now. These need resolution, not mitigation. An issue with no owner and no due date is not being managed.
- **Dependencies** — work this team needs from another team (inbound) or another team needs from this team (outbound). Each records the predecessor, the successor, the agreed delivery date, and the interface contract.

Required fields per entry: id, type (R/A/I/D), title, description, owner (a named person or specialist, never "the team"), raised date, target/review date, status, and for risks the probability and impact. Review the whole log at sprint planning (see `sprint_planning`), and review red items and active issues at every standup (see `sprint_planning`). Groom the log weekly alongside the backlog (see `backlog_management`): close stale entries, re-score, and confirm owners are still correct.

## Scoring risks on the 5x5 matrix

Use a 5x5 probability-impact matrix. Probability bands: 1 very low (<10%), 2 low (10-30%), 3 medium (30-50%), 4 high (50-70%), 5 very high (>70%). Impact 1-5 is calibrated against the milestone: 1 is cosmetic, 3 costs roughly a sprint or a meaningful budget slice, 5 threatens the release date or a hard constraint.

Exposure = probability x impact (1-25). The grid below fixes the band an entry lands in and the response that band requires:

| P \ I | 1 | 2 | 3 | 4 | 5 |
| --- | --- | --- | --- | --- | --- |
| 5 | 5 | 10 | 15 | 20 | 25 |
| 4 | 4 | 8 | 12 | 16 | 20 |
| 3 | 3 | 6 | 9 | 12 | 15 |
| 2 | 2 | 4 | 6 | 8 | 10 |
| 1 | 1 | 2 | 3 | 4 | 5 |

Act on the band, not the raw number:

- 1-4 (low): log and monitor; revisit at weekly grooming.
- 5-9 (medium): assign an owner and a written mitigation; review each sprint; mirror it as a tracked issue via `log_issue`.
- 10-14 (high): active mitigation now, a named contingency, and a tracked issue.
- 15-25 (critical): escalate immediately, fund the contingency, and put it on the standup agenda until the band drops.

For schedule and cost risks, also compute expected value: EMV = probability(%) x impact (in days or currency). A 40% chance of a 10-day slip is a 4-day expected hit; size contingency reserves against the summed EMV of open threats, not against the worst single case. Re-score on every status change; a risk whose probability is climbing toward its trigger is more urgent than its current band suggests.

## Risk response strategies

Pick one strategy per risk and write it down; an unlabelled risk has no plan. For threats, the four PMI responses are:

- **Avoid** — remove the cause so probability goes to zero. Cut the risky scope, change the approach, or drop the offending dependency. The cheapest fix when the feature is not load-bearing.
- **Transfer** — move the impact to a party better placed to carry it: a vendor SLA, a managed service, a contract clause, insurance. The risk still exists; someone else now owns the cost.
- **Mitigate** — reduce probability or impact while still owning it: add a spike, a fallback path, a feature flag, earlier integration. The default for risks you cannot avoid or transfer.
- **Accept** — take the risk knowingly. Active acceptance funds a contingency reserve; passive acceptance just monitors. Either way record it with `save_decision` naming the approver, because an accepted high-exposure risk with no recorded approval is an accountability gap.

For opportunities, the mirror set is exploit, share, enhance, and accept. Spend mitigation effort where exposure x cost-to-fix is worst, not uniformly across the register.

## A worked RAID block

A single managed risk should read complete on its own line. This is the shape an entry takes before it is mirrored to `log_issue`:

```
ID:        R-07
Type:      Risk (threat)
Title:     Upstream auth service JWKS rotation contract is unconfirmed
Prob:      4 (high, 50-70%)   Impact: 4 (high)   Exposure: 16 (critical)
Owner:     auth_engineer (Marcelo)
Raised:    2026-06-20         Check-by: 2026-07-04
Strategy:  Mitigate
Mitigation: Pin JWKS by kid with refetch-on-unknown-kid; add contract test
            against the IdP staging discovery doc this sprint.
Trigger:   IdP publishes a new kid not in our cache, or staging discovery
            doc 404s.
Contingency: Fall back to cached keys for 300s and page the auth_engineer;
            freeze the release if the trigger fires inside the RC window.
Status:    Open -> mirrored as issue #143 (label: risk), on standup agenda.
```

Every field is load-bearing: the check-by date forces a re-score, the trigger makes the contingency fireable, and the issue link means `get_open_issues` returns it. Drop the owner or the date and it stops being a risk and becomes a note.

## Dependency direction and critical-path mapping

Map dependencies before committing a milestone. Classify by direction (inbound vs outbound) and by relationship type from the precedence-diagramming method:

- **Finish-to-start (FS)** — the default: the successor cannot start until the predecessor finishes (build waits on the API contract being merged).
- **Start-to-start (SS)** — the successor cannot start until the predecessor starts (load testing can begin once the deploy starts, not only after it finishes).
- **Finish-to-finish (FF)** — the successor cannot finish until the predecessor finishes (docs cannot be signed off until the feature is signed off).
- **Start-to-finish (SF)** — rare: the successor cannot finish until the predecessor starts (the old service stays up until the new one begins serving).

Flag every cross-team and external-vendor dependency explicitly; these are the ones that slip outside your control. Run the Critical Path Method on the milestone's task network: for each task compute early start/finish and late start/finish; total float = late start - early start = late finish - early finish. Tasks with total float = 0 form the critical path; any slip there slips the release one-for-one. Track near-critical paths too: any chain whose float is at or below one sprint of buffer is one bad estimate away from becoming critical, so it gets the same attention.

For chains with shared resources or deep external dependencies, apply Critical Chain buffers (CCPM): a project buffer of roughly 50% of the aggregated safety stripped from the critical chain, plus feeding buffers where non-critical chains merge into it. Manage by buffer consumption, not by task-level dates: if buffer burn outpaces critical-chain completion (red on the fever chart), act before the deadline is at risk. The `software_architect` agent owns the technical contract at a dependency boundary; the Scrum Master owns the date, the owner, and the escalation.

## Mitigation, contingency, and reserves

Separate the two, because they are different decisions:

- **Mitigation** is proactive: reduce probability or impact now, using the response strategy chosen above.
- **Contingency** is the pre-agreed plan you execute *if* the risk triggers. Every medium-or-higher risk needs a written trigger condition (the observable event that fires the plan) and the contingency itself. A contingency with no trigger never gets invoked in time.

Hold two reserve types and do not blur them: a contingency reserve for known risks (inside the milestone baseline, drawn down by the Scrum Master as triggers fire), and a management reserve for unknown-unknowns (outside the baseline, released only by the sponsor or product owner). Record every drawdown against an issue so reserve burn is auditable.

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
- A risk with no chosen response strategy, so avoid/transfer/mitigate/accept is decided ad hoc when it triggers instead of in advance.
- Internal dependencies tracked but external/vendor ones left implicit. The dependencies outside your control are exactly the ones that slip.
- Mislabelling dependency direction (calling an SS chain FS), so the schedule serializes work that could overlap or overlaps work that must serialize.
- Treating only the zero-float critical path and ignoring near-critical chains; a chain with one sprint of float flips to critical after a single missed estimate.
- Open risks and dependencies kept in a doc that `get_open_issues` does not return, so the backlog and the RAID diverge and the standup works from stale data.
- Escalation with no SLA: a blocker sits unowned for days because no rule says when to push it up.
- Padding every task estimate privately instead of pooling safety into an explicit, managed buffer (CCPM); the schedule lies and the slack is invisible.
- Accepting a high-exposure risk without recording the decision and approver via `save_decision`, leaving no accountability when it materializes.

## Definition of done

- [ ] A RAID log exists for the milestone with every entry carrying type, owner, raised date, review date, and status.
- [ ] Every risk is scored on the 5x5 matrix; exposure band drives the response, and EMV is computed for schedule/cost risks.
- [ ] Every risk names one response strategy (avoid, transfer, mitigate, or accept) and accepted risks carry a `save_decision` with approver.
- [ ] Each medium-or-higher risk has a written mitigation, a contingency, and an explicit trigger condition.
- [ ] Dependencies are classified (direction and FS/SS/FF/SF), cross-team and external ones flagged, and mapped onto the critical path with total float computed.
- [ ] Near-critical chains (float at or below one sprint) are tracked, and CCPM buffers are sized and monitored by consumption where applicable.
- [ ] Contingency and management reserves are separated; every drawdown is recorded against an issue.
- [ ] Every open medium-or-higher risk and every external dependency is a tracked issue via `log_issue` and appears in `get_open_issues`.
- [ ] Cross-team transfers are recorded with `log_handoff`; risk acceptances and reserve draws with `save_decision`.
- [ ] An escalation ladder with named owners and decision SLAs is documented, and red-band items are on the standup agenda until they clear.
- [ ] The log is reviewed at sprint planning, red items at every standup, and the full register at weekly grooming.
