# Handoff and Memory Orchestration

Drive a feature through the lifecycle as an explicit, auditable state machine in project memory, so that `product_owner -> software_architect -> software_engineer -> qa -> sre` is a chain of recorded handoffs and not tribal knowledge. Every stage boundary is one `log_handoff` entry pointing at a committed contract artifact, every work session is checkpointed with `save_session`, every resume begins with `get_latest_activity`, and every ceremony verdict is an immutable `save_decision`. You are the orchestrator: you do not do the engineering, you make sure each stage hands the next exactly what it needs and that the trail survives a context loss.

## The pipeline as a state machine

The lifecycle (see `quality_gates_you_enforce_across_specialists` and the workflow in `agents/AGENTS.md`) has five stage boundaries. Each boundary is crossed exactly once per feature and recorded by `log_handoff(sender, recipient, contract_type, contract_path, status)`:

| Boundary | sender -> recipient | contract_type | contract_path (committed) |
| --- | --- | --- | --- |
| Scope -> Design | `product_owner` -> `software_architect` | `prd` | `docs/handoffs/<feat>/prd.md` |
| Design -> Build | `software_architect` -> `software_engineer` | `design` | `PLAN.md` + linked ADR ids |
| Build -> Verify | `software_engineer` -> `qa` | `code` | branch ref + `docs/handoffs/<feat>/build.md` |
| Verify -> Operate | `qa` -> `sre` | `qa_report` | `docs/handoffs/<feat>/qa_report.md` |
| Operate -> Release | `sre` -> `scrum_master` | `runbook` | `docs/handoffs/<feat>/runbook.md` |

`contract_path` must be a file under version control, never a local scratch path. The handoff record is a pointer; the artifact is the payload, and it has to be reproducible from git for the audit to mean anything. Bind every feature to a milestone (`milestones` skill) and tie its work items to issues so the chain is queryable from both ends.

## The handoff contract: what each stage hands the next

A handoff is only `approved` when the contract artifact carries everything the next stage cannot start without. Reject the handoff (keep it `pending`, or return it) if any field is missing.

- **product_owner -> software_architect.** PRD with each user story written as acceptance criteria (Given/When/Then), priority, explicit in-scope/out-of-scope boundaries, the target milestone id, and the estimate. Gate: no story without testable acceptance criteria. This is the input the architect's design contracts are built against.
- **software_architect -> software_engineer.** Component boundaries (C4 level), the design contracts/interfaces to implement, non-functional targets (latency, throughput, error budget), chosen technology, and the ADR ids recorded via `save_decision` for every load-bearing choice. Gate: every architectural decision is a retrievable decision record, not prose in a chat.
- **software_engineer -> qa.** The `feature/*` branch (Git Flow per `git_flow_branches`), the `PLAN.md` followed, commit shas, green unit-test run with coverage, the TDD red/green/refactor evidence, the issue ids closed, and known limitations. Gate: build green, coverage threshold met, conventional commits validated.
- **qa -> sre.** Test report (unit/integration/E2E), UAT sign-off, coverage delta, every defect filed via `log_issue` with severity, and rollback/regression notes. Gate: zero open P0/P1 issues on the milestone, UAT signed.
- **sre -> scrum_master.** Deployment plan, runbook, SLO/SLA and alerting wired, DR/rollback procedure, and the release candidate tag. Gate: green deploy to staging, SLOs defined, runbook linked. This closes the loop back to the release step you own.

## Logging and the status lifecycle

A handoff status moves `pending -> approved` or `pending -> rejected`. You flip it to `approved` only after the receiving stage's entry gate above is met; you are the gatekeeper, not the sender.

```python
client.log_handoff(
    sender="software_engineer",
    recipient="qa",
    contract_type="code",
    contract_path="docs/handoffs/feat-142/build.md",  # committed, references branch + shas
    status="pending",
)
# ... after you verify coverage, green build, conventional commits, closed issues:
client.log_handoff("software_engineer", "qa", "code",
                   "docs/handoffs/feat-142/build.md", status="approved")
```

A rejection is itself a recorded event: log the return handoff (`qa -> software_engineer`, status `rejected`) and `log_issue` the reason so the bounce is visible in the backlog, never a silent re-assignment. One boundary, one approved handoff: if you see two `approved` handoffs for the same boundary on the same feature, the state machine forked and the history is no longer trustworthy.

