---
name: cost-budgeting
description: Governs the post-hoc daily cost ceiling in solomon_harness/loop_budget.py that degrades an unattended loop to report-only once spend is reached, based on the engine's reported actual cost, not a self-estimate. Use when configuring daily_cost_ceiling_usd or diagnosing an over-budget block.
---

# Cost Budgeting

An unattended loop must throttle itself; this skill governs the post-hoc cost budget that degrades the automation path to report-only when the daily ceiling is reached. A loop that self-estimates with numbers the model cannot count is unsafe — the budget reads the engine's reported actuals.

## The ledger (`solomon_harness/loop_budget.py`)

`record(workspace_root, cost_usd, stage, day)` appends one entry to an append-only JSONL ledger anchored at the git common dir (`<common>/solomon-loop-budget.jsonl`; `<root>/.agents/solomon/state/loop-budget.jsonl` outside a git repo), so every worktree shares one budget. Each line is `{"day": "YYYY-MM-DD", "cost_usd": <float>, "stage": "<stage>"}`; the day key comes from `datetime.date.today()`, so the window rolls at local midnight. Writes are best-effort (an `OSError` is swallowed — a full disk must not abort a stage) and reads skip malformed lines, so a truncated append cannot poison the ledger. `daily_spend(workspace_root, day)` sums the day's entries (rounded to 6 decimals); `over_ceiling(workspace_root, ceiling_usd, day)` is true when a positive ceiling is reached — a ceiling of `None`, `0`, or a negative value disables the check entirely. `parse_engine_cost(stdout)` pulls the first of `total_cost_usd`, `cost_usd`, or `total_cost` from an engine's JSON result.

## Capture and enforcement (`run_stage`)

Both halves live in `solomon_harness/workflows.py` and bind only the automation ladder — at the default `human` level nothing is captured or checked.

- **Capture.** At autonomy L2/L3, Claude is invoked with `--output-format json` and Codex with `--json`; stdout is parsed with `parse_engine_cost`, and a found cost is recorded with the stage name. AGY has no supported structured-cost flag, so its native argv stays unchanged and no cost is invented from plain text. A run whose output lacks a cost field records nothing; report that telemetry state explicitly instead of presenting an undercount as parity.
- **Enforcement.** Before running a stage at L2/L3, and only for stages other than `workflow`, `run_stage` checks `over_ceiling` against `loop.daily_cost_ceiling_usd` from `.agents/solomon/config/project.json` (with `.agent/config.json` as the one-release read fallback). At the ceiling it prints `Blocked by loop budget: daily cost ceiling reached (...); degraded to report-only.` and returns exit code `3`. The `workflow` stage stays allowed so the harness can still inspect and report; drafting stages are refused. A human working interactively is never blocked.

`solomon-harness loop-budget` prints today's spend, the ceiling with its status (`OVER -> report-only` or `within budget`, or `none configured (set loop.daily_cost_ceiling_usd)`), and the ledger path.

## A worked over-budget day

Ceiling 5.00; a morning of scan iterations records 5.20 across the ledger. The next `solomon-harness dev start 42` exits `3` with the block message, while `solomon-harness dev workflow` still runs and reports. Verify with `solomon-harness loop-budget` (`OVER -> report-only`). Recovery: wait for the day key to roll, or have a human raise `daily_cost_ceiling_usd`; the normalized Claude, AGY, and Codex pre-tool guard blocks an autonomous run from editing `.agents/solomon/config/project.json` to widen its own ceiling.

## Post-hoc, so pair it with a pre-flight cap

The ceiling is post-hoc by nature: cost is known only after the engine runs, so it reacts after a spend, not before — one expensive tick can overshoot the ceiling before the next check trips. For a hard stop, pair it with a per-cycle cap upstream (max ticks via `dev loop --concurrency N`, or wall-clock on the host scheduler), and keep `solomon-harness loop-stop` as the immediate halt when spend is running away right now.

## Common pitfalls

- Enforcing a ceiling on a self-estimated cost instead of the engine's reported `total_cost_usd`.
- Treating the post-hoc ceiling as a hard pre-flight stop — it is not; add a per-cycle cap.
- Anchoring the ledger per-worktree so the daily total is split and never trips.
- Blocking a human when over budget — the degrade is for the automation path only.
- Assuming every engine reports a cost — a missing field records nothing, so the ledger undercounts; verify capture per host before trusting the number.
- Letting `record` failures abort a stage — the ledger write is best-effort by design.

## Definition of done

- [ ] Per-stage cost is captured from the engine's reported actuals at L2/L3 and recorded to the ledger.
- [ ] Reaching `daily_cost_ceiling_usd` degrades the automation path to report-only (exit 3; `workflow` still allowed), never a human.
- [ ] The ledger is anchored at the git common dir so all worktrees share one budget; an unset or non-positive ceiling disables the check.
- [ ] `solomon-harness loop-budget` reports spend versus ceiling and the ledger path; host cost asymmetry is documented.
- [ ] Changes ship with covering tests in `tests/test_loop_budget.py`.
