# Cost Budgeting

An unattended loop must throttle itself; this skill governs the post-hoc cost budget that degrades the automation path to report-only when the daily ceiling is reached. A loop that self-estimates with numbers the model cannot count is unsafe — the budget reads the engine's reported actuals.

## The ledger (`solomon_harness/loop_budget.py`)

`record(workspace_root, cost_usd, stage, day)` appends one entry to an append-only JSONL ledger anchored at the git common dir (`<common>/solomon-loop-budget.jsonl`; `<root>/.solomon/loop-budget.jsonl` outside a git repo), so every worktree shares one budget. Each line is `{"day": "YYYY-MM-DD", "cost_usd": <float>, "stage": "<stage>"}`; the day key comes from `datetime.date.today()`, so the window rolls at local midnight. Writes are best-effort (an `OSError` is swallowed — a full disk must not abort a stage) and reads skip malformed lines, so a truncated append cannot poison the ledger. `daily_spend(workspace_root, day)` sums the day's entries (rounded to 6 decimals); `over_ceiling(workspace_root, ceiling_usd, day)` is true when a positive ceiling is reached — a ceiling of `None`, `0`, or a negative value disables the check entirely. `parse_engine_cost(stdout)` pulls the first of `total_cost_usd`, `cost_usd`, or `total_cost` from an engine's JSON result.

## Capture and enforcement (`run_stage`)

Both halves live in `solomon_harness/workflows.py` and bind only the automation ladder — at the default `human` level nothing is captured or checked.

- **Capture.** At autonomy L2/L3 the engine is invoked with a JSON result flag (`--output-format json` for `claude` and `gemini`, `-o json` for `agy`), stdout is parsed with `parse_engine_cost`, and a found cost is recorded to the ledger with the stage name. A run whose output lacks a cost field records NOTHING — that spend is invisible to the ceiling, so the budget undercounts on hosts with a different or absent cost field; treat that asymmetry as a documented gap, not parity.
- **Enforcement.** Before running a stage at L2/L3, and only for stages other than `loop`, `run_stage` checks `over_ceiling` against `loop.daily_cost_ceiling_usd` from `.agent/config.json`. At the ceiling it prints `Blocked by loop budget: daily cost ceiling reached (...); degraded to report-only.` and returns exit code `3`. The `loop` stage stays allowed — that exemption IS the report-only degrade in code: the loop may still scan and propose, but every drafting stage (`start`, `review`, the scan loops) is refused. A human working interactively is never blocked.

`solomon-harness loop-budget` prints today's spend, the ceiling with its status (`OVER -> report-only` or `within budget`, or `none configured (set loop.daily_cost_ceiling_usd)`), and the ledger path.

## A worked over-budget day

Ceiling 5.00; a morning of scan iterations records 5.20 across the ledger. The next `solomon-harness dev start 42` exits `3` with the block message, while `solomon-harness dev loop` still runs and reports. Verify with `solomon-harness loop-budget` (`OVER -> report-only`). Recovery: wait for the day key to roll, or have a human raise `daily_cost_ceiling_usd` — and note the default denylist blocks an autonomous run from editing `.agent/config.json`, so the loop cannot raise its own ceiling; on the Gemini host pin the level with `SOLOMON_LOOP_AUTONOMY` so a config self-edit cannot widen it either.

## Post-hoc, so pair it with a pre-flight cap

The ceiling is post-hoc by nature: cost is known only after the engine runs, so it reacts after a spend, not before — one expensive tick can overshoot the ceiling before the next check trips. For a hard stop, pair it with a per-cycle cap upstream (max ticks via `dev loop-auto --concurrency N`, or wall-clock on the host scheduler), and keep `solomon-harness loop-stop` as the immediate halt when spend is running away right now.

## Common pitfalls

- Enforcing a ceiling on a self-estimated cost instead of the engine's reported `total_cost_usd`.
- Treating the post-hoc ceiling as a hard pre-flight stop — it is not; add a per-cycle cap.
- Anchoring the ledger per-worktree so the daily total is split and never trips.
- Blocking a human when over budget — the degrade is for the automation path only.
- Assuming every engine reports a cost — a missing field records nothing, so the ledger undercounts; verify capture per host before trusting the number.
- Letting `record` failures abort a stage — the ledger write is best-effort by design.

## Definition of done

- [ ] Per-stage cost is captured from the engine's reported actuals at L2/L3 and recorded to the ledger.
- [ ] Reaching `daily_cost_ceiling_usd` degrades the automation path to report-only (exit 3; `loop` still allowed), never a human.
- [ ] The ledger is anchored at the git common dir so all worktrees share one budget; an unset or non-positive ceiling disables the check.
- [ ] `solomon-harness loop-budget` reports spend versus ceiling and the ledger path; host cost asymmetry is documented.
- [ ] Changes ship with covering tests in `tests/test_loop_budget.py`.
