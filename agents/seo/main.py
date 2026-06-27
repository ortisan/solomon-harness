#!/usr/bin/env python3
"""Main entry point CLI for the agent harness template."""

import argparse
import os
import sys


def get_harness_dir():
    """Returns the absolute path to the harness directory containing this script."""
    return os.path.dirname(os.path.abspath(__file__))


def handle_db_init():
    """Initializes the database client dynamically."""
    try:
        from tools.database_client import DatabaseClient
        db = DatabaseClient()
        print(f"Database initialized successfully at: {db.db_path}")
    except Exception as e:
        print(f"Error: Failed to initialize database: {e}", file=sys.stderr)
        sys.exit(1)


def handle_eval():
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


def handle_run(task):
    """Simulates executing a task using the agent persona and skills.

    Args:
        task: A string description of the task to run.
    """
    import uuid
    import json
    from datetime import datetime, timezone

    harness_dir = get_harness_dir()

    # 1. Load Persona
    persona_path = os.path.join(harness_dir, "persona.md")
    persona_content = ""
    if os.path.isfile(persona_path):
        try:
            with open(persona_path, "r", encoding="utf-8") as f:
                persona_content = f.read()
        except Exception as e:
            print(f"Warning: Failed to read persona file: {e}", file=sys.stderr)
    else:
        print(f"Warning: Persona file not found at {persona_path}", file=sys.stderr)

    # 2. Load Skills
    skills_dir = os.path.join(harness_dir, "skills")
    skills = []
    if os.path.isdir(skills_dir):
        try:
            for item in os.listdir(skills_dir):
                if os.path.isfile(os.path.join(skills_dir, item)):
                    skills.append(item)
        except Exception as e:
            print(f"Warning: Failed to list skills: {e}", file=sys.stderr)

    # 3. Simulate Task Execution
    session_id = str(uuid.uuid4())
    print(f"Starting task session: {session_id}")
    print(f"Task: {task}")
    print(f"Loaded persona length: {len(persona_content)} characters")
    print(f"Loaded skills: {', '.join(skills) if skills else 'None'}")

    # 4. Log Execution to Short-Term Memory
    short_term_dir = os.path.join(harness_dir, "memory", "short_term")
    try:
        os.makedirs(short_term_dir, exist_ok=True)
    except Exception as e:
        print(f"Error: Failed to create short term memory directory: {e}", file=sys.stderr)
        sys.exit(1)

    log_data = {
        "session_id": session_id,
        "task": task,
        "status": "success",
        "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "persona_summary": persona_content[:150] + "..." if persona_content else "",
        "skills_loaded": skills,
        "output": f"Simulated success execution response for task: '{task}'"
    }

    log_path = os.path.join(short_term_dir, f"{session_id}.json")
    try:
        with open(log_path, "w", encoding="utf-8") as f:
            json.dump(log_data, f, indent=2)
        print(f"Task output logged to short term memory: {log_path}")
    except Exception as e:
        print(f"Error: Failed to write task log: {e}", file=sys.stderr)
        sys.exit(1)


def main():
    """Parser setup and command dispatching."""
    parser = argparse.ArgumentParser(description="Solomon Harness Agent Command Line Interface")
    subparsers = parser.add_subparsers(dest="command", help="Available subcommands")

    # db-init parser
    subparsers.add_parser("db-init", help="Initialize the long-term database client and tables")

    # eval parser
    subparsers.add_parser("eval", help="Run the agent evaluations test suite")

    # run parser
    run_parser = subparsers.add_parser("run", help="Simulate running a task")
    run_parser.add_argument("task", type=str, help="The task description to execute")

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
