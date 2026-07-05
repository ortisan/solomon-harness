# ADR-0021: Headless /solomon-loop iterations bypass the interactive decision card

- Status: accepted
- Date: 2026-07-04
- Deciders: loop_engineer
- Issue: #194

## Context and problem statement

`solomon-harness dev loop --concurrency N` (formerly `loop-auto`) is documented as
the headless cadence entrypoint: it drives N iterations of the `workflow` stage's
own scan/decide/advance logic under the single-driver lock (`docs/loop-engineering.md`,
Phase 1/2). In practice it does nothing. `run_stage` remaps the `loop` stage's
prompt to the unmodified `.claude/commands/solomon-workflow.md` body
(`prompt_stage = "workflow"` in `solomon_harness/workflows.py`) and runs it N times
through `claude -p`. That command file's step 3 always presents an enumerated
decision card via `AskUserQuestion` and waits for a human to pick Option 1 (Single
Step), Option 2 (Autonomous Mode), or Option 3 (Other) before taking any action —
including entering its own correctly designed Autonomous Mode branch. A headless
`claude -p` invocation has no human to answer that card, so every iteration scans,
prints the same card, and exits — confirmed live on 2026-07-04: `--concurrency 3`
returned exit code 0 across 3 iterations with no PR opened, no commit added, and no
issue status changed (#194).

This traces back to the original `loop-auto` implementation (a6d7c5d, 2026-07-01):
the loop-driving mechanism has never caused Option 2 to auto-select when no human
is present. The bug predates and is orthogonal to the `loop`/`workflow` rename.

## Decision drivers

- The project's non-negotiable enumerable-decisions rule (`agents/AGENTS.md`): a
  human directly invoking `/solomon-workflow` must keep seeing the decision card —
  this fix must not weaken or remove that interactive experience.
- The harness stays prompt-driven (`agents/AGENTS.md`, "Repository layout"): the
  harness supplies prompt definitions and thin Python adapters; the host tool's
  model executes the prompt. Logic must not be duplicated between a Python
  reimplementation of the Autonomous Mode branch and the prompt's own description
  of it.
- C1/C2 (`docs/loop-engineering.md`): no self-hosted model loop, and merge,
  release, and Done stay permanently human-gated at every autonomy level
  (`solomon_harness/loop_policy.py`, `HUMAN_GATED_STAGES`). This fix is about
  execution happening at all once a stage reaches the `workflow` prompt under the
  `loop` driver — it must not touch, widen, or duplicate the policy layer that
  already governs *which* stages autonomy may reach (L1/L2/L3, `AUTOMATION_ALLOWED_STAGES`).
- Minimal blast radius: only the loop-driven headless case changes; a direct
  `dev workflow` invocation (not driven by `loop`) must build the identical prompt
  it builds today.

## Considered options

- Inject an explicit autonomous-mode directive at the start of the prompt text,
  only when `run_stage` is building the `workflow` prompt on behalf of the `loop`
  stage, instructing the model to skip section "## 3. Propose as an enumerated
  decision card, confirm, run" and its `AskUserQuestion` call, and proceed directly
  to the Autonomous Mode instructions the command file already describes.
- Reimplement the scan/decide/execute-via-dev loop in Python inside `workflows.py`
  and stop dispatching to the `workflow` command file at all for the `loop` stage.
  Rejected: this duplicates the same logic the prompt already carries correctly,
  in two places that can drift, and moves decision-making out of the host tool's
  model and into deterministic Python — the harness's supplied design is prompt +
  thin adapter, not a Python orchestrator (C1 in spirit: the model is the loop).
- Rewrite step 3 of `solomon-workflow.md` to detect "no human present" itself
  (e.g., inspect an environment variable inline in the prompt) and branch
  accordingly, with no change to `workflows.py`. Rejected: fragile — nothing
  guarantees the model checks an ambient signal it was never told to look for, and
  it leaves the interactive/headless distinction undiscoverable from the code that
  actually drives the two cases differently (`run_stage`'s `prompt_stage`
  remapping is exactly where that distinction already lives).
- Pass a CLI flag to the engine that changes its behavior globally (e.g., a
  non-interactive mode flag). Rejected: no such engine-level switch exists for
  `AskUserQuestion` specifically, and it would apply to every prompt dispatched
  under `-p`, not just the `loop`-driven `workflow` prompt.

## Decision outcome

Chosen option: inject the autonomous-mode directive at the start of the prompt,
only on the `loop`-driven path, in `solomon_harness/workflows.py`.

`run_stage` already distinguishes the two cases needed: `stage == "loop"` sets
`prompt_stage = "workflow"` before calling `build_prompt`, while a direct
`dev workflow` invocation calls `build_prompt` with `stage == "workflow"` and no
such remapping. `build_prompt` takes a new keyword, `loop_driven: bool = False`;
`run_stage` passes `loop_driven=True` only in the `stage == "loop"` branch. When
`True`, `build_prompt` prepends a short directive block ahead of the command
file's own body: this is a headless, unattended `/solomon-loop` iteration with no
human present; skip "## 3. Propose as an enumerated decision card, confirm, run"
and its `AskUserQuestion` call entirely; proceed directly to the Autonomous Mode
bullet list already described under that section (scan, decide via the existing
rules, execute the next non-human-gated step via `solomon-harness dev <stage>
[args]`, save the decision, continue until a human-gated boundary or nothing left
to progress, then report). The directive names the section to skip and the
section to follow by their existing headings in `solomon-workflow.md` — it does
not re-describe the Autonomous Mode steps, so the two texts cannot drift apart;
if the command file's step 3 is renumbered or reworded, the directive's reference
breaks visibly (the section heading it names no longer exists) rather than
silently.

### Consequences

- Positive: a headless `solomon-harness dev loop --concurrency N` run now actually
  executes work per iteration instead of stalling at a card no one can answer,
  making the documented "Autonomous Mode" behavior real rather than decorative.
  An interactive `/solomon-workflow` invocation is byte-for-byte unchanged (no
  directive is injected), so the enumerated decision card keeps appearing exactly
  as the enumerable-decisions rule requires.
- Negative: the loop-driven prompt now carries one more instruction block the
  model must correctly follow; a model that ignores the directive and still emits
  `AskUserQuestion` would fail the same way as today (a headless engine cannot
  answer it) — this decision improves the odds the model takes the intended
  branch, it cannot force it the way a code gate can. The autonomy policy
  (`loop_policy.py`) is unchanged and remains the enforcement of record for which
  stages may mutate state; this ADR only makes the intended stage reachable at
  all.
- Follow-ups: none required by this fix. If a future host stops honoring
  `AskUserQuestion` gracefully under `-p` (e.g., raises instead of returning),
  revisit whether the directive still suffices or a firmer signal is needed.

## More information

- Implementation: branch `fix/loop-headless-autonomous-execution`;
  `solomon_harness/workflows.py` (`build_prompt`, `run_stage`),
  `.claude/commands/solomon-workflow.md` (a short note under step 3), covering
  tests in `tests/test_workflows.py`.
- Root-cause and reproduction: issue #194.
- Prior art this fix does not change: `docs/adr/0010-loop-single-driver-lock.md`
  (the single-driver lock), the L1/L2/L3 ladder and `HUMAN_GATED_STAGES` in
  `solomon_harness/loop_policy.py`.
- This decision is also recorded in the project memory via `save_decision`.
