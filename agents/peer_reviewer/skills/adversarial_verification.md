---
name: adversarial-verification
description: Governs refute-first verification of claims and findings — treating every statement as unproven, attempting refutation before acceptance, tagging results CONFIRMED/PLAUSIBLE/REFUTED, and sweeping defect classes beyond the cited sample. Use when a finding, success claim, severity rating, or documentation statement produced by an AI agent must be established as true or false before it drives a verdict or a fix.
---

# Adversarial Verification

This skill governs how any claim — a reviewer's finding, an author's success statement, a doc's description of behavior, a subagent's severity — is established before it is acted on. The stance is refute-first: the verifier's goal is to break the claim, and only a claim that survives a genuine refutation attempt is reported as true. Plausible-but-wrong findings are the dominant failure mode of AI review; they cost fix rounds, erode trust, and, when they drive a REQUEST CHANGES, block correct work. Refutation is cheaper than a wasted round.

## The verification loop

For each claim, in order:

1. Restate it falsifiably. "The lock prevents concurrent drivers" becomes "with a live foreign lock present, `run_stage` exits 1 before any mutating call". A claim that cannot be restated falsifiably is not verifiable — tag it and say what evidence would make it so.
2. Locate the strongest evidence that could refute it: run the test and read the output, execute the code path, read the implementation at the reviewed revision, reproduce the input. Reading the same prose that made the claim is not verification.
3. Attempt the refutation. Prefer executable evidence (a run, a failing input) over textual evidence; prefer textual evidence at the exact revision over memory of the codebase.
4. Tag the result. CONFIRMED: the refutation attempt failed against concrete evidence, cited. REFUTED: the claim is false — record why in the refutation log so it is never re-raised. PLAUSIBLE: verification was genuinely impossible (missing environment, nondeterminism) — reported separately and never counted in a verdict. When uncertain, default toward REFUTED for findings and toward unverified for success claims; the asymmetry is deliberate, because a false finding blocks good work while an unverified success claim must not pass a gate.

## A citation is a sample, not the defect list

When a finding cites one instance ("this ADR claim drifted from the code", "this call lacks a timeout"), verifying and fixing that instance is not closure. The instance is a sample from a class. Sweep the class: re-diff the whole ADR against the implementation, grep every sibling call site, check every surface that documents the changed behavior — including generated twins and templates that regenerate documentation. Reviews that fix only the cited line reliably bounce in the next round on an uncited sibling.

## Verifying documentation and "only fires when" claims

Statements about behavior — "the gate only fires when X", "this command is idempotent", "the fallback is best-effort" — are verified against the implementation, not against other documents. Read the condition in code and check both directions: the documented trigger fires, and nothing outside the documented trigger fires. A gate's justification is verified too: if a rule cites a convention as pre-existing, confirm the convention actually predates the change rather than being authored by it. Prose truth is invisible to CI; the adversarial reviewer is the only gate it has.

## Adjudicating other reviewers

Findings and severities from subagents or parallel reviewers enter this loop like any other claim. Verify the finding before accepting it, re-rate its severity yourself against the triage definitions, and be alert to two specific failure modes: a delegated reviewer inflating severity to seem thorough, and a delegated reviewer fabricating a plausible rationale for an action or relationship that the underlying artifact does not support. Read the primary artifact — the actual issue body, the actual diff — before acting on any subagent's characterization of it.

## Economy

Refutation effort scales with consequence. A blocker that would stop a merge deserves an executable refutation attempt; a naming minor deserves a glance at the style rule. Do not spend a worktree and a test run refuting a typo report. State, per finding, how hard it was tested — the verdict's credibility rests on that being honest.

## Common pitfalls

- Verifying a claim by re-reading the document that made it — evidence must be independent of the claim's source.
- Accepting "tests pass" without the test output at the reviewed revision — the claim is verified by the run, not the assertion.
- Fixing the cited instance and closing the finding — the citation is a sample; the class sweep is the closure condition.
- Passing a subagent's severity or issue-relationship characterization into the verdict unread — primary artifacts first.
- Treating PLAUSIBLE as a soft CONFIRMED — unverifiable findings inform, they never block or approve.
- Symmetric defaults under uncertainty — findings default to REFUTED, success claims default to unverified; getting this backward either blocks good work or waves bad work through.

## Definition of done

- [ ] Every claim that drives the verdict was restated falsifiably and carries a CONFIRMED/REFUTED/PLAUSIBLE tag.
- [ ] Each CONFIRMED tag cites independent evidence (command output or file:line at the reviewed revision).
- [ ] Refuted claims are in the refutation log with the reason, and are not re-raised in later rounds.
- [ ] Every confirmed instance-finding triggered a class sweep, and the sweep result is recorded.
- [ ] Behavior claims in documentation were checked against the implementation in both directions.
- [ ] Severities from delegated reviewers were re-adjudicated against the primary artifacts.
