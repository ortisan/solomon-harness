"""GitHub helpers for the solomon-dev workflows: the Project (v2) board.

These wrap the ``gh`` CLI so the /solomon-dev-* commands can ensure a delivery
board exists and move cards across the lifecycle columns. Every function returns
a result dict and degrades gracefully (it never raises on a gh failure) so a
workflow can report the problem instead of aborting. Requires ``gh`` to be
authenticated with the ``project`` scope.

CLI:
    python -m solomon_harness.github ensure-board [--title T] [--owner O]
    python -m solomon_harness.github set-status --issue N --status "In Review"
    python -m solomon_harness.github add-issue --issue N
"""

import argparse
import json
import subprocess
import sys
from typing import Any, Dict, List, Optional

DEFAULT_BOARD_TITLE = "solomon-dev"
BOARD_COLUMNS = ["Ideas", "Backlog", "Ready", "In Progress", "In Review", "Done"]


def _gh(args: List[str], parse_json: bool = False) -> Dict[str, Any]:
    """Run a gh command and return {'ok', 'data'|'stdout', 'error'}."""
    try:
        proc = subprocess.run(["gh", *args], capture_output=True, text=True, check=False)
    except FileNotFoundError:
        return {"ok": False, "error": "gh CLI not found; install GitHub CLI and authenticate."}
    if proc.returncode != 0:
        return {"ok": False, "error": (proc.stderr or proc.stdout).strip()}
    out = proc.stdout.strip()
    if parse_json:
        try:
            return {"ok": True, "data": json.loads(out) if out else None}
        except json.JSONDecodeError as exc:
            return {"ok": False, "error": f"could not parse gh JSON output: {exc}"}
    return {"ok": True, "stdout": out}


def repo_owner() -> Optional[str]:
    """Return the owner login of the current repo, or None."""
    res = _gh(["repo", "view", "--json", "owner"], parse_json=True)
    if res["ok"] and res.get("data"):
        return res["data"].get("owner", {}).get("login")
    return None


def find_project(owner: str, title: str) -> Optional[Dict[str, Any]]:
    """Return the project dict whose title matches, or None."""
    res = _gh(["project", "list", "--owner", owner, "--format", "json"], parse_json=True)
    if not res["ok"] or not res.get("data"):
        return None
    for project in res["data"].get("projects", []):
        if project.get("title") == title:
            return project
    return None


def ensure_project_board(
    title: str = DEFAULT_BOARD_TITLE, owner: Optional[str] = None
) -> Dict[str, Any]:
    """Find or create the delivery board for the repo owner."""
    owner = owner or repo_owner()
    if not owner:
        return {"ok": False, "error": "could not resolve the repository owner via gh."}

    existing = find_project(owner, title)
    if existing:
        return {"ok": True, "created": False, "owner": owner, "project": existing}

    res = _gh(
        ["project", "create", "--owner", owner, "--title", title, "--format", "json"],
        parse_json=True,
    )
    if not res["ok"]:
        return {"ok": False, "error": res["error"]}
    return {"ok": True, "created": True, "owner": owner, "project": res.get("data")}


def add_issue_to_board(
    issue_number: int, title: str = DEFAULT_BOARD_TITLE, owner: Optional[str] = None
) -> Dict[str, Any]:
    """Add an issue to the board, returning the created item."""
    board = ensure_project_board(title=title, owner=owner)
    if not board["ok"]:
        return board
    owner = board["owner"]
    number = board["project"].get("number")

    url = _gh(
        ["issue", "view", str(issue_number), "--json", "url"], parse_json=True
    )
    if not url["ok"] or not url.get("data"):
        return {"ok": False, "error": f"could not resolve URL for issue #{issue_number}."}
    issue_url = url["data"]["url"]

    res = _gh(
        ["project", "item-add", str(number), "--owner", owner, "--url", issue_url, "--format", "json"],
        parse_json=True,
    )
    if not res["ok"]:
        return {"ok": False, "error": res["error"]}
    return {"ok": True, "owner": owner, "project_number": number, "item": res.get("data")}


def _status_field(owner: str, project_number: int) -> Optional[Dict[str, Any]]:
    """Return the single-select 'Status' field with its options, or None."""
    res = _gh(
        ["project", "field-list", str(project_number), "--owner", owner, "--format", "json"],
        parse_json=True,
    )
    if not res["ok"] or not res.get("data"):
        return None
    for field in res["data"].get("fields", []):
        if field.get("name") == "Status" and field.get("options"):
            return field
    return None


def set_issue_status(
    issue_number: int,
    status: str,
    title: str = DEFAULT_BOARD_TITLE,
    owner: Optional[str] = None,
) -> Dict[str, Any]:
    """Move an issue's card to a Status column, adding it to the board if needed."""
    if status not in BOARD_COLUMNS:
        return {"ok": False, "error": f"unknown status '{status}'; expected one of {BOARD_COLUMNS}."}

    added = add_issue_to_board(issue_number, title=title, owner=owner)
    if not added["ok"]:
        return added
    owner = added["owner"]
    project_number = added["project_number"]
    item_id = (added.get("item") or {}).get("id")
    if not item_id:
        return {"ok": False, "error": "could not resolve the board item id for the issue."}

    project = find_project(owner, title) or {}
    project_id = project.get("id")
    field = _status_field(owner, project_number)
    if not project_id or not field:
        return {"ok": False, "error": "could not resolve the project id or Status field."}

    option = next((o for o in field["options"] if o.get("name") == status), None)
    if not option:
        return {"ok": False, "error": f"board has no '{status}' Status option."}

    res = _gh([
        "project", "item-edit",
        "--id", item_id,
        "--project-id", project_id,
        "--field-id", field["id"],
        "--single-select-option-id", option["id"],
    ])
    if not res["ok"]:
        return {"ok": False, "error": res["error"]}
    return {"ok": True, "issue": issue_number, "status": status}


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="solomon-dev GitHub board helper")
    sub = parser.add_subparsers(dest="command")

    p_board = sub.add_parser("ensure-board", help="Create the delivery board if missing")
    p_board.add_argument("--title", default=DEFAULT_BOARD_TITLE)
    p_board.add_argument("--owner", default=None)

    p_status = sub.add_parser("set-status", help="Move an issue card to a column")
    p_status.add_argument("--issue", type=int, required=True)
    p_status.add_argument("--status", required=True)
    p_status.add_argument("--title", default=DEFAULT_BOARD_TITLE)

    p_add = sub.add_parser("add-issue", help="Add an issue to the board")
    p_add.add_argument("--issue", type=int, required=True)
    p_add.add_argument("--title", default=DEFAULT_BOARD_TITLE)

    args = parser.parse_args(argv)

    if args.command == "ensure-board":
        result = ensure_project_board(title=args.title, owner=args.owner)
    elif args.command == "set-status":
        result = set_issue_status(args.issue, args.status, title=args.title)
    elif args.command == "add-issue":
        result = add_issue_to_board(args.issue, title=args.title)
    else:
        parser.print_help()
        return 1

    print(json.dumps(result, indent=2))
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    sys.exit(main())
