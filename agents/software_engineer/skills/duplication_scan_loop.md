# Duplication Scan Loop

This skill governs the standing duplicate-abstraction maintenance loop: a
generative loop that manufactures its own work from the codebase and owns exactly
one lens — duplication. It is deliberately separate from the architecture scan so
each loop's precision is measurable and its PRs stay reviewable. It opens a single
draft PR (or files an issue) per run and never merges. Run it on a cadence through
a host-tool scheduler, never a self-hosted model loop.

## How a run starts

The loop runs as the `/solomon-scan-dedup` workflow, driven by the
`software_engineer` agent. The command reads `docs/solomon-workflow.md` and this
skill before scanning, and accepts an optional argument (a path or module) that
narrows the scan; without one, the whole repository minus the denylist is in
scope. Keeping this loop separate from `/solomon-scan-arch` is deliberate: each
loop owns one lens, so a reviewer can judge every PR against a single question —
"is this the same abstraction twice?" — and each loop's hit rate can be measured
on its own.

## What to scan

Find duplicated abstractions: repeated helper logic, parallel near-identical
modules, and copy-pasted blocks that should sit behind one shared construct.
Prefer semantic duplication (the same idea expressed twice) over incidental
textual similarity: two functions that parse the same identifier in two places
are one finding; two loops that merely look alike but encode different business
rules are none. Useful detection passes:

- Grep for repeated function and class names, and near-identical signatures,
  across sibling modules.
- Compare modules that grew in parallel (two adapters, two CLI subcommands) for
  logic that drifted into both.
- Look for the same validation, parsing, or error-mapping block pasted at
  several call sites.

One lens only: layering violations and contract drift belong to the separate
`architecture_scan_loop`, even when they surface mid-scan. Note them for that
loop; do not act on them here.

## Ranking findings

Act on the single highest-confidence duplication. Confidence ranks by: (1)
provable behavioral equivalence — a regression test can pin both blocks to the
same outputs today; (2) blast radius — how many call sites the unification
touches; (3) stability — code being changed by an open branch is off-limits,
since the unification would collide with in-flight work. A large or ambiguous
finding is not discarded; it becomes an issue instead of a PR.

## Acting safely on one finding per run

- Safe to unify -> cut `feature/<slug>` (no issue number, per the repo branch
  convention); unify behind one construct; add a regression test proving behavior
  is unchanged (TDD: the test pins the current behavior before the refactor moves
  anything); open one draft PR with a `Refs`/`Closes` line; stop.
- Risky merge (shared code with diverging call sites, or a behavior change is
  needed) -> file `/solomon-issue` into `Backlog` describing the duplication and
  the proposed unification instead of a PR.

Hard guardrails the loop must honor:

- **One open draft PR per loop**; never a second while a prior scan-dedup draft is
  open. Check for one before scanning.
- **Denylist** (`solomon-harness loop-policy`): never touch generated/vendored
  code, secrets, migrations, `.agent/config.json`, `.git`.
- **Single driver**: the `scan-dedup` stage acquires the loop lock via `run_stage`;
  two concurrent drivers on one repository is a known failure mode.
- **Autonomy ladder**: allowed at L2/L3 (or `human`), denied at L1.
- **Run note**: append one line to `.solomon/scan-runs/scan-dedup-<date>.md`
  recording what was scanned and what was done.

## Recording and handoff

Every run writes a `save_decision` to project memory naming the duplication
unified (or filed) and why, so the next run does not re-discover the same
finding. The draft PR enters the unchanged `/solomon-review` gate; a human
approves any merge. The loop's autonomy ends at the draft PR.

## Common pitfalls

- Unifying two blocks that only look alike but have diverging behavior — the
  regression test must prove equivalence, or file an issue instead.
- A "DRY" change that adds a leaky abstraction worse than the duplication — file
  an issue when the shared construct would be contorted with flags and special
  cases to serve both call sites.
- Touching more than one duplication per run — keep the diff bounded and
  reviewable.
- Acting on an architecture finding because it surfaced during the dedup scan —
  wrong lens, wrong loop.
- Opening a second draft while a prior scan-dedup draft is still open, which
  floods review and defeats the per-loop budget.
- Self-merging the draft PR — autonomy stops at the review gate.
- Skipping the run note or the `save_decision`, so the next run re-litigates the
  same finding.

## Definition of done

- [ ] Exactly one duplication unified (one draft PR) or filed as one issue, or none.
- [ ] The unification ships with a regression test proving behavior is unchanged.
- [ ] No denylisted path was modified; the loop held the single-driver lock.
- [ ] A `save_decision` and a `.solomon/scan-runs/` run note were written.
- [ ] The PR is a draft routed to `/solomon-review`; no merge was performed.
