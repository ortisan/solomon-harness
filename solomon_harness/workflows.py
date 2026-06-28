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
    "loop", "idea", "issue", "bug", "refine", "start", "review", "release",
    # Standing maintenance loops (Phase 3): generative, open draft PRs only.
    "scan-arch", "scan-dedup",
]

# Stages that drive git/board state (branch, push, merge, release) and must run
# under a single driver. The lock is a portable Python gate run on both hosts —
# the documented concurrent-driver race produced premature merges that bypassed
# the review gate, so honoring an advisory markdown "Step 0" was not enough.
LOCKED_STAGES = {"loop", "start", "review", "release", "scan-arch", "scan-dedup"}


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
            )
    except Exception:
        # The ledger is a convenience over the durable store; a logging failure
        # must never block delivery work.
        pass


def build_prompt(workspace_root: str, stage: str, args: List[str]) -> str:
    """Return the command body for a stage with $ARGUMENTS substituted."""
    cmd_file = os.path.join(workspace_root, ".claude", "commands", f"solomon-{stage}.md")
    if not os.path.isfile(cmd_file):
        raise FileNotFoundError(cmd_file)
    with open(cmd_file, "r", encoding="utf-8") as f:
        text = f.read()
    if text.startswith("---"):
        # Drop the YAML frontmatter, keep the prompt body.
        text = "---".join(text.split("---")[2:]).strip()
    return text.replace("$ARGUMENTS", " ".join(args))


def run_stage(
    workspace_root: str,
    stage: str,
    args: List[str],
    engine: Optional[str] = None,
) -> int:
    """Run one workflow stage headless through the selected engine."""
    if stage not in STAGES:
        print(f"Error: unknown stage '{stage}'. Stages: {', '.join(STAGES)}", file=sys.stderr)
        return 1
    engine = (engine or os.environ.get("SOLOMON_ENGINE") or "claude").lower()
    if engine not in ("claude", "gemini"):
        print(f"Error: unknown engine '{engine}'. Use 'claude' or 'gemini'.", file=sys.stderr)
        return 1
    try:
        prompt = build_prompt(workspace_root, stage, args)
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
    if policy.level in ("L2", "L3") and stage != "loop":
        from solomon_harness import loop_budget

        if loop_budget.over_ceiling(workspace_root, policy.daily_cost_ceiling):
            print(
                f"Blocked by loop budget: daily cost ceiling reached "
                f"(${policy.daily_cost_ceiling}); degraded to report-only.",
                file=sys.stderr,
            )
            return 3

    lock = None
    if stage in LOCKED_STAGES:
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
            if capture_cost:
                # Capture the engine's reported cost into the budget ledger.
                proc = subprocess.run(
                    [engine, "-p", "--output-format", "json"],
                    input=prompt, text=True, capture_output=True, check=False,
                )
                out = getattr(proc, "stdout", None)
                if out:
                    print(out)
                from solomon_harness import loop_budget

                cost = loop_budget.parse_engine_cost(out or "")
                if cost is not None:
                    loop_budget.record(workspace_root, cost, stage=stage)
            else:
                proc = subprocess.run([engine, "-p"], input=prompt, text=True, check=False)
        except FileNotFoundError:
            print(f"Error: '{engine}' is not installed or not authenticated.", file=sys.stderr)
            return 1
        rc = proc.returncode
        if lock is not None:
            _record_loop_run(workspace_root, stage, args, rc, lock.session_id)
        if rc == 0 and stage in LOCKED_STAGES:
            from solomon_harness import notify

            notify.send(workspace_root, f"stage:{stage}", f"/solomon-{stage} {' '.join(args)} -> ok")
        return rc
    finally:
        if lock is not None:
            lock.release()
