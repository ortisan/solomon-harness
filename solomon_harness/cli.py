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

        try:
            latest = db.get_latest_activity()
            if latest:
                print("\nResume point (latest activity):")
                print(
                    f"  {latest['type']} | {latest['agent']} | {latest['task']} | "
                    f"{latest['status']} | {latest['timestamp']}"
                )
            else:
                print("\nNo previous sessions or handoffs recorded yet.")
        except Exception as e:
            print(f"Warning: could not read latest activity: {e}", file=sys.stderr)

        try:
            open_issues = db.get_open_issues()
            if open_issues:
                print("\nOpen issues:")
                for issue in open_issues:
                    print(f"  - [{issue['github_id']}] {issue['title']}")
            else:
                print("\nNo open issues.")
        except Exception as e:
            print(f"Warning: could not read open issues: {e}", file=sys.stderr)

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

    memory_parser = subparsers.add_parser(
        "memory", help="Memory store maintenance (reconcile the write-through mirror)"
    )
    memory_sub = memory_parser.add_subparsers(dest="memory_command", help="Memory subcommands")
    memory_sub.add_parser(
        "sync", help="Replay pending mirror records to SurrealDB and report the counts"
    )

    ig_parser = subparsers.add_parser(
        "install-global",
        help="Install agents, /solomon commands, the session hook, and the shared memory home into ~/.claude and ~/.solomon-harness",
    )
    ig_parser.add_argument("--no-mcp", action="store_true", help="Skip MCP server registration with the host CLI")

    doctor_parser = subparsers.add_parser("doctor", help="Check (and install) prerequisites")
    doctor_parser.add_argument("--no-install", action="store_true", help="Only report; do not install")

    subparsers.add_parser("healthcheck", help="Report runtime readiness and pending init items (Docker, memory, board, global install)")

    dev_parser = subparsers.add_parser("dev", help="Run a delivery workflow headless (loop, idea, issue, bug, refine, start, review, release)")
    dev_parser.add_argument("stage", type=str, help="The workflow stage")
    dev_parser.add_argument("dev_args", nargs=argparse.REMAINDER, help="Arguments passed to the workflow")

    release_parser = subparsers.add_parser(
        "release",
        help="Plan, prepare, or check a milestone-gated release (plan | prep [version] | check)",
    )
    release_parser.add_argument(
        "release_args",
        nargs=argparse.REMAINDER,
        help="release subcommand: plan (read-only), prep [version] (open the prep PR), check (fail-closed gate)",
    )

    wt_parser = subparsers.add_parser(
        "worktree",
        help="Create or locate the isolated git worktree for a branch (used by /solomon-start)",
    )
    wt_parser.add_argument("branch", type=str, help="Branch name, e.g. feature/<slug>")
    wt_parser.add_argument(
        "--base", type=str, default="main", help="Base ref for a new branch (default: main)"
    )

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
    elif args.command == "dev":
        from solomon_harness.workflows import run_stage
        sys.exit(run_stage(workspace_root, args.stage, args.dev_args))
    elif args.command == "release":
        from solomon_harness.release import run as release_run
        sys.exit(release_run(workspace_root, args.release_args))
    elif args.command == "worktree":
        from solomon_harness.worktree import cli_worktree
        sys.exit(cli_worktree(workspace_root, args.branch, base=args.base))
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
    elif args.command == "memory":
        from solomon_harness.voice import say
        if args.memory_command == "sync":
            from solomon_harness.tools.database_client import DatabaseClient
            with DatabaseClient(harness_dir=workspace_root) as db:
                counts = db.reconcile()
            print(say(
                f"memory sync: {counts['synced']} reconciled, "
                f"{counts['remaining']} pending"
            ))
        else:
            memory_parser.print_help()
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


