---
name: plan-authoring
description: Governs authoring PLAN.md between the Planning and Execution phases, covering the problem statement, the contract-bearing artifacts list from the spec corpus survey, proposed change, target-files fence, edge cases, a 3-to-8-step TDD breakdown, STRIDE notes, and checkable verification criteria. Use when starting a non-trivial feature or bugfix before writing any production code.
---

# Authoring PLAN.md

Write the PLAN.md the workflow mandates between Planning and Execution so a reviewer can approve the approach before a line of code exists. A plan earns approval when it is small enough to finish in one sitting, testable enough that every claim maps to a check, and reviewable enough that a second engineer can predict the diff from the plan alone. Vague plans produce sprawling diffs; this file is where you constrain scope, not in the pull request.

## What a plan is for

The plan is a design contract for a single change, not a design document for a system. Its job is to force the decisions that are expensive to reverse (the boundary you touch, the contract you change, the edge cases you will and will not handle) while they are still cheap to change. Anything that is obvious from the code, or that the TDD loop will surface anyway, does not belong here. If the plan is longer than the diff it describes, it is too big or too detailed.

Save the plan as `PLAN.md` at the repo root (the lifecycle expects it there). Record the design decision behind the approach with `save_decision` so the rationale outlives the file, and open the work item with `log_issue` if one does not already exist so the plan has a tracked target.

## The required sections

Keep the plan to these sections, in this order. Each has a job; skip none, pad none.

1. **Problem statement.** One or two sentences: the observed behavior or missing capability and why it matters now. State it from the outside (what a user or caller experiences), not as "refactor X". If you cannot name the symptom, you are not ready to plan. Link the issue id from `log_issue`/`get_open_issues`.
2. **Contract-bearing artifacts.** A short bulleted list of the artifacts the plan was built from — the spec document, the issue's acceptance criteria, the ADRs the change touches — as produced by the spec corpus survey (`spec_contract_fidelity`). This is how the reviewer checks the plan against the same corpus; a plan listing nothing but the issue title was built from a paraphrase. Note any divergence you reconciled and which rung of the precedence ladder decided it.
3. **Proposed change.** The approach in three to six sentences: which component owns the change, which port or contract is affected, and the one alternative you rejected with the reason. Name the boundary explicitly (see `hexagonal_architecture_ports_and_adapters`) so the reviewer knows whether domain, port, or adapter moves.
4. **Target files.** A bulleted list of every file you expect to create or modify, each with a half-line of why. This list is the scope fence: a diff that touches a file not on the list is a signal to stop and re-plan, not to quietly expand. Order them by the layer they sit in.
5. **Edge cases.** The boundary and failure inputs you will handle: empty/null, max size, concurrent access, the dependency timing out, the malformed payload. For each, state the expected behavior. These become test names later, so write them as observable outcomes ("returns 422 with a problem detail", not "handle bad input"). Cross-reference `robust_defensive_code` for which boundaries to enumerate.
6. **TDD step breakdown.** An ordered list of red-green steps, each one test wide. See the sizing rules below.
7. **STRIDE notes** (only when the change touches input, auth, data, or an external boundary). See below; otherwise write "No security-relevant surface" and move on.
8. **Verification criteria.** The explicit, checkable conditions that mean done. See below.

## Sizing the TDD step breakdown

Each step is a single trip through the Red, Green, Refactor loop owned by `tdd_red_green_refactor`; this section is where you pre-decompose the work so the loop has somewhere to go. Rules that keep steps reviewable:

- One behavior per step, phrased as the test you will write first: "Step 3: test that a duplicate key returns conflict, not a 500." The step names a failing test, never an implementation action like "add the validator".
- Order steps so each builds on a green suite. The first step is usually the narrowest happy path; edge cases and error paths come after the core behavior is green, not before.
- If a step needs more than roughly 20 lines of production code to go green, split it. A step you cannot make green in one short edit is a hidden multi-step.
- Aim for 3 to 8 steps. Fewer than 3 means the change is trivial enough to skip the breakdown; more than 8 means the plan is really two changes and should be two plans (and two branches per `git_flow_and_conventional_commits`).
- Each step maps to one commit. The breakdown is therefore also your commit plan; if two steps would share a commit, they are one step.

