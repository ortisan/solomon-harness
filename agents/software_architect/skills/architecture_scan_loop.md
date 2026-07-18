---
name: architecture-scan-loop
description: Governs the standing architecture-scan maintenance loop that sweeps the repository for layer violations, eroded design contracts, and undocumented ADR-worthy changes, acting on the single highest-confidence finding as a draft PR or a filed idea. Use when running the scheduled architecture drift scan or deciding whether a structural finding warrants a fix now or a triage item.
---

# Architecture Scan Loop

This skill governs the standing architecture-scan maintenance loop: a generative
loop whose input is the repository's current state, not a queued issue. It owns
exactly one inspection lens — architectural drift — and terminates at a single
draft PR or a triage item, never at a merge. Run it on a cadence through a
host-tool scheduler (the `/loop` skill, a scheduled routine, or the `ralph-wiggum`
plugin), never a self-hosted model loop.

## What to scan

Sweep against the existing fitness functions and the `architecture_review_gate`
checklist for: layer and dependency-direction violations (a port importing an
adapter, an inner ring depending on an outer one); eroded or bypassed design
contracts; and changes significant enough to warrant an ADR (a new cross-cutting
dependency, a public contract change, a new persistence or transport boundary)
that shipped without one. One lens only: duplication belongs to the separate
`duplication_scan_loop`.

This scan also owns one narrower, mechanical check on the ADR log itself: an
Accepted ADR that still carries no `## Reconciliation` section (the
append-only, post-merge convention in `docs/adrs/README.md`) after N merged
PRs have touched the area it governs is itself a drift finding, ranked
alongside the layer, contract, and missing-ADR findings above. Default N to 3
merged PRs touching the ADR's stated area; record the threshold used in the
run note so a later run applies the same bar rather than re-deriving it. The
standing one-finding-per-run cap (below) still applies — a stale-reconciliation
finding is not an exception to it, only one more candidate competing for the
single slot by severity.

## Objective rules and tooling

Every finding must cite a reproducible, objective rule, never a taste judgment.
Anchor the scan in executable fitness functions so a reviewer can re-run the
check: `import-linter` contracts for Python layer and dependency-direction rules
(forbidden imports, layered-architecture, independence of bounded contexts);
`grimp` or `pydeps` to surface import cycles; an ArchUnit-style suite where the
stack supports it. Treat the `architecture_review_gate` checklist items as the
acceptance criteria for "is this drift": if no checklist item or fitness function
flags it, it is not a finding. Calibrate ADR-significance against the recorded
triggers — a new cross-cutting dependency, a public-contract or schema change, a
new persistence or transport boundary, or the reversal of a prior ADR. A change
that matches a trigger but shipped without an ADR is itself a finding worth a
draft PR that adds the missing record.

## Cadence and convergence

Run on a fixed, low cadence (daily, or once per merge-batch), never continuously:
the loop reads repository state, so back-to-back runs over an unchanged tree only
waste a slot and the single-driver lock. Track convergence through the
`.solomon/scan-runs/` notes — when two consecutive runs surface no new
high-confidence finding, the architecture is within tolerance and the loop idles
until the next change lands. Never let an unresolved finding be re-proposed every
run: once a finding has an open draft PR or a filed idea, record it as handled in
the run note so the next iteration skips it and advances to the next-ranked drift
instead of thrashing on the same one.

## Acting safely on one finding per run

Rank findings by severity and act on the single highest-confidence finding:

- Low confidence -> `/solomon-idea` into `Ideas` for human triage; no PR.
- High confidence and bounded -> `feature/<slug>` (no issue number), the minimal
  fix with a covering test (TDD), one draft PR with a `Refs`/`Closes` line, stop.

A stale-reconciliation finding routes by how much verification it needs: if
the merged PRs' own review records already carry a reconciliation verdict
(`architecture_review_gate`'s ADR-reconciliation step) that was simply never
appended to the ADR file, appending it is a bounded documentation fix — take
the high-confidence path. If no such verdict exists and the scan would have
to re-derive whether the ADR still matches the code from scratch, that
judgment belongs to a human reviewer, not the scan loop — file it as an idea
instead of guessing.

Hard guardrails the loop must honor:

- **One open draft PR per loop.** Never open a second scan-arch draft PR while a
  prior one is still open — this caps board flooding and keeps each PR reviewable.
- **Denylist.** Never read or modify a path on the loop denylist
  (`solomon-harness loop-policy`): generated files, vendored code, secrets,
  migrations, `.agent/config.json`, `.git`.
- **Single driver.** The `scan-arch` stage acquires the loop lock through
  `run_stage`; if another driver holds it, the run is refused.
- **Autonomy ladder.** Allowed only at autonomy L2/L3 (or `human`); denied at L1
  (report-only). Merge/release stay permanently human.
- **Run note.** Append one line to `.solomon/scan-runs/scan-arch-<date>.md`
  (filesystem-as-memory) so the next iteration resumes from state, not context.

## Common pitfalls

- Opening multiple PRs in one run, or a second while one is open — floods review.
- "Fixing" generated or vendored files because they tripped a rule — denylist them.
- Proposing a large refactor as one finding — keep each finding bounded and
  independently reviewable, or file it as an idea instead.
- Self-merging the draft PR — autonomy terminates at the review gate.
- Citing drift without an objective rule (a fitness function or checklist item) —
  unreproducible findings get rejected.

## Definition of done

- [ ] Exactly one finding acted on (one draft PR or one triage item), or none.
- [ ] Any code change is TDD-first with a covering test; an ADR is written when the
      change is architecturally significant.
- [ ] No denylisted path was modified; the loop held the single-driver lock.
- [ ] A `save_decision` and a `.solomon/scan-runs/` run note were written.
- [ ] The PR is a draft routed to `/solomon-review`; no merge was performed.
