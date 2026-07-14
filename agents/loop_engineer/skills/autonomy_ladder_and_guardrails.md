---
name: autonomy-ladder-and-guardrails
description: Governs the human/L1/L2/L3 autonomy ladder, the denylist enforced by the loop-guard PreToolUse hook, the maker/checker model split, and the kill-switch implemented in solomon_harness/loop_policy.py. Use when configuring a loop's autonomy level, adding a denylist pattern, or diagnosing why a stage was blocked or allowed.
---

# Autonomy Ladder and Guardrails

The autonomy ladder (human / L1 / L2 / L3) is the one dial for how far a loop may act; this skill governs the ladder, the permanent human gate, the denylist, and the kill-switch. It is the policy that makes a loop more capable without ever making it less safe, enforced in portable Python (`solomon_harness/loop_policy.py`) on both hosts.

## The ladder (`LoopPolicy.decide_stage`)

- **human (default):** no restriction. A repository with no `loop` block in `.agent/config.json` behaves exactly as before.
- **L1 (report):** only the stages in `L1_ALLOWED_STAGES = {"loop"}` (scan and propose); every mutating stage is denied.
- **L2 (assisted):** the stages in `AUTOMATION_ALLOWED_STAGES` — `loop`, `loop-auto`, `idea`, `issue`, `bug`, `refine`, `start`, `review`, `scan-arch`, `scan-dedup` — create work and draft PRs, never merge.
- **L3 (unattended):** the same stage set as L2, may run on a cadence, and `requires_lock(stage)` is true for every stage except `loop`, so an unattended run only acts while holding the single-driver lock; `run_stage` enforces this, it is not just claimed.

`decide_stage` evaluates in a fixed order: the kill-switch denies first (even at `human`); `human` then allows everything; `HUMAN_GATED_STAGES = {"release"}` denies at every non-human level; then the level's allow-set applies; anything left — including an unknown or typo'd level — fails closed (`LoopPolicy` keeps a mistyped `l2` verbatim so it denies, never silently becomes `human`). A denied stage exits `3` from `run_stage`, printed as `Blocked by loop autonomy policy (level ...)`, never silently.

## Configuration

```json
"loop": { "autonomy": "L2", "denylist": ["**/*.enc"],
          "maker_model": "...", "checker_model": "...",
          "daily_cost_ceiling_usd": 5.0 }
```

`SOLOMON_LOOP_AUTONOMY` overrides the configured level for a cadence run (`from_config` reads env before config). `solomon-harness loop-policy` prints the level, kill-switch state, checker split, the denylist, and the per-stage allow/DENY table — run it before arming any cadence and again after any config change.

## Denylist and the maker/checker split

`is_denied_path` names the paths the loop must not modify. `DEFAULT_DENYLIST` is `.git/*`, `.agent/config.json`, `*/.env`, `.env`, `*.pem`, `*.key`, `*.enc`, `*secrets/*`, `*/migrations/*`, `*/node_modules/*`. A `denylist` in the config's `loop` block REPLACES the default list rather than extending it, so restate the defaults when adding a pattern. An absolute path is relativized against the workspace root before matching, so slash-bearing patterns hold no matter how the path was rooted. The list is **enforced** by the `loop-guard` PreToolUse hook (`.claude/settings.json`, matcher `Bash|Edit|Write|MultiEdit|NotebookEdit`): `denied_write_verdict` blocks a file-write tool call targeting a denied path — exit 2, reason fed back to the model — precisely so an autonomous (or prompt-injected) run cannot edit `.agent/config.json` to widen its own level, empty its denylist, or defeat its cost ceiling. On the Gemini host (no PreToolUse) the denylist is model-honored, so an unattended L3 cadence on Gemini must pin its level with `SOLOMON_LOOP_AUTONOMY` (env beats config in `from_config`) so a config self-edit cannot raise it. `checker_split_ok` requires the verifier to run on a different model than the maker — a config invariant surfaced by `loop-policy`; it complements, never replaces, the human `/solomon-review` gate.

## The kill-switch

`solomon-harness loop-stop` writes a sentinel beside the lock (`solomon-loop.stop` at the git common dir; `.solomon/loop.stop` outside a git repo) that makes `decide_stage` deny every stage at once, including at `human` level; `solomon-harness loop-stop --clear` removes it. Because the sentinel shares the lock's git-common anchor, one command halts every linked worktree of the repository.

Worked scenario for a runaway cadence: run `solomon-harness loop-stop`; the next `run_stage` call at any level is refused with exit `3` and the reason `loop halted by kill-switch; clear with 'solomon-harness loop-stop --clear'`. Confirm with `solomon-harness loop-policy` (`Kill-switch: ENGAGED`, DENY on every stage row), inspect what the loop did with `solomon-harness log` and `solomon-harness loop-lock status`, and only then `loop-stop --clear` to resume.

## Common pitfalls

- Coercing an invalid level to `human` — that fails open; keep it failing closed.
- Letting L3 act without the lock, or letting any level merge/release autonomously.
- Treating the denylist as enforced everywhere — it is a hard block only at the Claude `loop-guard` PreToolUse boundary; on Gemini it is model-honored, so pin the level via env there.
- Adding one pattern to `loop.denylist` and silently dropping the defaults — the config list replaces `DEFAULT_DENYLIST`, it does not extend it.
- Putting a webhook URL or model secret in the committed `loop`/`notify` block — secrets come from the environment.

## Definition of done

- [ ] `human` is unrestricted; L1 report-only; L2/L3 draft-only; an invalid level denies (exit 3 from `run_stage`).
- [ ] Merge, release, and Done are denied at every non-human level; L3 mutating stages hold the lock.
- [ ] The kill-switch halts all stages (all worktrees, even `human`) and is clearable; `loop-policy` shows the full state.
- [ ] The denylist is enforced at the loop-guard PreToolUse boundary (Edit/Write/Bash) and model-honored on Gemini; the checker-split is surfaced; secrets stay in env.
- [ ] Changes ship with covering tests in `tests/test_loop_policy.py`.
