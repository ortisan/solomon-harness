---
name: solomon-scan-dedup
description: "Standing maintenance loop — find one duplicated abstraction and open a single draft PR that unifies it Use when the user asks to run the corresponding Solomon stage or explicitly invokes $solomon-scan-dedup."
---

# solomon-scan-dedup

Apply this workflow when the user invokes the skill or asks for the stage it governs. Treat `ARGUMENTS` in the workflow below as the arguments supplied with the skill invocation or elsewhere in the conversation.

Codex compatibility rules:

- Invoke Solomon workflow stages explicitly with their `$solomon-*` skill names.
- When the workflow names Claude-specific Task or AskUserQuestion tools, use the equivalent sub-agent delegation or structured user-input capability available in the current Codex session.
- Read specialist definitions and skills under `agents/<name>/` before acting in that role.

You are running the duplicate-abstraction maintenance loop, driven by the
`software_engineer` agent. Like the architecture scan it is generative — it
manufactures its own work from the repository's current state — but it owns a
different single lens: duplication. Read `docs/solomon-workflow.md` and the
agent's `duplication_scan_loop` skill first. `ARGUMENTS` may narrow the scan.

Keeping this a separate loop from `scan-arch` is deliberate: each loop owns one
lens, so its precision is measurable and its PRs are reviewable.

## 1. Scan for duplication (one lens)

Find duplicated abstractions: repeated helper logic, parallel near-identical
modules, and copy-pasted blocks. Skip every path on the loop denylist
(`solomon-harness loop-policy`).

## 2. Act on at most ONE finding

Act on the single highest-confidence duplication only:

- **Safe to unify:** cut `feature/<slug>` (no issue number), unify the duplication
  behind one shared construct, and add a regression test proving behavior is
  unchanged (TDD). Open a **draft** PR with a `Refs`/`Closes` line and the
  canonical ADR line the CI gate enforces (usually
  `ADR: not warranted — <reason>` for a deduplication), then stop.
- **Risky merge:** file a `$solomon-issue` (board `Backlog`) describing the
  duplication and the proposed unification, instead of a PR.

Per-loop budget: at most one draft PR per run, and never a second while a prior
scan-dedup draft PR is still open. The single-driver lock is acquired
automatically through `run_stage`.

## 3. Record and hand off

- `save_decision` — the duplication unified (or filed) and why.
- Write a one-line run note to `.solomon/scan-runs/scan-dedup-<date>.md`.
- The draft PR enters the unchanged `$solomon-review` gate; a human approves any
  merge. Never advance past the draft PR yourself.
