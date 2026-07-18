---
description: Standing maintenance loop — scan the codebase for one architectural drift and open a single draft PR
argument-hint: (optional) a path or subsystem to focus the scan
allowed-tools: Bash(gh:*), Bash(git:*), Bash(uv run:*), Task, Read, Grep, Glob, AskUserQuestion, mcp__solomon-memory__save_decision, mcp__solomon-memory__log_issue
---

You are running the architecture-scan maintenance loop, driven by the
`software_architect` agent. It is a generative loop: its input is the repository's
current state, not a queued issue. Read `docs/solomon-workflow.md` and the agent's
`architecture_scan_loop` skill first. `$ARGUMENTS` may narrow the scan to a path.

This loop owns exactly one inspection lens — architectural drift — so its findings
stay reviewable. It never merges; it terminates at a draft PR or a triage item.

## 1. Scan for drift (one lens)

Sweep the codebase against the architecture fitness functions and the
`architecture_review_gate` checklist: layer/dependency violations, eroded design
contracts, and changes significant enough to need an ADR that never got one. Skip
every path on the loop denylist (`solomon-harness loop-policy` shows it):
generated files, vendored code, secrets, migrations.

## 2. Act on at most ONE finding

Rank findings by severity and act on the single highest-confidence one only:

- **Low confidence:** file a discovery item with `/solomon-idea` (board `Ideas`)
  for human triage. Do not open a PR.
- **High confidence, bounded fix:** cut `feature/<slug>` (no issue number), make
  the minimal change with a covering test (TDD), and open a **draft** PR with a
  `Refs`/`Closes` line and the canonical ADR line the CI gate enforces —
  usually `ADR: not warranted — <reason>` for a scoped drift fix, or the
  `ADR: docs/adrs/NNNN-<slug>.md` link when the finding tripped the
  significance checklist. Then stop.

Respect the per-loop budget: open at most one draft PR per run, and do not open a
second while a prior scan-arch draft PR is still open. Honor the single-driver
lock — this stage acquires it automatically through `run_stage`.

## 3. Record and hand off

- `save_decision` — the finding acted on and why, so the run is auditable.
- Write a one-line run note to `.solomon/scan-runs/scan-arch-<date>.md`.
- QA honesty rule (`persona_driven_exploratory_testing`): if `docs/qa/state.csv`
  exists and this fix is user-visible, reset the affected rows to `untested`;
  a pure refactor states "no user-visible change" explicitly.
- The draft PR enters the unchanged `/solomon-review` gate; a human approves any
  merge. Never advance past the draft PR yourself.