## Checkpointing and resuming

Within a stage, work is checkpointed so a dropped context or an agent swap loses nothing. Use a stable `session_id` of `<feature>/<stage>`:

```python
client.save_session(
    session_id="feat-142/software_engineer",
    agent_name="software_engineer",
    task="Implement OPA policy cache per ADR-17",
    messages=[{"state": "red", "next": "write cache-hit test"}],
)
```

- Checkpoint cadence: at minimum at every standup (`status_meetings_and_ceremonies`) and at the end of every work session, plus immediately before any handoff. The last checkpoint before a handoff and the handoff record should agree.
- **Resume always starts with `get_latest_activity()`** — it returns the most recent session or handoff across the project. That single call tells whoever picks the feature up where the pipeline stopped and whether the last event was a checkpoint (resume in-stage via `get_session`) or a handoff (start the next stage from its contract). Reading any other state first risks acting on a stale view.
- `get_session(session_id)` restores a specific in-stage checkpoint; `get_open_issues()` surfaces the blockers that gate the next handoff. Never advance a feature whose milestone still has open P0/P1 issues.

## Ceremony outcomes as decisions

Every ceremony that changes commitment or direction produces a `save_decision`, so the verdict is auditable and the rationale outlives the meeting (`sprint_planning`, `status_meetings_and_ceremonies`):

```python
client.save_decision(
    title="Go: feat-142 promoted to release/1.4 RC",
    rationale="QA report green, UAT signed, 0 open P0/P1, SLOs defined by sre.",
    outcome="approved",
    author="scrum_master",
    branch="release/1.4",
    commit_sha="<rc-sha>",
)
```

Record a decision for: the sprint commitment (scope frozen for the sprint), each go/no-go release gate, any mid-sprint scope change, and retro action items. Reference the `get_decision` id from the handoff contract artifact so the design-stage ADRs and the release gate are linked. Use `save_memory(key, value, category)` only for durable cross-feature facts (for example a standing environment URL or a naming convention), not for per-feature flow state, which belongs in sessions and handoffs.

## Common pitfalls

- A stage starts work without an `approved` handoff for its boundary. The contract was never verified; reject and require the missing handoff first.
- `contract_path` points at a local or untracked file. The audit trail breaks the moment the workspace is reset; require a committed path.
- Resuming a feature by reading a guessed session id instead of `get_latest_activity` first, acting on a checkpoint that a later handoff already superseded.
- Two `approved` handoffs for the same boundary, or a handoff that skips a stage (architect straight to qa). The pipeline forked or jumped a gate; both invalidate the history.
- A rejection handled as a quiet re-assignment with no `rejected` handoff and no `log_issue`. The bounce vanishes from the backlog and velocity is misread.
- Ceremony verdicts (go/no-go, scope cut) living only in meeting notes. With no `save_decision`, the rationale is unrecoverable at the next gate.
- Handoff marked `approved` while `get_open_issues` still shows P0/P1 on the milestone. The gate in `quality_gates_you_enforce_across_specialists` was not actually met.
- `save_session` used as long-term memory, or `save_memory` used for per-feature flow state. Sessions are checkpoints; memory is durable facts; mixing them rots both.
- Stale checkpoint: a handoff is logged but the last `save_session` predates the work it describes, so resume replays an old state.

## Definition of done

- [ ] Every stage boundary the feature crossed has exactly one `approved` `log_handoff`, in pipeline order, with no skipped stage.
- [ ] Each handoff's `contract_path` is a committed artifact that carries the full contract for the receiving stage (acceptance criteria, design contracts, build evidence, QA report, or runbook).
- [ ] No handoff was approved while the milestone had an open P0/P1 issue (`get_open_issues`), and every rejection is recorded as a `rejected` handoff plus a `log_issue`.
- [ ] Each stage has `save_session` checkpoints at least per standup and immediately before its handoff, under a stable `<feature>/<stage>` `session_id`.
- [ ] Resume procedure is `get_latest_activity` first, then `get_session`/contract; this is documented and followed.
- [ ] Sprint commitment, every go/no-go gate, and scope changes are `save_decision` records with rationale and outcome, linked from the relevant contract artifact.
- [ ] The feature is bound to a milestone and its issues, so the full chain is queryable from the handoff trail and the backlog alike.
