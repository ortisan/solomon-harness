"""Headless runner for the /solomon-* delivery workflows.

`run_stage` builds the prompt from the matching `.claude/commands/solomon-<stage>.md`
file and runs it through the chosen engine (claude or gemini) non-interactively,
so the workflows can run in CI and automation, not only inside the host tool.
"""

import os
import subprocess
import sys
from typing import List, Optional

STAGES = [
    "workflow", "loop", "idea", "issue", "bug", "refine", "start", "review", "release",
    # Standing maintenance loops (Phase 3): generative, open draft PRs only.
    "scan-arch", "scan-dedup",
]

# Renamed stages, still accepted on input with a deprecation notice:
# `loop-auto` became `loop` when the orchestrator moved from `loop` to `workflow`.
DEPRECATED_STAGE_ALIASES = {"loop-auto": "loop"}

# Stages that drive git/board state (branch, push, merge, release) and must run
# under a single driver. The lock is a portable Python gate run on both hosts —
# the documented concurrent-driver race produced premature merges that bypassed
# the review gate, so honoring an advisory markdown "Step 0" was not enough.
LOCKED_STAGES = {"workflow", "loop", "start", "review", "release", "scan-arch", "scan-dedup"}

# `loop` is the headless cadence entrypoint: `dev loop --concurrency N` drives
# N iterations of the `workflow` stage's own scan/propose/advance logic — the
# same one confirmed step per `/solomon-workflow` invocation, repeated in a
# bounded, auditable for-loop rather than a new self-scheduling mechanism.
DEFAULT_CONCURRENCY = 1


def _parse_concurrency(args: List[str]) -> "tuple[int, List[str]]":
    """Split ``--concurrency N`` (or ``--concurrency=N``) out of a stage's args.

    Returns ``(concurrency, remaining_args)``; ``remaining_args`` is what gets
    substituted into the `workflow` stage's ``$ARGUMENTS`` so the flag never
    leaks into the prompt text. Defaults to `DEFAULT_CONCURRENCY` (one iteration
    — identical to running `workflow` directly) when the flag is absent.
    """
    concurrency = DEFAULT_CONCURRENCY
    remaining: List[str] = []
    i = 0
    while i < len(args):
        arg = args[i]
        if arg == "--concurrency":
            if i + 1 >= len(args):
                raise ValueError("--concurrency requires a value")
            value = args[i + 1]
            i += 2
        elif arg.startswith("--concurrency="):
            value = arg.split("=", 1)[1]
            i += 1
        else:
            remaining.append(arg)
            i += 1
            continue
        try:
            concurrency = int(value)
        except ValueError:
            raise ValueError(f"--concurrency must be an integer, got {value!r}")
        if concurrency < 1:
            raise ValueError("--concurrency must be >= 1")
    return concurrency, remaining


def _target_issue_from_args(args: List[str]) -> Optional[int]:
    """The first purely-numeric stage argument, as the GitHub issue number.

    The loop stage's per-issue workers and the start/review/release stages
    receive a numeric target argument; anything else (flags, slugs, prose) is
    never parsed for digits -- the episodic link must be typed input, not a
    guess (ADR-0017).
    """
    for arg in args:
        if arg.isdigit() and arg.isascii():
            return int(arg)
    return None


def _record_loop_run(workspace_root: str, stage: str, args: List[str], rc: int, session_id: str) -> None:
    """Append one auditable loop-run entry; best-effort, never fails the stage."""
    try:
        from solomon_harness.tools.database_client import DatabaseClient

        with DatabaseClient(harness_dir=workspace_root) as db:
            db.save_loop_run(
                stage=stage,
                target=" ".join(args),
                decision=f"ran /solomon-{stage}",
                status="ok" if rc == 0 else "failed",
                session_id=session_id,
                target_issue=_target_issue_from_args(args),
            )
    except Exception:
        # The ledger is a convenience over the durable store; a logging failure
        # must never block delivery work.
        pass


def _read_command_file(workspace_root: str, stage: str) -> str:
    cmd_file = os.path.join(workspace_root, ".claude", "commands", f"solomon-{stage}.md")
    if not os.path.isfile(cmd_file):
        raise FileNotFoundError(cmd_file)
    with open(cmd_file, "r", encoding="utf-8") as f:
        return f.read()


def build_prompt(workspace_root: str, stage: str, args: List[str]) -> str:
    """Return the command body for a stage with $ARGUMENTS substituted."""
    text = _read_command_file(workspace_root, stage)
    if text.startswith("---"):
        # Drop the YAML frontmatter, keep the prompt body.
        text = "---".join(text.split("---")[2:]).strip()
    return text.replace("$ARGUMENTS", " ".join(args))


def _allowed_tools(workspace_root: str, stage: str) -> Optional[str]:
    """Return the command file's declared ``allowed-tools:`` frontmatter value.

    The headless engine has no TTY, so any tool call outside the ambient
    project settings.json allowlist blocks with no one to approve it (#179).
    Each `.claude/commands/solomon-<stage>.md` already declares, and has
    already been reviewed for, the exact tools that stage needs — this makes
    that existing declaration effective instead of silently discarding it.
    """
    try:
        text = _read_command_file(workspace_root, stage)
    except FileNotFoundError:
        return None
    if not text.startswith("---"):
        return None
    parts = text.split("---")
    if len(parts) < 3:
        return None
    for line in parts[1].splitlines():
        line = line.strip()
        if line.lower().startswith("allowed-tools:"):
            value = line.split(":", 1)[1].strip()
            return value or None
    return None


