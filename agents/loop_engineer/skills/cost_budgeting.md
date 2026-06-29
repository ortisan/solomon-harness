# Cost Budgeting

An unattended loop must throttle itself; this skill governs the post-hoc cost budget that degrades the automation path to report-only when the daily ceiling is reached. A loop that self-estimates with numbers the model cannot count is unsafe — the budget reads the engine's reported actuals.

## The ledger (`solomon_harness/loop_budget.py`)

`record(workspace_root, cost_usd, stage, day)` appends one entry to an append-only ledger anchored at the git common dir (`solomon-loop-budget.jsonl`), so every worktree shares one budget. `daily_spend(workspace_root, day)` sums today's entries; `over_ceiling(workspace_root, ceiling_usd, day)` is true when a positive ceiling is reached. `parse_engine_cost(stdout)` pulls `total_cost_usd` from an engine's `--output-format json` result.

## Capture and enforcement

At autonomy L2/L3, `run_stage` invokes the engine with `--output-format json`, parses the cost with `parse_engine_cost`, and records it. Before running a mutating stage it checks `over_ceiling` against `loop.daily_cost_ceiling_usd`; when the ceiling is hit it returns `3` and the automation path degrades to report-only — it stops drafting and merging work, but never blocks a human. `solomon-harness loop-budget` shows today's spend versus the ceiling.

## Post-hoc, so pair it with a pre-flight cap

The ceiling is post-hoc by nature: cost is known only after the engine runs, so it reacts after a spend, not before. For a hard stop, pair it with a per-cycle cap upstream (max ticks or wall-clock on the host scheduler). On the Gemini host the cost field may differ or be absent; treat a missing cost as zero and document the asymmetry rather than implying parity.

## Common pitfalls

- Enforcing a ceiling on a self-estimated cost instead of the engine's reported `total_cost_usd`.
- Treating the post-hoc ceiling as a hard pre-flight stop — it is not; add a per-cycle cap.
- Anchoring the ledger per-worktree so the daily total is split and never trips.
- Blocking a human when over budget — the degrade is for the automation path only.

## Definition of done

- [ ] Per-stage cost is captured from the engine's reported actuals at L2/L3 and recorded to the ledger.
- [ ] Reaching `daily_cost_ceiling_usd` degrades the automation path to report-only (exit 3), never a human.
- [ ] The ledger is anchored at the git common dir so all worktrees share one budget.
- [ ] `solomon-harness loop-budget` reports spend versus ceiling; host cost asymmetry is documented.
- [ ] Changes ship with covering tests in `tests/test_loop_budget.py`.
