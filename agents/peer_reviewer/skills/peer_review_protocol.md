---
name: peer-review-protocol
description: Governs the end-to-end protocol for peer-reviewing an AI-produced work product — spec-first ordering, read-only evidence gathering, severity triage, round discipline, and the verdict format. Use when reviewing a diff, pull request, plan, ADR, spec, or report produced by an AI agent and an explicit approve-or-request-changes verdict is needed.
---

# Peer Review Protocol

This skill governs how a peer review of AI-produced work runs from intake to verdict. The stance: the review is a verification exercise, not a reading exercise. The reviewer's job is to establish what is actually true about the work — which requirements it satisfies, which claims hold, which defects are real — and to say so in a verdict the human gate can act on without re-deriving the evidence.

## Intake: identify the contract first

Before reading a line of the change, identify what governs it: the issue's acceptance criteria, the spec under `docs/specs/`, the ADR it implements, or the explicit request. Compliance with that contract is the first review dimension; code quality, readability, and style come second. A beautifully factored change that misses an acceptance criterion is REQUEST CHANGES; an ugly change that satisfies the contract gets its style findings triaged honestly as minors. When no written contract exists, state that in the report and review against the stated request plus the project's non-negotiables (TDD, hexagonal boundaries, secure-by-default) — do not invent requirements.

## Evidence gathering is read-only

Review the revision under review, never a mutation of the working tree. Use `git show <sha>:<path>` to read files as they exist in the change, `git grep <pattern> <sha>` to search that revision, and `git diff <base>...<head>` for the delta. Never run `git checkout <sha> -- .` or switch branches over a tree that may hold uncommitted work: it destroys other work and, worse, makes the review read a hybrid tree, which fabricates findings that exist in neither revision. If a runtime check is genuinely needed (a test run, a reproduced bug), do it in a dedicated worktree created for the review and remove it afterward.

## Ordering inside the review

1. Contract compliance: walk each acceptance criterion and mark it satisfied, unsatisfied, or unverifiable, with the file:line or command output that proves it.
2. Claim verification: every success statement in the PR body, commit messages, or agent report ("tests pass", "the gate only fires when X", "docs updated") is re-established from evidence, per the adversarial-verification skill.
3. Defect scan: correctness first, then security-relevant surfaces, then quality. For each confirmed defect, sweep the class — the instance found is a sample, not the defect list.
4. Documentation truth: any behavior the change alters must be checked against every surface that documents it (README, docs, ADRs, generated twins, wiki templates). Prose drift is invisible to CI and is a legitimate finding.

## Severity triage and round discipline

Assign severity yourself — blocker (breaks the contract, corrupts data, bypasses a gate), major (wrong behavior on a realistic path), minor (quality, naming, docs). Delegated reviewers' severities are inputs, not conclusions. Two rules keep multi-round reviews convergent: a finding triaged minor in round N does not become a blocker in round N+1 without new evidence (no goalpost moving), and a refuted finding is logged and never re-raised. Every fix round is re-reviewed with full rigor, because fix rounds routinely introduce fresh subtle defects; scrutinize hardest the code the fix newly adds, not only whether the original finding went away.

## The verdict

The report ends with exactly one of APPROVE or REQUEST CHANGES. APPROVE means: all acceptance criteria verified satisfied, no blocker or major findings open, all claims verified or explicitly marked unverifiable with a reason. REQUEST CHANGES enumerates the confirmed findings, most severe first, each with its evidence and a concrete expected resolution. Findings that are plausible but unconfirmed are listed separately, tagged PLAUSIBLE, and never counted toward the verdict. The verdict is advisory: the human merge gate decides; the reviewer never merges, closes, or edits the work.

## Common pitfalls

- Reviewing style before the spec — a change can be clean and still not do the job; contract compliance always leads.
- Checking out the reviewed revision over a live working tree — it clobbers uncommitted work and fabricates hybrid-tree findings; use `git show`/`git grep` against the sha.
- Passing through a subagent's severity rating unexamined — adjudicate every rating yourself before it reaches the verdict.
- Escalating a previously triaged minor to a blocker in a later round without new evidence — goalpost moving destroys convergence and trust in the review.
- Re-reviewing only the fixed lines in a fix round — each round can introduce new defects beside the fix; the whole delta gets full rigor.
- Counting PLAUSIBLE findings in the verdict — only CONFIRMED findings justify REQUEST CHANGES.

## Definition of done

- [ ] The governing contract (AC, spec, ADR, or request) is identified and every criterion is marked satisfied/unsatisfied/unverifiable with evidence.
- [ ] All evidence was gathered read-only from the reviewed revision (or a disposable review worktree).
- [ ] Every claim in the work's own description was verified or explicitly marked unverifiable.
- [ ] Each finding carries file:line or command-output evidence, a severity the reviewer assigned, and a CONFIRMED or PLAUSIBLE tag.
- [ ] Confirmed defects triggered a class sweep; refuted claims are in the refutation log.
- [ ] The report ends with exactly one verdict, APPROVE or REQUEST CHANGES, and the work itself was not modified.