When a change must pause mid-breakdown (handed to another agent or resumed next session), record the completed steps with `log_handoff` and the in-flight state with `save_session` so the next actor resumes at the right step instead of re-deriving the plan.

## STRIDE notes for security-relevant changes

When the change handles untrusted input, authentication, authorization, secrets, or any external boundary, add a short STRIDE pass here rather than discovering the threat in review. This is the planning-time companion to `security_stride_during_design`: walk Spoofing, Tampering, Repudiation, Information disclosure, Denial of service, Elevation of privilege, and for each one that applies, name the threat in one line and the mitigation you will build. Drop the categories that do not apply; do not pad with "N/A" essays. Anything authn/authz-shaped (tokens, sessions, MFA, policy) is the `auth_engineer` agent's domain, so reference its skills rather than re-deriving the control here. Each mitigation you name must show up as a target file and a test step, or it is a wish, not a plan.

## Verification criteria

State, as a checklist, exactly what an approver runs or observes to accept the change. Each item must be objectively checkable, not a feeling:

- The specific test command and the new tests that must pass (tie back to the edge cases and step breakdown so coverage is traceable).
- The lint/type/format gate that must be clean.
- Any behavioral check beyond unit tests: an integration test, a manual reproduction of the original symptom now passing, a metric or log line that should appear.
- For security changes, the specific abuse case that must now fail closed.

If a criterion cannot be expressed as something a reviewer runs or reads, rewrite it until it can. "Works correctly" is not a criterion; "the reproduction in the issue returns 200 and the regression test `test_duplicate_key_conflict` passes" is.

## Common pitfalls

- A plan with no problem statement, opening straight at "proposed change". Reject it: without the symptom, the reviewer cannot judge whether the change solves anything.
- Target-files list missing files the diff later touches, or listing whole directories. The list is a fence; an inaccurate fence is worse than none because it launders scope creep as "already planned".
- Step breakdown written as implementation actions ("add service method", "wire the route") instead of failing tests. That is a task list, not a TDD plan, and it lets code precede tests, which `definition_of_done` forbids.
- Steps too large to go green in one short edit, hiding three behaviors in "Step 2: implement the endpoint". Split until each step is one test.
- Edge cases phrased as inputs ("bad date") with no stated expected behavior, so they cannot become test assertions.
- STRIDE section present but with mitigations that never reappear as files or steps. A mitigation with no test is undone the first time someone refactors.
- Verification criteria that restate the goal ("the feature works") instead of naming the command, test, or observation an approver checks.
- A plan larger than the change it describes, or one that quietly redesigns a neighboring component. Keep it to one change on one branch; a second concern is a second plan.

## Definition of done

- [ ] `PLAN.md` exists at the repo root with all required sections: problem statement, the contract-bearing artifacts it was built from, proposed change, target files, edge cases, TDD step breakdown, STRIDE notes (or an explicit "no security-relevant surface"), and verification criteria.
- [ ] The problem statement names an observable symptom and links the issue id from `log_issue`/`get_open_issues`.
- [ ] The contract-bearing artifacts list cites the spec, acceptance criteria, and ADRs the survey read, and records any reconciled divergence with the ladder rung that decided it.
- [ ] The target-files list is complete and specific; the eventual diff touches nothing outside it without a re-plan.
- [ ] Every edge case states an expected, assertable behavior and maps to a planned test.
- [ ] The step breakdown is 3 to 8 red-green steps, each one test wide and each mappable to a single commit, feeding the `tdd_red_green_refactor` loop.
- [ ] Security-relevant changes carry STRIDE notes whose every mitigation appears as a target file and a test step; authn/authz concerns defer to the `auth_engineer` skills.
- [ ] Verification criteria are objectively checkable (commands, named tests, observations), not restatements of the goal.
- [ ] The design decision and rationale are recorded with `save_decision`; in-flight or handed-off plans persist state via `save_session`/`log_handoff`.
