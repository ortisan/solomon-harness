#!/usr/bin/env python3
"""Harness command line interface, shared by every agent.

Agents invoke this through a thin entrypoint that passes its own directory as
``harness_dir`` so the loop reads that agent's config, persona and memory store.
"""

import argparse
import os
import sys
from typing import Optional, List


def _subagent_description(filepath: str) -> str:
    """Return a one-line description for a generated subagent file.

    Prefers the YAML front-matter ``description:`` field, falling back to the
    first non-heading line of the body.
    """
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            lines = f.readlines()
    except OSError:
        return ""

    if lines and lines[0].strip() == "---":
        for line in lines[1:]:
            stripped = line.strip()
            if stripped == "---":
                break
            if stripped.lower().startswith("description:"):
                return stripped.split(":", 1)[1].strip()

    for line in lines:
        stripped = line.strip()
        if stripped and not stripped.startswith("#") and stripped != "---":
            return stripped
    return ""


def _generate_integrations(workspace_root: str) -> None:
    """Regenerate the host-tool integrations (.claude/agents, .gemini/commands).

    Loaded from scripts/generate-integrations.py so the compile step keeps the
    Claude subagents and Gemini commands in sync with the agents/ and
    .claude/commands/ sources. A no-op when the script is absent.
    """
    import importlib.util

    gi_path = os.path.join(workspace_root, "scripts", "generate-integrations.py")
    if not os.path.isfile(gi_path):
        return
    spec = importlib.util.spec_from_file_location("generate_integrations", gi_path)
    if spec and spec.loader:
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        module.generate(workspace_root)


def handle_db_init(harness_dir: str) -> None:
    """Initializes the database client for the given harness directory."""
    from solomon_harness.tools.database_client import DatabaseClient

    try:
        with DatabaseClient(harness_dir=harness_dir) as db:
            print(f"Database initialized successfully at: {db.db_path}")
    except Exception as e:
        print(f"Error: Failed to initialize database: {e}", file=sys.stderr)
        sys.exit(1)


def handle_eval(harness_dir: str) -> None:
    """Runs the shared agent evaluation suite against this harness directory."""
    import unittest
    from solomon_harness.evals import build_agent_suite

    print(f"Running agent evaluations for {harness_dir}...")
    suite = build_agent_suite(harness_dir)
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    if not result.wasSuccessful():
        sys.exit(1)
    else:
        sys.exit(0)


def handle_run(harness_dir: str, task=None) -> None:
    """Show where the team stopped and point to the delivery workflows.

    The harness does not run a model itself; the host tool (Claude Code or the
    Gemini CLI) provides the execution loop and the /solomon-* workflows.
    This command resumes context from the project memory and lists those
    workflows. It no longer simulates task execution.
    """
    from solomon_harness.tools.database_client import DatabaseClient

    try:
        db_client = DatabaseClient(harness_dir=harness_dir)
    except Exception as e:
        print(f"Error: Failed to initialize database client: {e}", file=sys.stderr)
        sys.exit(1)

    from solomon_harness.voice import say

    with db_client as db:
        print(say("project status"))

        # One-screen board digest: resume point, open work, the last loop run,
        # and PRs awaiting review. Facts only; the next step is decided by
        # /solomon-loop, never computed here.
        from solomon_harness.digest import gather_digest

        print()
        for line in gather_digest(harness_dir, db):
            print(line)

        # Surface any pending initialization items (Docker down, memory on the
        # SQLite fallback, missing board scope, global install not run).
        try:
            from solomon_harness.healthcheck import pending_summary, run_checks

            pending = pending_summary(run_checks(harness_dir))
            if pending:
                print(say("\nPending initialization (run 'solomon-harness healthcheck' for detail):"))
                for item in pending:
                    print(f"  - {item}")
        except Exception as e:
            print(f"Warning: could not run healthcheck: {e}", file=sys.stderr)

        if task:
            print(
                "\nTasks are not auto-run here. Start this one with a workflow, "
                f'e.g.  /solomon-issue "{task}"'
            )

        print("\nDelivery workflows (run in Claude Code or the Gemini CLI):")
        workflows = [
            ("/solomon-loop", "scan where work stopped and propose the next step"),
            ("/solomon-idea", "capture a product idea"),
            ("/solomon-issue", "create a feature or story issue"),
            ("/solomon-bug", "create a bug report"),
            ("/solomon-refine", "refine an issue to Ready"),
            ("/solomon-start", "start development: branch, plan, TDD, draft PR"),
            ("/solomon-review", "review a pull request"),
            ("/solomon-release", "deliver and release"),
        ]
        for name, desc in workflows:
            print(f"  {name:<21} {desc}")
        print("\nHeadless (CI/automation):  solomon-harness dev <stage> [args]")


