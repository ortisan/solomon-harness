#!/usr/bin/env python3
"""Main entry point CLI for the agent harness template."""

import argparse
import os
import sys
from typing import Optional, List, Dict, Any


def get_harness_dir() -> str:
    """Returns the absolute path to the harness directory containing this script."""
    return os.path.dirname(os.path.abspath(__file__))


def handle_db_init() -> None:
    """Initializes the database client dynamically."""
    try:
        from tools.database_client import DatabaseClient
        with DatabaseClient() as db:
            print(f"Database initialized successfully at: {db.db_path}")
    except Exception as e:
        print(f"Error: Failed to initialize database: {e}", file=sys.stderr)
        sys.exit(1)


def handle_eval() -> None:
    """Runs the agent_evals.py test suite."""
    import unittest
    harness_dir = get_harness_dir()
    tests_dir = os.path.join(harness_dir, "tests")

    if not os.path.isdir(tests_dir):
        print(f"Error: Tests directory not found at {tests_dir}", file=sys.stderr)
        sys.exit(1)

    print(f"Running agent evaluations from {tests_dir}...")
    loader = unittest.TestLoader()
    suite = loader.discover(start_dir=tests_dir, pattern="agent_evals.py")

    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    if not result.wasSuccessful():
        sys.exit(1)
    else:
        sys.exit(0)


def handle_run(task: Optional[str] = None) -> None:
    """Simulates executing a task or starts the interactive execution loop.

    Args:
        task: Optional task description to run immediately.
    """
    import uuid
    import json
    from tools.database_client import DatabaseClient

    harness_dir = get_harness_dir()

    # Initialize DatabaseClient
    try:
        db_client = DatabaseClient()
    except Exception as e:
        print(f"Error: Failed to initialize database client: {e}", file=sys.stderr)
        sys.exit(1)

    with db_client as db:
        # Welcome message in clean English (no emojis/clichés)
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
        harness_dir = get_harness_dir()
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

            # Simulate running the agent on this task
            print("Executing task simulation...")
            print("Step 1: Loading configuration...")
            print("Step 2: Loading persona profile instructions...")
            print("Step 3: Injecting skills...")

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


def main() -> None:
    """Parser setup and command dispatching."""
    parser = argparse.ArgumentParser(description="Solomon Harness Agent Command Line Interface")
    subparsers = parser.add_subparsers(dest="command", help="Available subcommands")

    # db-init parser
    subparsers.add_parser("db-init", help="Initialize the long-term database client and tables")

    # eval parser
    subparsers.add_parser("eval", help="Run the agent evaluations test suite")

    # run parser
    run_parser = subparsers.add_parser("run", help="Simulate running a task")
    run_parser.add_argument("task", type=str, nargs="?", default=None, help="The task description to execute (optional)")

    args = parser.parse_args()

    # Add harness directory to sys.path so tool/test imports work correctly
    harness_dir = get_harness_dir()
    if harness_dir not in sys.path:
        sys.path.insert(0, harness_dir)

    if args.command == "db-init":
        handle_db_init()
    elif args.command == "eval":
        handle_eval()
    elif args.command == "run":
        handle_run(args.task)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
