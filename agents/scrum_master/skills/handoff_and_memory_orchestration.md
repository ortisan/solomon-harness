---
name: handoff-and-memory-orchestration
description: Governs driving a feature through the product_owner, software_architect, software_engineer, qa, and sre lifecycle as an auditable state machine, recorded via log_handoff, save_session, and save_decision. Use when a feature crosses a lifecycle stage boundary, resuming after a context loss, or reviewing a handoff trail for completeness.
---

# Handoff and Memory Orchestration

Drive a feature through the lifecycle as an explicit, auditable state machine in project memory, so that `product_owner -> software_architect -> software_engineer -> qa -> sre` is a chain of recorded handoffs and not tribal knowledge. Every stage boundary is one `log_handoff` entry pointing at a committed contract artifact, every work session is checkpointed with `save_session`, every resume begins with `get_latest_activity`, and every ceremony verdict is an immutable `save_decision`. You are the orchestrator: you do not do the engineering, you make sure each stage hands the next exactly what it needs and that the trail survives a context loss.

## The pipeline as a state machine

The lifecycle (see `quality_gates_you_enforce_across_specialists` and the workflow in `agents/AGENTS.md`) has five stage boundaries. Each boundary is crossed exactly once per feature and recorded by `log_handoff(sender, recipient, contract_type, contract_path, status)`:

| Boundary | sender -> recipient | contract_type | contract_path (committed) |
| --- | --- | --- | --- |
| Scope -> Design | `product_owner` -> `software_architect` | `prd` | `.solomon/handoffs/issue-<N>-product_owner-to-software_architect.md` |
| Design -> Build | `software_architect` -> `software_engineer` | `design` | `.solomon/handoffs/issue-<N>-software_architect-to-software_engineer.md` + linked ADR ids |
| Build -> Verify | `software_engineer` -> `qa` | `code` | `.solomon/handoffs/issue-<N>-software_engineer-to-qa.md` (references branch + shas) |
| Verify -> Operate | `qa` -> `sre` | `qa_report` | `.solomon/handoffs/issue-<N>-qa-to-sre.md` |
| Operate -> Release | `sre` -> `scrum_master` | `runbook` | `.solomon/handoffs/issue-<N>-sre-to-scrum_master.md` |

`contract_path` must be a file under version control, never a local scratch path. The handoff record is a pointer; the artifact is the payload, and it has to be reproducible from git for the audit to mean anything. Bind every feature to a milestone (`milestones` skill) and tie its work items to issues so the chain is queryable from both ends.

## The `.solomon/handoffs/` contract artifact

Every boundary writes one Markdown file under `.solomon/handoffs/`, named `issue-<N>-<from>-to-<to>.md` where `<N>` is the GitHub issue number and `<from>`/`<to>` are the specialist role names. The name alone tells a reader which issue, which boundary, and which direction, so a directory listing reconstructs the pipeline state without opening a file. The file is committed on the feature branch, so the artifact and the code it describes share one history and one review.

The artifact is the contract, structured so the receiving stage can start with zero questions. Keep a fixed front-matter block and a body:

```markdown
---
issue: 142
boundary: software_engineer -> qa
contract_type: code
milestone: 1.4
branch: feature/opa-policy-cache
commit_shas: [a1b2c3d, e4f5a6b]
status: pending
decision_refs: [ADR-17, ADR-19]
---

## What is delivered
OPA policy cache per ADR-17, LRU with 5-minute TTL, behind feature flag
`policy_cache_enabled`.

## Entry gate for the receiving stage
- Unit run green: 48 passed, coverage 91% (threshold 85%).
- TDD evidence: red/green/refactor commits a1b2c3d (red) -> e4f5a6b (green).
- Conventional commits validated by the pre-commit hook.
- Issues closed: #142; no new defects opened.

## Known limitations / risks
- Cache invalidation on policy bundle reload is eager, not yet load-tested
  at >1k rps. RAID R-09 (label: risk) tracks it.

## How to verify
`uv run pytest tests/policy/ -q` then exercise `/authz` with the flag on/off.
```

The front-matter `status` mirrors the `log_handoff` status, and the body's "Entry gate" section is exactly what you check before flipping that status to `approved`. If a field the receiving stage needs is absent, the artifact is incomplete and the handoff stays `pending`.

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
    contract_path=".solomon/handoffs/issue-142-software_engineer-to-qa.md",
    status="pending",
)
# ... after you verify coverage, green build, conventional commits, closed issues:
client.log_handoff("software_engineer", "qa", "code",
                   ".solomon/handoffs/issue-142-software_engineer-to-qa.md",
                   status="approved")