def handle_loop_lock(workspace_root: str, action: str) -> None:
    """Inspect or clear the single-driver loop lock (recovery after a crash)."""
    from solomon_harness.loop_lock import LoopLock

    lock = LoopLock(workspace_root)
    info = lock.read()

    if action == "status":
        if not info:
            print(f"No loop lock held. ({lock.path})")
            return
        state = "STALE (reclaimable)" if lock.is_stale(info) else "live"
        print(f"Loop lock: {lock.path}")
        print(f"  session:   {info.get('session_id')}  pid: {info.get('pid')}  host: {info.get('host')}")
        print(f"  stage:     {info.get('stage')}")
        print(f"  acquired:  {info.get('acquired_at')}")
        print(f"  heartbeat: {info.get('heartbeat_at')}")
        print(f"  state:     {state}")
        return

    # release: force-remove for recovery, warning if a live foreign driver owns it.
    if not info:
        print("No loop lock to release.")
        return
    if info.get("session_id") != lock.session_id and not lock.is_stale(info):
        print(
            f"Warning: lock is held by a live driver (session {info.get('session_id')}, "
            f"pid {info.get('pid')}). Removing anyway.",
            file=sys.stderr,
        )
    try:
        os.remove(lock.path)
        print(f"Released loop lock at {lock.path}")
    except FileNotFoundError:
        print("No loop lock to release.")


def handle_loop_guard(workspace_root: str) -> None:
    """PreToolUse hook: block git push / gh pr merge under a live foreign lock.

    Reads the Claude Code hook payload from stdin. Exits 2 to block (the message
    is fed back to the model), 0 to allow. Fail-open: any error allows the tool,
    because the portable enforcement is the run_stage gate, not this hook.
    """
    import json as _json

    try:
        raw = sys.stdin.read()
        payload = _json.loads(raw) if raw.strip() else {}
    except Exception:
        sys.exit(0)

    try:
        from solomon_harness.loop_lock import LoopLock, guard_verdict

        lock = LoopLock(workspace_root, session_id=payload.get("session_id"))
        block, reason = guard_verdict(payload, lock)
    except Exception:
        sys.exit(0)

    if block:
        print(reason, file=sys.stderr)
        sys.exit(2)
    sys.exit(0)


def handle_log(workspace_root: str, last: int) -> None:
    """Print the read-only loop activity feed over the project memory."""
    from solomon_harness import loop_log
    from solomon_harness.tools.database_client import DatabaseClient

    try:
        with DatabaseClient(harness_dir=workspace_root) as db:
            entries = loop_log.gather_feed(db, last=last)
    except Exception as e:
        print(f"Error: could not read loop activity: {e}", file=sys.stderr)
        sys.exit(1)
    for line in loop_log.format_feed(entries):
        print(line)


