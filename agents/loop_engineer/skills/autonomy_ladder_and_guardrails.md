# Autonomy Ladder and Guardrails

The autonomy ladder (human / L1 / L2 / L3) is the one dial for how far a loop may act; this skill governs the ladder, the permanent human gate, the denylist, and the kill-switch. It is the policy that makes a loop more capable without ever making it less safe, enforced in portable Python (`solomon_harness/loop_policy.py`) on both hosts.

## The ladder (`LoopPolicy.decide_stage`)

- **human (default):** no restriction. A repository with no `loop` block in `.agent/config.json` behaves exactly as before.
- **L1 (report):** only `loop` (scan and propose); every mutating stage is denied.
- **L2 (assisted):** `idea`..`review` plus the scan loops — create work and draft PRs, never merge.
- **L3 (unattended):** as L2, may run on a cadence, and `requires_lock` for mutating stages.

Three rules no level can widen: **merge, release, and Done are permanently human-gated** (`HUMAN_GATED_STAGES`); an **unknown/typo'd level fails closed** (a mistyped `l2` denies, never silently becomes `human`); and the **kill-switch** halts everything. A denied stage exits `3` from `run_stage`, never silently.

## Configuration

```json
"loop": { "autonomy": "L2", "denylist": ["**/*.enc"],
          "maker_model": "...", "checker_model": "...",
          "daily_cost_ceiling_usd": 5.0 }
```

`SOLOMON_LOOP_AUTONOMY` overrides the configured level for a cadence run. `solomon-harness loop-policy` prints the level, kill-switch state, denylist, checker split, and the per-stage allow/deny table.

## Denylist and the maker/checker split

`is_denied_path` names the paths the loop must not modify (defaults: `.git/*`, `.agent/config.json`, `*.env`, `*.pem`, `*.key`, `*.enc`, `*secrets/*`, migrations, vendored code). It is **enforced** by the `loop-guard` PreToolUse hook, which blocks an `Edit`/`Write`/`MultiEdit` to a denied path (and a `git push`/`gh pr merge` under a foreign lock) — a Claude-side hard block. On the Gemini host (no PreToolUse) the denylist is model-honored, so an unattended L3 cadence on Gemini must pin its level with `SOLOMON_LOOP_AUTONOMY` (env beats config in `from_config`) so a self-edit of `.agent/config.json` cannot raise the level. `checker_split_ok` requires the verifier to run on a different model than the maker — a config invariant surfaced by `loop-policy`; it complements, never replaces, the human `/solomon-review` gate.

## The kill-switch

`solomon-harness loop-stop` writes a sentinel beside the lock (`solomon-loop.stop` at the git common dir) that makes `decide_stage` deny every stage at once, including `human`; `loop-stop --clear` removes it. It is the one-command emergency halt for any cadence.

## Common pitfalls

- Coercing an invalid level to `human` — that fails open; keep it failing closed.
- Letting L3 act without the lock, or letting any level merge/release autonomously.
- Treating the denylist as enforced everywhere — it is a hard block only at the Claude `loop-guard` PreToolUse boundary; on Gemini it is model-honored, so pin the level via env there.
- Putting a webhook URL or model secret in the committed `loop`/`notify` block — secrets come from the environment.

## Definition of done

- [ ] `human` is unrestricted; L1 report-only; L2/L3 draft-only; an invalid level denies.
- [ ] Merge, release, and Done are denied at every non-human level.
- [ ] The kill-switch halts all stages and is clearable; `loop-policy` shows the full state.
- [ ] The denylist is enforced at the loop-guard PreToolUse boundary (Edit/Write/Bash) and model-honored on Gemini; the checker-split is surfaced; secrets stay in env.
- [ ] Changes ship with covering tests in `tests/test_loop_policy.py`.
