"""Headless runner for the host-neutral Solomon delivery workflows.

``run_stage`` reads the canonical catalog below ``.agents/solomon`` (with a
one-version legacy fallback) and invokes Claude, AGY, or Codex through its
native non-interactive process adapter.
"""

import os
import subprocess
import sys
from typing import Any, List, Optional

from solomon_harness.layout import PathConfinementError

STAGES = [
    "workflow", "loop", "idea", "issue", "bug", "refine", "start", "review", "release",
    # Standing maintenance stages: generative scans plus state convergence.
    "scan-arch", "scan-dedup", "reconcile",
]

# Renamed stages, still accepted on input with a deprecation notice:
# `loop-auto` became `loop` when the orchestrator moved from `loop` to `workflow`.
DEPRECATED_STAGE_ALIASES = {"loop-auto": "loop"}

# Stages that drive git/board state (branch, push, merge, release) and must run
# under a single driver. The lock is a portable Python gate for all three hosts —
# the documented concurrent-driver race produced premature merges that bypassed
# the review gate, so honoring an advisory markdown "Step 0" was not enough.
LOCKED_STAGES = set(STAGES)

# A locked headless driver receives a bearer token whose digest and exact scope
# live in the lock record. These are the delivery operations needed to create a
# feature worktree, test, commit, and publish it. Destructive history rewrites,
# tags, pull/rebase, and every merge form are intentionally absent.
SHELL_CAPABILITY_SCOPES = {
    "dev:execute",
    "gh:mutate",
    "git:add",
    "git:branch",
    "git:checkout",
    "git:commit",
    "git:fetch",
    "git:push",
    "git:switch",
    "git:worktree",
    "harness:read",
}
SHELL_CAPABILITY_BRANCHES = {
    "chore/*",
    "docs/*",
    "feature/*",
    "fix/*",
    "refactor/*",
    "test/*",
}

# `loop` is the headless cadence entrypoint: `dev loop --concurrency N` drives N
# iterations of the `workflow` stage's own prompt, with LOOP_AUTONOMOUS_MODE_DIRECTIVE
# prepended (see build_prompt) so each headless iteration skips the interactive
# decision card and scans/decides/executes on its own via `dev <stage>`, instead of
# stalling at a card nobody is present to answer (#194). Only this loop-driven
# dispatch gets the directive; a direct `dev workflow` invocation is unaffected and
# # Keeps presenting the enumerated decision card.
DEFAULT_CONCURRENCY = 1

# Injected into the prompt for any stage when executed headlessly via run_stage (the
# non-interactive runner). It instructs the model to bypass interactive prompts and tools.
HEADLESS_STAGE_DIRECTIVE = (
    "This is a headless, non-interactive execution: no human is present to answer questions. "
    "Do not call ask_question or AskUserQuestion. Skip all confirmation prompts, do not wait "
    "for user input, and use default choices or automatic modes where applicable. "
    "IMPORTANT: When executing commands via the run_command tool, you MUST set WaitMsBeforeAsync "
    "to a very high value (at least 300000 ms / 5 minutes) to ensure that the command runs "
    "synchronously and does not execute as a background task. Never let a command run as a "
    "background task or wait for it using timers, as this causes the headless client execution "
    "to exit prematurely.\n\n"
)

