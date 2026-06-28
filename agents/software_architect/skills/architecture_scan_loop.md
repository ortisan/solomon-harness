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

## Acting safely on one finding per run

Rank findings by severity and act on the single highest-confidence finding:

- Low confidence -> `/solomon-idea` into `Ideas` for human triage; no PR.
- High confidence and bounded -> `feature/<slug>` (no issue number), the minimal
  fix with a covering test (TDD), one draft PR with a `Refs`/`Closes` line, stop.

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
