#!/usr/bin/env python3
"""Harness command line interface, shared by every agent.

Agents invoke this through a thin entrypoint that passes its own directory as
``harness_dir`` so the loop reads that agent's config, persona and memory store.
"""

import argparse
import os
import sys
from typing import Optional, List, Dict, Any


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


def handle_run(harness_dir: str, task: Optional[str] = None) -> None:
    """Simulates executing a task or starts the interactive execution loop.

    Args:
        harness_dir: The agent directory owning the config, persona and memory.
        task: Optional task description to run immediately.
    """
    import uuid
    import json
    from solomon_harness.tools.database_client import DatabaseClient

    # Initialize DatabaseClient
    try:
        db_client = DatabaseClient(harness_dir=harness_dir)
    except Exception as e:
        print(f"Error: Failed to initialize database client: {e}", file=sys.stderr)
        sys.exit(1)

    with db_client as db:
        # Welcome message in clean English (no emojis/cliches)
        print("Welcome to the Solomon Harness Interactive Agent Loop.")
        print("Database client initialized successfully.")

        # Query where it stopped
        try:
            latest = db.get_latest_activity()
            if latest:
                print("Previous Active State:")
                print(f"  Type: {latest['type']}")
                print(f"  Agent: {latest['agent']}")
                print(f"  Task: {latest['task']}")
                print(f"  Status: {latest['status']}")
                print(f"  Timestamp: {latest['timestamp']}")
            else:
                print("No previous active agent sessions or handoffs found.")
        except Exception as e:
            print(f"Warning: Failed to retrieve previous active state: {e}", file=sys.stderr)

        # Query what is open
        def show_open_issues() -> List[Dict[str, Any]]:
            try:
                open_issues = db.get_open_issues()
                if open_issues:
                    print("Current Open Issues:")
                    for issue in open_issues:
                        print(f"  - [{issue['github_id']}] {issue['title']}")
                    return open_issues
                else:
                    print("No open issues found.")
                    return []
            except Exception as e:
                print(f"Warning: Failed to retrieve open issues: {e}", file=sys.stderr)
                return []

        open_issues = show_open_issues()

        # Load agent name from config if available
        agent_name = "dev_agent"
        config_path = os.path.join(harness_dir, ".agent", "config.json")
        if os.path.isfile(config_path):
            try:
                with open(config_path, "r", encoding="utf-8") as f:
                    config = json.load(f)
                    agent_name = config.get("agent_name", "dev_agent")
            except Exception:
                pass

        current_task = task
        first_iteration = True

        while True:
            # Prompt selection if not passed as CLI argument or not the first iteration
            if not current_task:
                if first_iteration:
                    prompt_text = "Please select one of the open issues to run, or type a title to conceive/create a new issue: "
                else:
                    prompt_text = "Task completed. Please select the next task from the open list, or type a new task name to create it: "

                try:
                    user_input = input(prompt_text).strip()
                except (KeyboardInterrupt, EOFError):
                    print("\nExiting interactive loop.")
                    sys.exit(0)

                if not user_input:
                    continue

                if user_input.lower() in ("exit", "quit"):
                    print("Exiting interactive loop.")
                    sys.exit(0)

                current_task = user_input

            first_iteration = False

            # Match input to open issues
            matched_issue = None
            for issue in open_issues:
                if current_task.lower() == issue["github_id"].lower() or current_task.lower() == issue["title"].lower():
                    matched_issue = issue
                    break

            if matched_issue:
                issue_id = matched_issue["github_id"]
                task_title = matched_issue["title"]
                print(f"Selected existing issue: [{issue_id}] {task_title}")
            else:
                # Create a new issue
                issue_id = f"gh-{str(uuid.uuid4())[:8]}"
                task_title = current_task
                print(f"Conceived new issue: [{issue_id}] {task_title}")
                try:
                    db.log_issue(issue_id, task_title, "task", "open", None)
                except Exception as e:
                    print(f"Warning: Failed to log new issue to database: {e}", file=sys.stderr)

            # This loop records task lifecycle to the project memory; it does not
            # itself run a model. The host tool (Claude Code, Codex, Gemini CLI)
            # provides the execution loop and reads the compiled agent definition.
            print("Recording task lifecycle to project memory...")

            # Update/insert active session state
            session_id = str(uuid.uuid4())
            messages = [{"role": "user", "content": f"Execute task: {task_title}"}]
            try:
                db.save_session(session_id, agent_name, task_title, messages)
                print(f"Active session state saved: {session_id}")
            except Exception as e:
                print(f"Warning: Failed to save active session state: {e}", file=sys.stderr)

            # Simulate execution completion
            print(f"Task execution simulation finished: {task_title}")

            # Prompt for confirmation
            try:
                confirm = input("Confirm task completion? (yes/no): ").strip().lower()
            except (KeyboardInterrupt, EOFError):
                print("\nExiting interactive loop.")
                sys.exit(0)

            if confirm in ("yes", "y"):
                try:
                    # Log decision
                    db.log_decision(
                        title=f"Completed task {issue_id}",
                        rationale=f"Simulated execution of task: {task_title}",
                        outcome="Approved",
                        author=agent_name,
                        branch="main",
                        commit_sha=f"sha-{str(uuid.uuid4())[:7]}"
                    )
                    # Log memory
                    db.save_memory(
                        key=f"memory-{session_id}",
                        value=f"Successfully simulated and approved task: {task_title}",
                        category="agent_loop_refinement"
                    )
                    # Log handoff
                    db.log_handoff(
                        sender=agent_name,
                        recipient="user",
                        contract_type="task_handoff",
                        contract_path="short_term",
                        status="completed"
                    )
                    # Close issue
                    db.log_issue(issue_id, task_title, "task", "closed", None)
                    print("Task closed. Decisions, memory, and handoff successfully logged.")
                except Exception as e:
                    print(f"Error: Failed to record task completion to database: {e}", file=sys.stderr)
            else:
                print("Task completion was not confirmed. Issue status remains open.")

            # Clear current_task to prompt again on next loop iteration
            current_task = None
            # Refresh open issues list for printing
            open_issues = show_open_issues()


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

    subparsers.add_parser("compile", help="Compile agent harnesses from templates")
    subparsers.add_parser("index", help="Index project codebase into the database memory")

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
    elif args.command == "compile":
        from solomon_harness.compiler import compile_harnesses
        compile_harnesses(workspace_root)
    elif args.command == "index":
        from solomon_harness.bootstrap import index_codebase
        from solomon_harness.tools.database_client import DatabaseClient
        try:
            with DatabaseClient(harness_dir=workspace_root) as db:
                index_codebase(workspace_root, db)
        except Exception as e:
            print(f"Error: Codebase indexing failed: {e}", file=sys.stderr)
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