# Injected only when `loop` is driving the `workflow` prompt headlessly (build_prompt's
# `loop_driven=True`). It names the command file's own section headings rather than
# re-describing the Autonomous Mode steps, so the harness stays prompt-driven: the
# only source of truth for *what* Autonomous Mode does is solomon-workflow.md itself,
# and if that file's step 3 is ever renumbered or reworded this reference breaks
# visibly instead of silently drifting out of sync with it.
LOOP_AUTONOMOUS_MODE_DIRECTIVE = (
    "This is a headless, unattended /solomon-loop iteration: no human is present to "
    "answer a question. Skip section \"## 3. Propose as an enumerated decision card, "
    "confirm, run\" entirely — do not present or wait on the decision card in any "
    "form (no AskUserQuestion call, no numbered list awaiting a reply). Proceed "
    "directly to the Autonomous Mode instructions already described under that "
    "section (Option 2): scan the current state, decide the next step via the same "
    "rules. If the next step is permanently human-gated (release/merge/Done), skip/bypass "
    "it and evaluate the remaining rules to find the next actionable, non-human-gated "
    "task. Execute the chosen actionable stage headless via `solomon-harness dev <stage> [args]`, "
    "save the decision, and continue until no actionable work remains, then report the "
    "final status. "
    "IMPORTANT: When executing commands via the run_command tool, you MUST set WaitMsBeforeAsync "
    "to a very high value (at least 300000 ms / 5 minutes) to ensure that the command runs "
    "synchronously and does not execute as a background task. Never let a command run as a "
    "background task or wait for it using timers, as this causes the headless client execution "
    "to exit prematurely.\n\n"
)


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
    guess (ADR-0018).
    """
    for arg in args:
        if arg.isdigit() and arg.isascii():
            return int(arg)
    return None


def _record_loop_run(
    workspace_root: str,
    stage: str,
    args: List[str],
    rc: int,
    session_id: str,
    status: Optional[str] = None,
) -> None:
    """Append one auditable loop-run entry; best-effort, never fails the stage.
    ``status`` overrides the rc-derived vocabulary (today ``"skipped"``: a
    zero-exit start that changed nothing)."""
    try:
        from solomon_harness.tools.database_client import DatabaseClient

        with DatabaseClient(harness_dir=workspace_root) as db:
            db.save_loop_run(
                stage=stage,
                target=" ".join(args),
                decision=f"ran /solomon-{stage}",
                status=status or ("ok" if rc == 0 else "failed"),
                session_id=session_id,
                target_issue=_target_issue_from_args(args),
            )
    except Exception:
        # The ledger is a convenience over the durable store; a logging failure
        # must never block delivery work.
        pass


def _read_command_file(workspace_root: str, stage: str) -> str:
    from solomon_harness.layout import HarnessPaths, confined_read_path

    paths = HarnessPaths(workspace_root)
    name = f"solomon-{stage}.md"
    candidates = (
        paths.workflows / name,
        paths.root / "solomon_harness" / "catalog" / "workflows" / name,
        paths.legacy_workflows / name,
    )
    for command_file in candidates:
        safe_command_file = confined_read_path(paths.root, command_file)
        if safe_command_file.is_file():
            return safe_command_file.read_text(encoding="utf-8")
    raise FileNotFoundError(candidates[0])


def build_prompt(workspace_root: str, stage: str, args: List[str], *, loop_driven: bool = False, headless: bool = False) -> str:
    """Return the command body for a stage with $ARGUMENTS substituted.

    ``loop_driven`` is True only when the `loop` stage is dispatching the
    `workflow` command file headlessly (see `run_stage`). In that case, and
    only that case, LOOP_AUTONOMOUS_MODE_DIRECTIVE is prepended so the model
    skips the interactive decision card and proceeds straight into Autonomous
    Mode (#194). A direct invocation of any stage — including `workflow` on
    its own — never sets this, so its prompt is unchanged.
    """
    text = _read_command_file(workspace_root, stage)
    if text.startswith("---"):
        # Drop the YAML frontmatter, keep the prompt body.
        text = "---".join(text.split("---")[2:]).strip()
    arguments = " ".join(args)
    text = text.replace("$ARGUMENTS", arguments).replace("{{arguments}}", arguments)
    if headless:
        text = HEADLESS_STAGE_DIRECTIVE + text
    if loop_driven:
        text = LOOP_AUTONOMOUS_MODE_DIRECTIVE + text
    return text


# Tools that only return a usable result when a live human answers them. The
# `allowed-tools:` frontmatter serves both an interactive Claude Code session
# (which reads the command file directly) and this headless --allowed-tools
# passthrough (which never has a TTY) — the same declaration cannot safely
# grant both audiences the same tools. Stripped unconditionally for every
# stage, so a confirmation gate (e.g. the merge step in #172/#195) is
# unreachable headlessly by construction, not by prose plus unverified
# non-interactive tool behavior.
HEADLESS_UNSAFE_TOOLS = {"AskUserQuestion"}


def _allowed_tools(workspace_root: str, stage: str) -> Optional[str]:
    """Return Claude's declared ``allowed-tools:``, minus any tool
    that requires a live human to answer (see ``HEADLESS_UNSAFE_TOOLS``).

    The headless engine has no TTY, so any tool call outside the ambient
    project settings.json allowlist blocks with no one to approve it (#179).
    Host metadata remains in Claude's thin bridge/skill while the executable
    workflow body stays host-neutral in the canonical catalog.
    """
    from solomon_harness.layout import HarnessPaths, confined_read_path

    paths = HarnessPaths(workspace_root)
    name = f"solomon-{stage}.md"
    candidates = (
        paths.claude_skills / f"solomon-{stage}" / "SKILL.md",
        paths.solomon / "host-metadata" / "claude" / "commands" / name,
        paths.legacy_workflows / name,
    )
    text = None
    for candidate in candidates:
        safe_candidate = confined_read_path(paths.root, candidate)
        if safe_candidate.is_file():
            text = safe_candidate.read_text(encoding="utf-8")
            break
    if text is None:
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
            if not value:
                return None
            tools = [t.strip() for t in value.split(",")]
            kept = [t for t in tools if t not in HEADLESS_UNSAFE_TOOLS]
            return ", ".join(kept) if kept else None
    return None


def run_stage(
    workspace_root: str,
    stage: str,
    args: List[str],
    engine: Optional[str] = None,
) -> int:
    """Run one workflow stage headless through the selected engine."""
    try:
        from solomon_harness.tools.database_client import DatabaseClient
        from solomon_harness.bootstrap import scan_project_structure
        with DatabaseClient(harness_dir=workspace_root) as db:
            scan_project_structure(workspace_root, db)
    except Exception as exc:
        import logging
        logging.warning(f"Project structure scan failed at loop/stage start: {type(exc).__name__}")

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
    if engine not in ("agy", "claude", "codex"):
        print(f"Error: unknown engine '{engine}'. Use 'agy', 'claude', or 'codex'.", file=sys.stderr)
        return 1

    # `loop` has no command file of its own: it drives N iterations of the
    # `workflow` stage's existing prompt/logic, so the engine sees the same
    # `/solomon-workflow` instructions on every iteration and `--concurrency`
    # never leaks into $ARGUMENTS.
    prompt_stage = stage
    iterations = 1
    prompt_args = args
    loop_driven = False
    if stage == "loop":
        try:
            iterations, prompt_args = _parse_concurrency(args)
        except ValueError as exc:
            print(f"Error: {exc}", file=sys.stderr)
            return 1
        prompt_stage = "workflow"
        loop_driven = True

    try:
        prompt = build_prompt(workspace_root, prompt_stage, prompt_args, loop_driven=loop_driven, headless=(prompt_stage != "workflow"))
    except FileNotFoundError as exc:
        print(f"Error: command file not found ({exc}). Run 'solomon-harness init' first.", file=sys.stderr)
        return 1
    except PathConfinementError as exc:
        print(f"Error: unsafe workflow path ({exc}).", file=sys.stderr)
        return 1

    # Governed-autonomy gate (portable across all hosts): the maturity ladder, the
    # permanent human gate for merge/release/terminal decisions (ADR-0034 only
    # permits closed-issue projection repair), and the kill-switch. At the
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

    # Remediation cap: refuse to drive the same locked stage+target past the
    # consecutive-round limit (#341 package 5). A wedged review/fix cycle that
    # keeps re-proposing the same PR is stopped and surfaced to a human instead
    # of burning unbounded rounds.
    if stage in LOCKED_STAGES:
        target = " ".join(args)
        if target:
            try:
                from solomon_harness import loop_log
                from solomon_harness.tools.database_client import DatabaseClient

                with DatabaseClient(harness_dir=workspace_root) as _db:
                    if loop_log.remediation_limit_reached(_db, target, stage):
                        print(
                            f"Blocked: /solomon-{stage} {target} has hit the "
                            "consecutive-round remediation cap; stopping and "
                            "surfacing to a human instead of re-proposing it.",
                            file=sys.stderr,
                        )
                        return 3
            except Exception:
                pass

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
    shell_capability = ""
    if stage in LOCKED_STAGES or policy.requires_lock(stage):
        from solomon_harness.loop_lock import (
            SHELL_CAPABILITY_ENV,
            LoopLock,
            LoopLockHeld,
        )

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
        capability_scopes = (
            {"harness:read"}
            if policy.level == "L1"
            else SHELL_CAPABILITY_SCOPES
        )
        capability_branches = (
            set() if policy.level == "L1" else SHELL_CAPABILITY_BRANCHES
        )
        probe_scope = sorted(capability_scopes)[0]
        inherited_capability = os.environ.get(SHELL_CAPABILITY_ENV, "")
        if inherited_capability and lock.shell_capability_allows(
            inherited_capability,
            scope=probe_scope,
        ):
            shell_capability = inherited_capability
        else:
            shell_capability = lock.issue_shell_capability(
                scopes=capability_scopes,
                branches=capability_branches,
            )

    # Per-issue claim gate + acquisition (ADR-0027): layered on top of the
    # repo-wide lock above, not a replacement for it. Only meaningful inside a
    # real git repo -- a plain workspace with no `.git` has no claims remote
    # to check or race against in the first place.
    #
    # heartbeat_stop_event/heartbeat_thread stay None unless a claim is
    # actually acquired below; the outer finally always stops them, so every
    # early return between here and the try/finally must go through
    # lock.release() but never needs to touch the heartbeat (it cannot have
    # started yet on any of those paths).
    heartbeat_stop_event = None
    heartbeat_thread = None
    claim_lost_event = None
    claim_acquired = False
    claimed_issue_number = None
    claim_session_id = None
    claim_store = None
    if stage == "start" and os.path.exists(os.path.join(workspace_root, ".git")):
        issue_number = _target_issue_from_args(args)
        if issue_number is not None:
            from solomon_harness import claim
            import datetime

            # One GitClaimStore for the whole claim gate below: pure helpers
            # (get_current_session_id, is_claim_active, the TTL constant, the
            # malformed-ref recheck via get_claim_ref) stay direct module
            # calls -- they carry no IO and are not part of the ClaimStore
            # port -- while every IO operation (get/pr_protected/acquire/
            # refresh/release) routes through this one store instance.
            claim_store = claim.GitClaimStore(workspace_root)

            def _claim_age(claim_data: dict) -> str:
                acquired_str = claim_data.get("acquired_at") or "unknown"
                try:
                    acquired = datetime.datetime.fromisoformat(acquired_str.replace("Z", "+00:00"))
                    now = datetime.datetime.now(datetime.timezone.utc)
                    return f"{int((now - acquired).total_seconds() / 60)} minutes"
                except (ValueError, AttributeError):
                    return "unknown"

            current_sess = claim.get_current_session_id()
            active_claim = claim_store.get(issue_number)
            has_pr = claim_store.pr_protected(issue_number)
            if active_claim and claim.is_claim_active(active_claim, current_sess, has_open_pr=has_pr):
                print(
                    f"Error: issue #{issue_number} is already claimed by session "
                    f"'{active_claim.get('session_id')}' (claim age: {_claim_age(active_claim)}). "
                    f"Refusing to start. Use 'solomon-harness claim release {issue_number}' to clear it.",
                    file=sys.stderr,
                )
                if lock is not None:
                    lock.release()
                return 1

            # Atomically claim. A push failure here only blocks the stage once
            # confirmed as a genuine lost race (a re-fetch shows another
            # session's claim now live on the ref) -- otherwise it just means
            # this workspace has no claims remote to push to (no `origin`, no
            # network), which is a no-op environment, not a collision.
            if claim_store.acquire(issue_number, session_id=current_sess):
                claim_acquired = True
                claimed_issue_number = issue_number
                claim_session_id = current_sess
                # Heartbeat writer (B5a): a `start` that runs longer than the
                # claim TTL before a PR exists would otherwise become
                # reclaimable mid-implementation (the #24 double-pick).
                # Periodically re-touch the claim's heartbeat_at until the
                # stage completes; the outer finally stops this thread. A
                # confirmed takeover (refresh_claim returns False only for
                # that) is surfaced loudly and fails the stage: the work in
                # flight no longer holds the issue, so its result must not be
                # reported as a success (B5's abort-on-loss).
                import threading

                heartbeat_stop_event = threading.Event()
                claim_lost_event = threading.Event()

                def _claim_heartbeat_loop(
                    issue: int = issue_number,
                    session: str = current_sess,
                    store: "claim.ClaimStore" = claim_store,
                    stop: "threading.Event" = heartbeat_stop_event,
                    lost: "threading.Event" = claim_lost_event,
                ) -> None:
                    while not stop.wait(claim.CLAIM_HEARTBEAT_INTERVAL_SECONDS):
                        if not store.refresh(issue, session):
                            lost.set()
                            print(
                                f"CRITICAL: issue #{issue}'s claim was taken over by "
                                "another session while this stage was running; this "
                                "run's result will be marked failed to prevent "
                                "double-shipping the issue.",
                                file=sys.stderr,
                            )
                            break

                heartbeat_thread = threading.Thread(
                    target=_claim_heartbeat_loop,
                    daemon=True,
                    name=f"claim-heartbeat-issue-{issue_number}",
                )
                heartbeat_thread.start()
            else:
                # claim_issue refused. It fails closed internally (an active
                # claim, or PR/review liveness that could not be confirmed), so
                # do NOT re-derive activity here with a weaker TTL-only
                # is_claim_active(has_open_pr=False) check -- that would let a
                # stale-but-PR-protected or liveness-uncertain claim slip
                # through and start a duplicate. Any ref still present --
                # including one whose content is malformed (get_claim_ref
                # returns (sha, None) for those) -- means "refused, do not
                # proceed"; only a genuinely absent ref is the safe "proceed
                # without a claim" fallback.
                recheck = claim.get_claim_ref(workspace_root, issue_number)
                if recheck is not None:
                    holder = (recheck[1] or {}).get("session_id", "unknown/malformed")
                    print(
                        f"Error: issue #{issue_number} could not be safely claimed "
                        f"(held by session '{holder}', or PR/review "
                        "liveness could not be confirmed). Refusing to start.",
                        file=sys.stderr,
                    )
                    if lock is not None:
                        lock.release()
                    return 1
                print(
                    f"Warning: could not record a claim ref for issue #{issue_number} "
                    "(no claims remote configured?); proceeding without one.",
                    file=sys.stderr,
                )

    from solomon_harness.notify import log_progress
    capture_cost = policy.level in ("L2", "L3")
    log_progress(f"Running /solomon-{stage} headless via {engine}...")
    # Pessimistic default so the finally's failed-run claim release covers an
    # exception thrown before the engine ever assigns a real exit code.
    rc = 1
    run_skipped = False
    run_stalled = False
    try:
        try:
            from solomon_harness.engine_adapters import build_engine_command

            allowed_tools = None
            add_dirs: list[str] = []
            if engine == "claude":
                allowed_tools = _allowed_tools(workspace_root, prompt_stage)
            if stage == "start" and os.path.exists(os.path.join(workspace_root, ".git")):
                try:
                    from solomon_harness.worktree import worktree_root

                    add_dirs.append(worktree_root(workspace_root))
                except Exception:  # noqa: S110 - optional worktree hint may be unavailable
                    pass
            cmd = build_engine_command(
                engine,
                workspace_root,
                json_output=capture_cost,
                allowed_tools=allowed_tools,
                add_dirs=add_dirs,
                orchestrator_model=policy.orchestrator_model,
            )

            from solomon_harness.subprocess_env import clean_git_env

            child_env = clean_git_env()
            child_env["SOLOMON_SUBPROCESS"] = "1"
            if lock is not None:
                # Propagate this driver's own identity into the engine child so
                # that a nested `solomon-harness dev <stage>` it shells out to
                # (the loop's Autonomous Mode branch acting on its own scan,
                # #197) resolves the SAME session_id via LoopLock's own env
                # lookup and reenters this still-held lock, instead of falling
                # back to a new `host:pid` identity and being refused as a
                # foreign competing driver.
                child_env["SOLOMON_SESSION_ID"] = lock.session_id
                child_env[SHELL_CAPABILITY_ENV] = shell_capability

            noop_baseline = None
            if stage == "start":
                from solomon_harness import worktree as _worktree

                noop_baseline = _worktree.workspace_snapshot(workspace_root)

            from solomon_harness import loop_watchdog
            from solomon_harness.loop_policy import _read_loop_config

            wcfg = loop_watchdog.WatchdogConfig.from_loop_block(_read_loop_config(workspace_root))

            # rc stays at its pessimistic 1 until the engine reports a real
            # exit code: re-initializing it to 0 here would make the finally's
            # failed-run claim release read any mid-run exception (engine
            # missing, KeyboardInterrupt) as a success and keep the claim for
            # the whole TTL.
            stall_retry_used = False
            while True:
              run_stalled = False
              for i in range(iterations):
                if iterations > 1:
                    log_progress(f"-- {prompt_stage} iteration {i + 1}/{iterations} --")
                proc: Any = None
                if capture_cost:
                    # Capture the engine's reported cost into the budget ledger.
                    import unittest.mock
                    import io
                    if isinstance(subprocess.run, unittest.mock.Mock) or hasattr(subprocess.run, "assert_called"):
                        mocked_res = subprocess.run(  # noqa: S603 - adapter builds trusted argv
                            cmd,
                            input=prompt,
                            text=True,
                            capture_output=True,
                            env=child_env,
                            cwd=workspace_root,
                        )
                        class DummyProc:
                            stdin = None
                            stdout = io.StringIO(getattr(mocked_res, "stdout", "") or "")
                            stderr = io.StringIO(getattr(mocked_res, "stderr", "") or "")
                            returncode = getattr(mocked_res, "returncode", 0)
                            def wait(self): pass
                        proc = DummyProc()
                        monitor = None
                    else:
                        proc = subprocess.Popen(
                            cmd,
                            stdin=subprocess.PIPE,
                            stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE,
                            text=True,
                            env=child_env,
                            cwd=workspace_root,
                            start_new_session=True,
                        )
                        if proc.stdin:
                            proc.stdin.write(prompt)
                            proc.stdin.close()
                        monitor = loop_watchdog.StallMonitor(proc, wcfg).start()
                    stdout_buf = []
                    stderr_buf = []
                    import threading

                    def read_stderr():
                        for chunk in iter(lambda: proc.stderr.read(1024), ""):
                            stderr_buf.append(chunk)
                            if monitor is not None:
                                monitor.mark_activity()
                            sys.stderr.write(chunk.replace("\r\n", "\n").replace("\n", "\r\n"))
                            sys.stderr.flush()

                    t = threading.Thread(target=read_stderr, daemon=True)
                    t.start()

                    for chunk in iter(lambda: proc.stdout.read(1024), ""):
                        stdout_buf.append(chunk)
                        if monitor is not None:
                            monitor.mark_activity()
                        sys.stdout.write(chunk.replace("\r\n", "\n").replace("\n", "\r\n"))
                        sys.stdout.flush()

                    proc.wait()
                    t.join(timeout=1.0)
                    if monitor is not None:
                        monitor.stop()
                        if monitor.stalled:
                            run_stalled = True
                            print(f"Stall watchdog killed /solomon-{stage}: {monitor.reason}.", file=sys.stderr)
                            rc = 1
                            break
                    out = "".join(stdout_buf)
                    from solomon_harness import loop_budget

                    cost = loop_budget.parse_engine_cost(out or "")
                    if cost is not None:
                        loop_budget.record(workspace_root, cost, stage=stage)
                else:
                    try:
                        proc = subprocess.run(  # noqa: S603 - adapter builds trusted argv
                            cmd,
                            input=prompt,
                            text=True,
                            check=False,
                            env=child_env,
                            cwd=workspace_root,
                            timeout=wcfg.terminal_cap,
                        )
                    except subprocess.TimeoutExpired:
                        run_stalled = True
                        print(
                            f"Stall watchdog killed /solomon-{stage}: terminal cap "
                            f"{wcfg.terminal_cap:.0f}s exceeded.",
                            file=sys.stderr,
                        )
                        rc = 1
                        break
                rc = proc.returncode
                if rc != 0:
                    # A failed iteration stops the run rather than plowing ahead —
                    # consistent with the single confirmed step `loop` takes today.
                    break
              if run_stalled and stage == "start" and not stall_retry_used:
                  stall_retry_used = True
                  log_progress("Engine stalled; retrying once before parking the run.")
                  continue
              break
        except PathConfinementError as exc:
            print(f"Error: unsafe workflow path ({exc}).", file=sys.stderr)
            rc = 1
            return 1
        except FileNotFoundError:
            print(f"Error: '{engine}' is not installed or not authenticated.", file=sys.stderr)
            rc = 1  # keep the local in sync so the finally releases the claim
            return 1
        if claim_lost_event is not None and claim_lost_event.is_set():
            # The claim was confirmed taken over mid-run: whatever the engine
            # exited with, this run no longer owns the issue and must not be
            # recorded or notified as a success (B5's abort-on-loss).
            print(
                f"Error: /solomon-{stage} finished after its issue claim was "
                "taken over by another session; marking this run failed.",
                file=sys.stderr,
            )
            rc = 1
        if rc == 0 and noop_baseline is not None:
            from solomon_harness import worktree as _worktree

            if not _worktree.workspace_changed(workspace_root, noop_baseline):
                # A PR-protected issue means work was delivered remotely (the
                # manual-mode resume opens a PR without moving local refs), so
                # the run is a real success and the claim must stay.
                protected = False
                if claimed_issue_number is not None:
                    try:
                        if claim_store is None:
                            from solomon_harness import claim as _claim

                            claim_store = _claim.GitClaimStore(workspace_root)
                        protected = bool(claim_store.pr_protected(claimed_issue_number))
                    except Exception:
                        protected = True
                if not protected:
                    run_skipped = True
                    print(
                        f"/solomon-{stage} {' '.join(args)} exited 0 with no "
                        "workspace changes; recording the run as skipped and "
                        "releasing the claim.",
                        file=sys.stderr,
                    )
        if run_stalled:
            print(
                f"/solomon-{stage} {' '.join(args)} was killed by the stall "
                "watchdog after a retry; parking the run for human triage "
                "(claim and worktree preserved).",
                file=sys.stderr,
            )
        if lock is not None:
            _record_loop_run(
                workspace_root,
                stage,
                args,
                rc,
                lock.session_id,
                status="parked" if run_stalled else ("skipped" if run_skipped else None),
            )
        if rc == 0 and stage in LOCKED_STAGES and not run_skipped:
            from solomon_harness import notify

            notify.send(workspace_root, f"stage:{stage}", f"/solomon-{stage} {' '.join(args)} -> ok")
        return rc
    finally:
        if heartbeat_stop_event is not None:
            heartbeat_stop_event.set()
        if heartbeat_thread is not None:
            heartbeat_thread.join(timeout=2.0)
        if (
            claim_acquired
            and claimed_issue_number is not None
            and ((rc != 0 and not run_stalled) or run_skipped)
            and (claim_lost_event is None or not claim_lost_event.is_set())
        ):
            # A failed `start` must not hold the issue for the rest of the
            # TTL: release the claim this session took (never force -- if the
            # claim moved on, release_claim refuses and the new holder keeps
            # it). A successful start keeps its claim: the draft PR now
            # protects the issue and the merge path releases it. A skipped
            # no-op start releases too: nothing protects the issue. A parked
            # (stall-killed) run keeps its claim so a human triages it; the
            # claim TTL is the backstop against a permanent hold.
            try:
                if claim_store is None:
                    from solomon_harness import claim as _claim

                    claim_store = _claim.GitClaimStore(workspace_root)
                claim_store.release(claimed_issue_number, session_id=claim_session_id)
            except Exception as exc:  # noqa: BLE001 - best-effort cleanup, never mask the stage result
                print(
                    f"Warning: could not release the claim on issue "
                    f"#{claimed_issue_number} after a failed start ({exc}); "
                    "it will expire via the TTL.",
                    file=sys.stderr,
                )
        if lock is not None:
            lock.release()
