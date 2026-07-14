# ADR-0031: the machine-checked ADR line on every pull-request body

- Status: accepted
- Date: 2026-07-14
- Deciders: software_architect, maintainer (#221 umbrella)
- Issue: #235 (S2b)

## Context and problem statement

The ADR trigger told /solomon-start and /solomon-release to link a record or
"state explicitly" that none was warranted — prose with no enforcement
(umbrella RAID R2). Nothing failed a PR whose body carried neither, so the
decision-or-skip discipline depended on each author remembering. The review
of this very change proved the blast radius question is real: an unwired
mandatory gate silently breaks every flow that opens PRs mechanically.

## Decision drivers

- Machine-checkable: a violated contract must fail CI, not wait for a human.
- Freshness: the verdict must track the body, including post-push edits.
- Total coverage: every PR-producing flow (start, release prep, the scan
  loops, future automations) must be able to satisfy the contract.
- Tolerant input, canonical output: LLMs and humans type several dashes; a
  typography footgun would block merges for no informational gain.

## Considered options

- Keep prose-only guidance. Rejected: it is the defect — unenforced.
- A PR label or checklist checkbox. Rejected: labels are mutable out-of-band,
  invisible in the body's history, and not diffable by a reviewer.
- A canonical body line plus a validator, wired into the existing heavy CI
  job. Rejected after review: the gate ran after the full suite (slow
  feedback) and the default pull_request types miss body edits — a green
  verdict could go stale against an edited-away line.
- A canonical body line, a tolerant validator, and a dedicated minimal
  workflow re-running on `edited`. Chosen.

## Decision outcome

Every PR body carries exactly one canonical line —
`ADR: docs/adrs/NNNN-<slug>.md` or `ADR: not warranted — <reason>` — validated
by `scripts/check-adr-gate.py`: old-path links fail, a reasonless skip fails,
more than one line fails, fenced-code illustrations are stripped, and em/en/
ASCII dashes are accepted on input while the em dash stays the canonical
output form. Enforcement is a dedicated least-privilege workflow
(`.github/workflows/adr-gate.yml`, `types: [opened, synchronize, reopened,
edited]`, body via env var) plus a mechanical re-check in the review stage
before the architect judges the line's honesty. Start, release prep
(`solomon_harness/release.py`), and both scan loops write the line.

### Consequences

- Positive: the record-or-skip decision is visible, diffable, and enforced on
  every PR from merge forward; body edits cannot silently invalidate a verdict.
- Negative: every future PR-producing automation must write the line or its
  PRs fail the gate (the cost is one body line); historical PRs are exempt
  (no backfill), so the contract only governs forward.
- Follow-ups: none pending — the three existing mechanical flows were wired
  in this change after the review found them breaking.

## More information

Validator: `scripts/check-adr-gate.py` (+ `tests/test_adr_gate.py`). Workflow:
`.github/workflows/adr-gate.yml`. Convention text: `docs/solomon-workflow.md`
"ADR trigger". This decision is also recorded in the project memory via
`save_decision`.