def main(harness_dir: Optional[str] = None, argv: Optional[List[str]] = None) -> None:
    """Parser setup and command dispatching.

    Args:
        harness_dir: The agent directory the thin entrypoint is running from.
            Defaults to the current working directory when omitted.
        argv: Optional argument list (defaults to sys.argv[1:]).
    """
    parser = argparse.ArgumentParser(description="Solomon Harness Agent Command Line Interface")
    subparsers = parser.add_subparsers(dest="command", help="Available subcommands")

    subparsers.add_parser("db-init", help="Initialize the long-term database client and tables")
    subparsers.add_parser("eval", help="Run the agent evaluations test suite")
    run_parser = subparsers.add_parser("run", help="Simulate running a task")
    run_parser.add_argument("task", type=str, nargs="?", default=None, help="The task description to execute (optional)")

    # New subcommands for workspace management
    init_parser = subparsers.add_parser("init", help="Initialize workspace configuration and rules")
    init_parser.add_argument("--non-interactive", action="store_true", help="Run in non-interactive mode using default configurations")

    subparsers.add_parser(
        "compile",
        help="Compile agent harnesses and regenerate host-tool integrations",
    )
    subparsers.add_parser("index", help="Index project codebase into the database memory")
    subparsers.add_parser("wiki", help="Refresh the living code-overview wiki page from the index")

    mem_up = subparsers.add_parser("memory-up", help="Start the memory backend (docker compose) if it is not already running")
    mem_up.add_argument("--wait", type=int, default=25, help="Seconds to wait for the backend port after starting")
    subparsers.add_parser("memory-down", help="Stop the memory backend (docker compose down)")

    ig_parser = subparsers.add_parser(
        "install-global",
        help="Install agents, /solomon commands, the session hook, and the shared memory home into ~/.claude and ~/.solomon-harness",
    )
    ig_parser.add_argument("--no-mcp", action="store_true", help="Skip MCP server registration with the host CLI")

    doctor_parser = subparsers.add_parser("doctor", help="Check (and install) prerequisites")
    doctor_parser.add_argument("--no-install", action="store_true", help="Only report; do not install")

    subparsers.add_parser("healthcheck", help="Report runtime readiness and pending init items (Docker, memory, board, global install)")

    loop_lock_parser = subparsers.add_parser(
        "loop-lock", help="Inspect or clear the single-driver loop lock"
    )
    loop_lock_parser.add_argument(
        "action", choices=["status", "release"], nargs="?", default="status",
        help="status (default) shows the holder; release clears a stale or stuck lock",
    )

    log_parser = subparsers.add_parser(
        "log", help="Show the loop activity feed (loop runs, decisions, handoffs)"
    )
    log_parser.add_argument("--last", type=int, default=20, help="How many recent entries to show")

    subparsers.add_parser(
        "loop-guard",
        help="PreToolUse hook: block push/merge while another driver holds the loop lock (reads the hook payload on stdin)",
    )

    dev_parser = subparsers.add_parser("dev", help="Run a delivery workflow headless (loop, idea, issue, bug, refine, start, review, release)")
    dev_parser.add_argument("stage", type=str, help="The workflow stage")
    dev_parser.add_argument("dev_args", nargs=argparse.REMAINDER, help="Arguments passed to the workflow")

    skills_parser = subparsers.add_parser("skills", help="Manage agent skills")
    skills_parser.add_argument("skills_args", nargs=argparse.REMAINDER, help="Arguments passed to skills manager")

    agents_parser = subparsers.add_parser("agents", help="List and show agent definitions")
    agents_subparsers = agents_parser.add_subparsers(dest="agents_command", help="Agents subcommands")
    agents_subparsers.add_parser("list", help="List all available agents")
    agents_subparsers.add_parser("help", help="Display usage instructions")
    show_parser = agents_subparsers.add_parser("show", help="Show specific agent profile")
    show_parser.add_argument("agent_name", type=str, help="Agent name")

    args = parser.parse_args(argv)

    if harness_dir is None:
        harness_dir = os.getcwd()

    # Determine workspace root
    project_root = harness_dir
    found_root = False
    while project_root and project_root != os.path.dirname(project_root):
        if os.path.exists(os.path.join(project_root, ".git")):
            found_root = True
            break
        if (
            os.path.exists(os.path.join(project_root, "agents"))
            and os.path.exists(os.path.join(project_root, "memory"))
        ):
            found_root = True
            break
        project_root = os.path.dirname(project_root)
    workspace_root = project_root if found_root else harness_dir

    if args.command == "db-init":
        handle_db_init(harness_dir)
    elif args.command == "eval":
        handle_eval(harness_dir)
    elif args.command == "run":
        handle_run(harness_dir, args.task)
    elif args.command == "init":
        from solomon_harness.bootstrap import bootstrap_project
        bootstrap_project(workspace_root, non_interactive=args.non_interactive)
    elif args.command == "doctor":
        from solomon_harness.prereqs import check_prerequisites
        sys.exit(0 if check_prerequisites(auto_install=not args.no_install) else 1)
    elif args.command == "healthcheck":
        from solomon_harness.healthcheck import format_report, run_checks
        checks = run_checks(workspace_root)
        print(format_report(checks))
        sys.exit(1 if any(c["status"] == "fail" for c in checks) else 0)
    elif args.command == "loop-lock":
        handle_loop_lock(workspace_root, args.action)
    elif args.command == "loop-guard":
        handle_loop_guard(workspace_root)
    elif args.command == "log":
        handle_log(workspace_root, args.last)
    elif args.command == "dev":
        from solomon_harness.workflows import run_stage
        sys.exit(run_stage(workspace_root, args.stage, args.dev_args))
    elif args.command == "compile":
        from solomon_harness.bootstrap import scaffold_agents
        scaffold_agents(workspace_root)
        # Keep the host-tool integrations in sync so they never drift from source.
        _generate_integrations(workspace_root)
    elif args.command == "index":
        from solomon_harness.bootstrap import index_codebase
        from solomon_harness.tools.database_client import DatabaseClient
        try:
            with DatabaseClient(harness_dir=workspace_root) as db:
                index_codebase(workspace_root, db)
        except Exception as e:
            print(f"Error: Codebase indexing failed: {e}", file=sys.stderr)
            sys.exit(1)
    elif args.command == "memory-up":
        from solomon_harness.memory import _describe, ensure_memory_up
        result = ensure_memory_up(workspace_root, wait_seconds=args.wait)
        print(_describe(result))
        # Never fail the session-start hook: a missing Docker daemon must not
        # block work, because the client falls back to SQLite.
    elif args.command == "memory-down":
        from solomon_harness.memory import _describe, stop_memory
        result = stop_memory(workspace_root)
        print(_describe(result))
        sys.exit(0 if result.get("ok") else 1)
    elif args.command == "install-global":
        from solomon_harness.install_global import describe, install_global
        result = install_global(register_mcp=not args.no_mcp)
        print(describe(result))
    elif args.command == "wiki":
        from solomon_harness.bootstrap import index_codebase, write_code_overview
        from solomon_harness.tools.database_client import DatabaseClient
        try:
            with DatabaseClient(harness_dir=workspace_root) as db:
                index_codebase(workspace_root, db)
                path = write_code_overview(workspace_root, db)
            print(f"Updated code-overview wiki page: {os.path.relpath(path, workspace_root)}")
        except Exception as e:
            print(f"Error: Failed to refresh the wiki: {e}", file=sys.stderr)
            sys.exit(1)
    elif args.command == "skills":
        from solomon_harness.skills import main as skills_main
        sys.exit(skills_main(args.skills_args, start_dir=workspace_root))
    elif args.command == "agents":
        # The generated host-tool subagents live in .claude/agents/ (produced by
        # scripts/generate-integrations.py from the agents/ source of truth).
        agents_dir = os.path.join(workspace_root, ".claude", "agents")
        if args.agents_command == "list":
            if not os.path.isdir(agents_dir):
                print(
                    f"Error: Subagents directory '{agents_dir}' not found. "
                    "Run 'solomon-harness compile' or scripts/generate-integrations.py first.",
                    file=sys.stderr,
                )
                sys.exit(1)
            print("Available subagents:")
            found = False
            import glob
            for filepath in sorted(glob.glob(os.path.join(agents_dir, "*.md"))):
                found = True
                filename = os.path.basename(filepath)
                name = filename[:-3]
                print(f"  {name} - {_subagent_description(filepath)}")
            if not found:
                print(f"No subagents found in '{agents_dir}'.")
        elif args.agents_command == "show":
            if not args.agent_name:
                print("Error: Subcommand 'show' requires an agent name.", file=sys.stderr)
                sys.exit(1)
            agent_file = os.path.join(agents_dir, f"{args.agent_name}.md")
            if not os.path.isfile(agent_file):
                print(f"Error: Subagent '{args.agent_name}' does not exist.", file=sys.stderr)
                sys.exit(1)
            try:
                with open(agent_file, "r", encoding="utf-8") as f:
                    print(f.read())
            except Exception as e:
                print(f"Error reading subagent: {e}", file=sys.stderr)
                sys.exit(1)
        elif args.agents_command == "help":
            print("Usage: solomon-harness agents [list|show <agent_name>]")
            sys.exit(0)
        else:
            print("Usage: solomon-harness agents [list|show <agent_name>]")
            sys.exit(1)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()


