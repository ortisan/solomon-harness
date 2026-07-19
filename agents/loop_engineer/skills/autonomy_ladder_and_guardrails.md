---
name: autonomy-ladder-and-guardrails
description: Governs the human/L1/L2/L3 autonomy ladder, the denylist enforced by the loop-guard PreToolUse hook, the maker/checker model split, and the kill-switch implemented in solomon_harness/loop_policy.py. Use when configuring a loop's autonomy level, adding a denylist pattern, or diagnosing why a stage was blocked or allowed.
---

# Autonomy Ladder and Guardrails

The autonomy ladder (human / L1 / L2 / L3) is the one dial for how far a loop may act; this skill governs the ladder, the permanent human gate, the denylist, and the kill-switch. It is enforced in portable Python (`solomon_harness/loop_policy.py`) and through native adapters for Claude, AGY, and Codex.

## The ladder (`LoopPolicy.decide_stage`)

- **human (default):** no restriction. A repository with no `loop` block in `.agents/solomon/config/project.json` behaves exactly as before.
- **L1 (report):** only `workflow` may inspect and propose; every mutating stage is denied.
- **L2 (assisted):** `workflow`, `loop`, `idea`, `issue`, `bug`, `refine`, `start`, `review`, `scan-arch`, and `scan-dedup` may create work and draft PRs, never merge.
- **L3 (unattended):** the same stage set as L2 may run on a cadence, and every stage except `workflow` requires the single-driver lock; `run_stage` enforces this.

`decide_stage` evaluates in a fixed order: the kill-switch denies first (even at `human`); `HUMAN_GATED_STAGES = {"release"}` denies next, at EVERY level including `human` — on the dev automation path a release is never autonomous; `human` then allows everything else; then the level's allow-set applies; anything left — including an unknown or typo'd level — fails closed (`LoopPolicy` keeps a mistyped `l2` verbatim so it denies, never silently becomes `human`). A denied stage exits `3` from `run_stage`, printed as `Blocked by loop autonomy policy (level ...)`, never silently.

## Configuration

```json
"loop": { "autonomy": "L2", "denylist": ["**/*.enc"],
          "maker_model": "...", "checker_model": "...",
          "daily_cost_ceiling_usd": 5.0 }
```

`SOLOMON_LOOP_AUTONOMY` overrides the configured level for a cadence run (`from_config` reads env before config). `solomon-harness loop-policy` prints the level, kill-switch state, checker split, the denylist, and the per-stage allow/DENY table — run it before arming any cadence and again after any config change.

## Denylist and the maker/checker split

`is_denied_path` names the configurable paths the loop must not modify. `DEFAULT_DENYLIST` includes `.git/*`, environment files, keys, encrypted material, secrets, migrations, and dependency trees. A `denylist` in the config's `loop` block replaces those configurable defaults rather than extending them, so restate them when adding a pattern. It can never remove the mandatory trust roots: canonical and legacy project config, the install manifest, manifest-owned core/adapters, and the runtime venv remain immutable during a run. The adapter compiler registers the same normalized `host-hook pre-tool-use` guard for Claude (`.claude/settings.json`), AGY (`.agents/hooks.json`), and Codex (inline in `.codex/config.toml`). The guard blocks a write using each host's native verdict protocol, so an autonomous run cannot edit project config to widen its own level or defeat its cost ceiling. `checker_split_ok` requires the verifier to run on a different model than the maker; it complements, never replaces, the human review gate.

## The kill-switch

`solomon-harness loop-stop` writes a sentinel beside the lock (`solomon-loop.stop` at the git common dir; `.agents/solomon/state/loop.stop` outside a git repo) that makes `decide_stage` deny every stage at once, including at `human` level; `solomon-harness loop-stop --clear` removes it. Because the sentinel shares the lock's git-common anchor, one command halts every linked worktree of the repository.

Worked scenario for a runaway cadence: run `solomon-harness loop-stop`; the next `run_stage` call at any level is refused with exit `3` and the reason `loop halted by kill-switch; clear with 'solomon-harness loop-stop --clear'`. Confirm with `solomon-harness loop-policy` (`Kill-switch: ENGAGED`, DENY on every stage row), inspect what the loop did with `solomon-harness log` and `solomon-harness loop-lock status`, and only then `loop-stop --clear` to resume.

## Common pitfalls

- Coercing an invalid level to `human` — that fails open; keep it failing closed.
- Letting L3 act without the lock, or letting any level merge/release autonomously.
- Assuming the three hosts use the same hook payload or response format — normalize input and serialize the verdict through the host adapter.
- Adding one pattern to `loop.denylist` and silently dropping the configurable defaults — the config list replaces `DEFAULT_DENYLIST`, although mandatory trust roots still cannot be removed.
- Putting a webhook URL or model secret in the committed `loop`/`notify` block — secrets come from the environment.

## Definition of done

- [ ] `human` is unrestricted except the permanently human-gated stages; L1 report-only (`workflow` only); L2/L3 draft-only; an invalid level denies (exit 3 from `run_stage`).
- [ ] Merge, release, and Done are denied at every level of the dev automation path; L3 mutating stages hold the lock.
- [ ] The kill-switch halts all stages (all worktrees, even `human`) and is clearable; `loop-policy` shows the full state.
- [ ] The denylist is enforced through native Claude, AGY, and Codex pre-tool hooks; the checker split is surfaced; secrets stay in env.
- [ ] Changes ship with covering tests in `tests/test_loop_policy.py`.
