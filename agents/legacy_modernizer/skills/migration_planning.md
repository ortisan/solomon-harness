# Migration Planning

This skill governs how the Legacy Modernizer plans a legacy codebase to the house standards, one bounded step per run, delegation only. It turns a non-conformant codebase into a sequenced roadmap of small changes and, on each run, advances exactly one of them and hands it to the specialist who owns the standard it touches. The Legacy Modernizer writes the plan and the handoff; it writes no source-refactor diff.

## Assess and sequence the roadmap

Produce an ordered roadmap, not a pile of findings. Each entry is a single bounded scope: one named module or path, never the whole codebase. The big-bang rewrite is rejected outright; it couples a long unreviewable branch to one irreversible switch, which is the failure mode this contract exists to prevent.

Sequence the roadmap dependency- and risk-first: a step that other steps depend on, or that lowers the blast radius of later steps, comes earlier. The two ordering anchors are concrete:

- A secret-removal step (owner security) must come before the module it touches is opened to wider change, so no later refactor moves a live credential around in history.
- A covering-test safety net (owner software_engineer or qa) must precede the structural work it protects: a Test-Driven Development covering test exists and is green before any architecture refactor (owner software_architect) that depends on it. Restructuring code with no test net first is rejected.

State each step's owner, its single standard, and the step it depends on, so the next session reads why step N precedes step N+1 rather than re-deriving the order.

## One bounded step, one delegate per run

A single run advances at most one bounded step and routes it to one delegate. The delegate set is closed and fixed at exactly eight specialists: software_architect, software_engineer, security, observability, qa, dba, sre, and documenter. The closed set makes "who executes this step" deterministic and grep-able.

A candidate step whose required owner falls outside that set is held or flagged and never assigned to an empty or invented delegate. UI, mobile, auth, and loop-mechanics work has no owner in the set, so it is surfaced as held, not silently mis-routed.

## Per-step exit bars

Each bounded step advances exactly one standard and clears the owner-attributed exit bar for that standard before it reaches review. The four bars are enumerated, each naming its owner:

- Test-Driven Development (TDD): a covering test follows the red/green/refactor cycle and is green before the draft pull request. Owner: software_engineer, verified with qa.
- secure-by-default: a STRIDE pass over the touched code with no secrets in code, parameterized queries for every data access, and input validation at the boundary. Owner: security.
- OpenTelemetry (OTel): spans, metrics, and structured logs instrument every touched path. Owner: observability.
- hexagonal: the touched module sits behind a port, with its framework and I/O concerns moved into an adapter. Owner: software_architect.

A step that needs schema, index, or migration work pairs the structural bar with the dba; a step that changes deploy or rollback behaviour pairs it with the sre; a step that changes an operator-facing contract pairs it with the documenter. The standard the step advances stays one; the supporting owner is named alongside it.

## Termination and the human gate

The run terminates at a single draft PR behind /solomon-review and goes no further. The Legacy Modernizer proposes no merge and no release at any autonomy level, and never opens a multi-step or whole-repo big-bang PR. Merge and release stay human-gated, mirroring the loop contract of /solomon-scan-arch and /solomon-scan-dedup.

Record the delegated step as a handoff with log_handoff, naming the executing delegate and the standard, and persist the next step so the following session resumes from the record rather than from re-reading the diff.

## Common pitfalls

- Emitting an unordered findings list instead of a dependency- and risk-first roadmap, so no one can tell which step is safe to run next.
- Advancing more than one bounded step in a run, or scoping a step to the whole codebase instead of one named module, which rebuilds the big-bang branch.
- Refactoring structure before a covering test exists, so a regression has nothing to catch it.
- Moving a module before its secret-removal step, dragging a live credential through history.
- Assigning a step to an owner outside the closed eight-specialist set, or to an empty delegate, instead of holding or flagging it.
- Letting the Legacy Modernizer author the refactor diff itself, collapsing the planning and execution boundary and bypassing the per-standard owner.
- Proposing a merge or a release, or opening a multi-step PR, instead of stopping at the human-gated draft PR.
- Skipping the OpenTelemetry, secure-by-default, or hexagonal exit bar because the step "looks small".

## Definition of done

- [ ] The roadmap is ordered dependency- and risk-first, each entry a single bounded scope (one named module or path), with secret-removal and a covering test sequenced before the architecture refactor that depends on them.
- [ ] The run advanced at most one bounded step, routed to one delegate from the closed set software_architect, software_engineer, security, observability, qa, dba, sre, documenter.
- [ ] Any step whose owner falls outside the set is held or flagged, never assigned.
- [ ] The step's single standard cleared its owner-attributed exit bar: a TDD covering test (software_engineer/qa), secure-by-default with parameterized queries, input validation and a STRIDE pass (security), OpenTelemetry on touched paths (observability), and a hexagonal port and adapter boundary (software_architect).
- [ ] The run terminated at one human-gated draft PR behind /solomon-review with no merge and no release proposed and no big-bang PR opened.
- [ ] The delegated step is recorded with log_handoff naming the delegate, and the next step is persisted for the following session.
