---
name: verification-iron-law
description: Governs completion claims with the verification iron law — no claim without verification evidence produced in the same run, verification scope matching claim scope, and a report citing command, exit code, and output. Use when about to state that anything works, passes, is fixed, or is complete, when preparing the pre-PR verification report in the start stage, and when a verification command fails.
---

# Verification iron law

The verification iron law: no completion claim without verification evidence produced in the same run as the claim. If the proving command has not been executed here and now, with its output read, the result cannot be claimed — not "should pass now", not "this fixes it", not "done". A claim without fresh evidence is not optimism, it is a false report: downstream stages (review, merge, release) act on it, and every unverified claim they act on converts minutes of verification into hours of triage. This skill defines the gate sequence, the scope-parity rule that sizes the verification to the claim, and the report format that makes the evidence auditable.

## The gate sequence

Before any claim of success, walk four steps in order; skipping any one of them means you are claiming, not verifying.

1. **Identify** the command that proves the claim. A behavior claim names its test; a "suite is green" claim names the suite invocation; a "validator passes" claim names the validator.
2. **Run** it fresh and in full. Cached results, a run from before the last edit, memory of "it passed earlier", or another agent's report are not evidence — the code changed, so the evidence expired.
3. **Read** the complete output: the exit code, the pass/fail/skip counts, and every warning. A green summary line above a skipped-test warning is not a pass.
4. **Claim** only what the output supports, citing it. If the output is not shown, the verification did not happen.

## Scope parity

The scope of the verification must be at least the claim scope. A narrow claim needs its specific command: "the duplicate-key case now returns conflict" is proven by that one test. A broad claim needs the broad command: "the task is complete", "ready for PR", "safe to merge" are proven only by the full suite plus the repository's validators (for this repo: `uv run pytest -q` and the CI validator scripts), because the claim quantifies over everything they cover. The asymmetry is deliberate — over-verification wastes minutes, under-verification wastes review rounds — so when in doubt, verify one scope wider than the claim. A green pipeline still proves only compilation, lint, and existing tests: it never proves the deliverable matches the contract, which is the separate fidelity check owned by `spec_contract_fidelity` and, at review, the qa gate's parity pass.

## The verification report

The start stage ends with a verification report, written before the push/PR confirmation and reproduced in the PR body's summary. Its shape:

- **Claim** — what is being asserted, in one line.
- **Command(s)** — the exact invocations run, copy-pastable.
- **Exit code** — per command.
- **Output summary** — counts (passed/failed/skipped), plus any warning worth a reviewer's eye.
- **Verdict** — PASS or FAIL, nothing in between.

The report is evidence, so it quotes the run that just happened in this same run of work — never a reconstruction. If the suite was green two commits ago and you edited since, the report requires a re-run. Keep it compact: five lines that a reviewer can re-execute beat five paragraphs of assurance.

## When verification fails

A failing verification is information, not an obstacle. Read the failure output before touching code; diagnose the root cause (the `debugging_method` skill owns the discipline — no guess-loop fixes); apply the minimal root-cause fix, never a suppression or a weakened assertion to force green; then re-run the full identifying command from scratch, not just the previously failing subset, because fixes regress neighbors. Never claim partial success ("mostly passing"), never blame tooling without evidence, and never downgrade the claim to fit a failure you have not diagnosed — either the claim gets evidence or the claim is withdrawn.

## Common pitfalls

- Claiming from memory of a pre-edit run. Any edit after the last verification expires the evidence; re-run.
- Scope mismatch: running one test and claiming "everything passes". The claim quantifies over the suite; the evidence covers one case — that is a false report even when it happens to be true.
- Reading only the summary line. Skipped tests, collection errors, and deprecation warnings that will fail CI hide above it; the exit code and full tail are part of the evidence.
- Making the failing test pass by editing the test. Fix production first; change a test only with a written reason the contract changed (and then `spec_contract_fidelity` demands the contract actually changed).
- Shipping the report without exit codes, or with prose in place of commands. A report a reviewer cannot re-execute is assurance, not evidence.
- Verifying before the final formatting/cleanup pass, then committing after it. Any code-mutating step after evidence collection makes the evidence stale; verify last.

## Definition of done

- [ ] Every success claim in this stage cites a command executed in this same run, with exit code and output summary.
- [ ] The verification scope is at least the claim scope; completion claims ran the full suite and validators.
- [ ] The pre-PR verification report exists with claim, commands, exit codes, output summary, and a PASS verdict.
- [ ] No failing check was silenced, skipped, or weakened to reach green; failures were root-caused and re-verified in full.
- [ ] Verification ran after the last mutation of the working tree — nothing changed between the evidence and the claim.
