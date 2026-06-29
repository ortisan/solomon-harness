# Duplication Scan Loop

This skill governs the standing duplicate-abstraction maintenance loop: a
generative loop that manufactures its own work from the codebase and owns exactly
one lens — duplication. It is deliberately separate from the architecture scan so
each loop's precision is measurable and its PRs reviewable. It opens a single
draft PR (or files an issue) per run and never merges. Run it on a cadence through
a host-tool scheduler, never a self-hosted model loop.

## What to scan

Find duplicated abstractions: repeated helper logic, parallel near-identical
modules, and copy-pasted blocks that should sit behind one shared construct.
Prefer semantic duplication (the same idea expressed twice) over incidental
textual similarity. One lens only: layering and contract drift belong to the
separate `architecture_scan_loop`.

## Acting safely on one finding per run

Act on the single highest-confidence duplication:

- Safe to unify -> `feature/<slug>` (no issue number); unify behind one construct;
  add a regression test proving behavior is unchanged (TDD); one draft PR; stop.
- Risky merge (shared code with diverging call sites, or a behavior change is
  needed) -> file `/solomon-issue` into `Backlog` describing the proposed
  unification instead of a PR.

Hard guardrails the loop must honor:

- **One open draft PR per loop**; never a second while a prior scan-dedup draft is
  open.
- **Denylist** (`solomon-harness loop-policy`): never touch generated/vendored
  code, secrets, migrations, `.agent/config.json`, `.git`.
- **Single driver**: the `scan-dedup` stage acquires the loop lock via `run_stage`.
- **Autonomy ladder**: allowed at L2/L3 (or `human`), denied at L1.
- **Run note**: append one line to `.solomon/scan-runs/scan-dedup-<date>.md`.

## Common pitfalls

- Unifying two blocks that only look alike but have diverging behavior — the
  regression test must prove equivalence, or file an issue instead.
- A "DRY" change that adds a leaky abstraction worse than the duplication — prefer
  filing an issue when the shared construct would be contorted.
- Touching more than one duplication per run — keep the diff bounded and reviewable.
- Self-merging the draft PR — autonomy stops at the review gate.

## Definition of done

- [ ] Exactly one duplication unified (one draft PR) or filed as one issue, or none.
- [ ] The unification ships with a regression test proving behavior is unchanged.
- [ ] No denylisted path was modified; the loop held the single-driver lock.
- [ ] A `save_decision` and a `.solomon/scan-runs/` run note were written.
- [ ] The PR is a draft routed to `/solomon-review`; no merge was performed.