def run_stage(
    workspace_root: str,
    stage: str,
    args: List[str],
    engine: Optional[str] = None,
) -> int:
    """Run one workflow stage headless through the selected engine."""
    if stage in DEPRECATED_STAGE_ALIASES:
        replacement = DEPRECATED_STAGE_ALIASES[stage]
        print(
            f"Warning: stage '{stage}' is deprecated; running it as '{replacement}'.",
            file=sys.stderr,
        )
        stage = replacement
    if stage not in STAGES:
        print(f"Error: unknown stage '{stage}'. Stages: {', '.join(STAGES)}", file=sys.stderr)
        return 1
    engine = (engine or os.environ.get("SOLOMON_ENGINE") or "claude").lower()
    if engine not in ("claude", "gemini", "agy"):
        print(f"Error: unknown engine '{engine}'. Use 'claude', 'gemini' or 'agy'.", file=sys.stderr)
        return 1

    # `loop` has no command file of its own: it drives N iterations of the
    # `workflow` stage's existing prompt/logic, so the engine sees the same
    # `/solomon-workflow` instructions on every iteration and `--concurrency`
    # never leaks into $ARGUMENTS.
    prompt_stage = stage
    iterations = 1
    prompt_args = args
    if stage == "loop":
        try:
            iterations, prompt_args = _parse_concurrency(args)
        except ValueError as exc:
            print(f"Error: {exc}", file=sys.stderr)
            return 1
        prompt_stage = "workflow"

    try:
        prompt = build_prompt(workspace_root, prompt_stage, prompt_args)
    except FileNotFoundError as exc:
        print(f"Error: command file not found ({exc}). Run 'solomon-harness init' first.", file=sys.stderr)
        return 1

    # Governed-autonomy gate (portable, both hosts): the maturity ladder, the
    # permanent human gate for merge/release/Done, and the kill-switch. At the
    # default "human" level this allows everything, so behavior is unchanged.
    from solomon_harness.loop_policy import LoopPolicy

    policy = LoopPolicy.from_config(workspace_root)
    decision = policy.decide_stage(stage)
    if not decision.allowed:
        print(
            f"Blocked by loop autonomy policy (level {policy.level}): {decision.reason}",
            file=sys.stderr,
        )
        return 3

    # Budget governor: at L2/L3, an exhausted daily cost ceiling degrades the
    # automation path to report-only (it stops drafting/merging), never a human.
    if policy.level in ("L2", "L3") and stage != "workflow":
        from solomon_harness import loop_budget

        if loop_budget.over_ceiling(workspace_root, policy.daily_cost_ceiling):
            print(
                f"Blocked by loop budget: daily cost ceiling reached "
                f"(${policy.daily_cost_ceiling}); degraded to report-only.",
                file=sys.stderr,
            )
            return 3

    # Acquire the single-driver lock for stages that touch git/board state, and —
    # at L3 — for every stage the policy says must hold it (requires_lock), so the
    # "L3 only runs while holding the lock" contract is enforced, not just claimed.
    lock = None
    if stage in LOCKED_STAGES or policy.requires_lock(stage):
        from solomon_harness.loop_lock import LoopLock, LoopLockHeld

        lock = LoopLock(workspace_root, stage=stage)
        try:
            lock.acquire()
        except LoopLockHeld as held:
            print(
                f"Error: another solomon driver holds the loop lock ({held}). "
                "Wait for it to finish, or clear a stale lock with "
                "'solomon-harness loop-lock release'.",
                file=sys.stderr,
            )
            return 1

    capture_cost = policy.level in ("L2", "L3")
    print(f"Running /solomon-{stage} headless via {engine}...")
    try:
        try:
            if engine == "agy":
                exec_path = os.path.expanduser("~/.local/bin/agy")
                if not os.path.isfile(exec_path):
                    exec_path = "agy"
                cmd = [exec_path, "-p", "Execute prompt from stdin", "--dangerously-skip-permissions"]
                if capture_cost:
                    cmd.extend(["-o", "json"])
            elif engine == "gemini":
                cmd = [engine, "-p", "Execute prompt from stdin", "--skip-trust"]
                if capture_cost:
                    cmd.extend(["--output-format", "json"])
            else:
                cmd = [engine, "-p"]
                if capture_cost:
                    cmd.extend(["--output-format", "json"])
                if engine == "claude":
                    allowed_tools = _allowed_tools(workspace_root, prompt_stage)
                    if allowed_tools:
                        cmd.extend(["--allowed-tools", allowed_tools])

            from solomon_harness.subprocess_env import clean_git_env

            rc = 0
            for i in range(iterations):
                if iterations > 1:
                    print(f"-- {prompt_stage} iteration {i + 1}/{iterations} --")
                if capture_cost:
                    # Capture the engine's reported cost into the budget ledger.
                    proc = subprocess.run(
                        cmd,
                        input=prompt, text=True, capture_output=True, check=False,
                        env=clean_git_env(),
                    )
                    out = getattr(proc, "stdout", None)
                    if out:
                        print(out)
                    from solomon_harness import loop_budget

                    cost = loop_budget.parse_engine_cost(out or "")
                    if cost is not None:
                        loop_budget.record(workspace_root, cost, stage=stage)
                else:
                    proc = subprocess.run(cmd, input=prompt, text=True, check=False, env=clean_git_env())
                rc = proc.returncode
                if rc != 0:
                    # A failed iteration stops the run rather than plowing ahead —
                    # consistent with the single confirmed step `loop` takes today.
                    break
        except FileNotFoundError:
            print(f"Error: '{engine}' is not installed or not authenticated.", file=sys.stderr)
            return 1
        if lock is not None:
            _record_loop_run(workspace_root, stage, args, rc, lock.session_id)
        if rc == 0 and stage in LOCKED_STAGES:
            from solomon_harness import notify

            notify.send(workspace_root, f"stage:{stage}", f"/solomon-{stage} {' '.join(args)} -> ok")
        return rc
    finally:
        if lock is not None:
            lock.release()