```

A rejection is itself a recorded event: log the return handoff (`qa -> software_engineer`, status `rejected`) and `log_issue` the reason so the bounce is visible in the backlog, never a silent re-assignment. One boundary, one approved handoff: if you see two `approved` handoffs for the same boundary on the same feature, the state machine forked and the history is no longer trustworthy.

## A worked handoff-contract walkthrough

Feature #142 reaches the Build -> Verify boundary. The sequence you orchestrate:

1. `software_engineer` commits `.solomon/handoffs/issue-142-software_engineer-to-qa.md` on `feature/opa-policy-cache`, with the front matter and entry-gate body above, `status: pending`.
2. They call `log_handoff(..., status="pending")` pointing at that committed path.
3. You verify the entry gate: `get_open_issues()` shows no open P0/P1 on milestone 1.4, the artifact's coverage (91%) clears the 85% threshold, and the TDD red/green shas resolve. RAID R-09 is a tracked risk, not a blocker, so it does not hold the gate.
4. You flip the handoff to `approved` and update the artifact front matter `status: approved` in a commit. QA can now start with everything it needs and nothing to ask.
5. If instead coverage were 80%, you log `qa -> software_engineer` `rejected`, `log_issue` "coverage below threshold on policy cache", and the card stays in Review (see `quality_gates_you_enforce_across_specialists`).

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

- Checkpoint cadence: at minimum at every standup (`sprint_planning`) and at the end of every work session, plus immediately before any handoff. The last checkpoint before a handoff and the handoff record should agree.
- **Resume always starts with `get_latest_activity()`** — it returns the most recent session or handoff across the project. That single call tells whoever picks the feature up where the pipeline stopped and whether the last event was a checkpoint (resume in-stage via `get_session`) or a handoff (start the next stage from its contract). Reading any other state first risks acting on a stale view.
- `get_session(session_id)` restores a specific in-stage checkpoint; `get_open_issues()` surfaces the blockers that gate the next handoff. Never advance a feature whose milestone still has open P0/P1 issues.

## Ceremony outcomes as decisions

Every ceremony that changes commitment or direction produces a `save_decision`, so the verdict is auditable and the rationale outlives the meeting (`sprint_planning`):

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

Record a decision for: the sprint commitment (scope frozen for the sprint), each go/no-go release gate, any mid-sprint scope change, and retro action items. Reference the `get_decision` id from the handoff contract artifact (the `decision_refs` front-matter list) so the design-stage ADRs and the release gate are linked. Use `save_memory(key, value, category)` only for durable cross-feature facts (for example a standing environment URL or a naming convention), not for per-feature flow state, which belongs in sessions and handoffs.

## Common pitfalls

- A stage starts work without an `approved` handoff for its boundary. The contract was never verified; reject and require the missing handoff first.
- `contract_path` points at a local or untracked file instead of a committed `.solomon/handoffs/issue-<N>-<from>-to-<to>.md`. The audit trail breaks the moment the workspace is reset; require a committed path.
- The artifact file name does not match the boundary it records (wrong issue number or reversed direction), so a directory listing reconstructs the pipeline wrong.
- Resuming a feature by reading a guessed session id instead of `get_latest_activity` first, acting on a checkpoint that a later handoff already superseded.
- Two `approved` handoffs for the same boundary, or a handoff that skips a stage (architect straight to qa). The pipeline forked or jumped a gate; both invalidate the history.
- A rejection handled as a quiet re-assignment with no `rejected` handoff and no `log_issue`. The bounce vanishes from the backlog and velocity is misread.
- Handoff marked `approved` while `get_open_issues` still shows P0/P1 on the milestone. The gate in `quality_gates_you_enforce_across_specialists` was not actually met.
- The artifact front-matter `status` and the `log_handoff` status disagree, so the committed contract and the memory record tell different stories.
- `save_session` used as long-term memory, or `save_memory` used for per-feature flow state. Sessions are checkpoints; memory is durable facts; mixing them rots both.
- Stale checkpoint: a handoff is logged but the last `save_session` predates the work it describes, so resume replays an old state.

## Definition of done

- [ ] Every stage boundary the feature crossed has exactly one `approved` `log_handoff`, in pipeline order, with no skipped stage.
- [ ] Each handoff's `contract_path` is a committed `.solomon/handoffs/issue-<N>-<from>-to-<to>.md` whose name matches the boundary and that carries the full contract for the receiving stage.
- [ ] Each artifact has the fixed front matter (issue, boundary, contract_type, milestone, branch, shas, status, decision_refs) and an explicit entry-gate section.
- [ ] No handoff was approved while the milestone had an open P0/P1 issue (`get_open_issues`), and every rejection is recorded as a `rejected` handoff plus a `log_issue`.
- [ ] Each stage has `save_session` checkpoints at least per standup and immediately before its handoff, under a stable `<feature>/<stage>` `session_id`.
- [ ] Resume procedure is `get_latest_activity` first, then `get_session`/contract; this is documented and followed.
- [ ] Sprint commitment, every go/no-go gate, and scope changes are `save_decision` records with rationale and outcome, linked from the artifact's `decision_refs`.
- [ ] The feature is bound to a milestone and its issues, so the full chain is queryable from the handoff trail and the backlog alike.
