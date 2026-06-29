"""GitHub helpers for the solomon workflows: the Project (v2) board.

These wrap the ``gh`` CLI so the /solomon-* commands can ensure a delivery
board exists and move cards across the lifecycle columns. Every function returns
a result dict and degrades gracefully (it never raises on a gh failure) so a
workflow can report the problem instead of aborting. Requires ``gh`` to be
authenticated with the ``project`` scope.

CLI:
    python -m solomon_harness.github ensure-board [--title T] [--owner O]
    python -m solomon_harness.github set-status --issue N --status "Code Review"
    python -m solomon_harness.github add-issue --issue N
"""

import argparse
import json
import os
import subprocess
import sys
from typing import Any, Dict, List, Optional

# Fallback board title when the repository name cannot be resolved.
DEFAULT_BOARD_TITLE = "solomon"
BOARD_COLUMNS = ["Ideas", "Backlog", "Ready", "In Progress", "Code Review", "QA", "Done"]


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


def repo_name() -> Optional[str]:
    """Return the current repository's short name (without owner), or None."""
    res = _gh(["repo", "view", "--json", "name"], parse_json=True)
    if res["ok"] and res.get("data"):
        return res["data"].get("name")
    return None


def repo_name_with_owner() -> Optional[str]:
    """Return the current repository's owner/name, or None."""
    res = _gh(["repo", "view", "--json", "nameWithOwner"], parse_json=True)
    if res["ok"] and res.get("data"):
        return res["data"].get("nameWithOwner")
    return None


def board_title(repo: Optional[str] = None) -> str:
    """The per-repository board title: the repository name itself.

    Each repository gets one board named after it, so boards never collide and
    ``find_project`` resolves the right one. Falls back to the base name when the
    repository cannot be resolved.
    """
    return (repo or repo_name()) or DEFAULT_BOARD_TITLE


def _link_project_to_repo(owner: str, number, repo_with_owner: Optional[str]) -> Dict[str, Any]:
    """Link a project to the repository so it shows under the repo's Projects."""
    if not number or not repo_with_owner:
        return {"ok": False, "error": "missing project number or repository"}
    return _gh(["project", "link", str(number), "--owner", owner, "--repo", repo_with_owner])


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
    title: Optional[str] = None, owner: Optional[str] = None
) -> Dict[str, Any]:
    """Find or create the per-repository delivery board, linked to the repo."""
    owner = owner or repo_owner()
    if not owner:
        return {"ok": False, "error": "could not resolve the repository owner via gh."}

    title = title or board_title()
    repo_with_owner = repo_name_with_owner()

    existing = find_project(owner, title)
    if existing:
        return {"ok": True, "created": False, "owner": owner, "project": existing}

    res = _gh(
        ["project", "create", "--owner", owner, "--title", title, "--format", "json"],
        parse_json=True,
    )
    if not res["ok"]:
        return {"ok": False, "error": res["error"]}
    project = res.get("data") or {}
    # Configure the lifecycle columns (Status options) on the new board.
    cols = _configure_board_columns(owner, project.get("number"))
    # Link it to the repository so it shows under the repo's Projects tab.
    linked = _link_project_to_repo(owner, project.get("number"), repo_with_owner)
    return {
        "ok": True,
        "created": True,
        "owner": owner,
        "project": project,
        "columns_configured": bool(cols.get("ok")),
        "linked_to_repo": bool(linked.get("ok")),
    }


def _configure_board_columns(owner: str, project_number) -> Dict[str, Any]:
    """Set the board's Status field options to the lifecycle columns.

    Uses the GraphQL updateProjectV2Field mutation, since gh has no command to set
    single-select options. Degrades gracefully (e.g. when the token lacks the
    project scope).
    """
    if not project_number:
        return {"ok": False, "error": "missing project number"}
    field = _status_field(owner, project_number)
    if not field or not field.get("id"):
        return {"ok": False, "error": "could not resolve the Status field"}
    options = ", ".join(
        f'{{name: "{col}", color: GRAY, description: ""}}' for col in BOARD_COLUMNS
    )
    mutation = (
        "mutation { updateProjectV2Field(input: {"
        f'fieldId: "{field["id"]}", singleSelectOptions: [{options}]'
        "}) { projectV2Field { ... on ProjectV2SingleSelectField { id name } } } }"
    )
    return _gh(["api", "graphql", "-f", f"query={mutation}"])


def add_issue_to_board(
    issue_number: int, title: Optional[str] = None, owner: Optional[str] = None
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
    title: Optional[str] = None,
    owner: Optional[str] = None,
) -> Dict[str, Any]:
    """Move an issue's card to a Status column, adding it to the board if needed."""
    if status not in BOARD_COLUMNS:
        return {"ok": False, "error": f"unknown status '{status}'; expected one of {BOARD_COLUMNS}."}

    owner = owner or repo_owner()
    title = title or board_title()
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


STANDARD_LABELS = [
    ("type:feature", "0E8A16", "A new capability or user story"),
    ("type:bug", "D73A4A", "A defect to fix"),
    ("type:idea", "FBCA04", "An idea under discovery"),
    ("type:chore", "C5DEF5", "Maintenance, tooling, or follow-up"),
    ("priority:p0", "B60205", "Critical"),
    ("priority:p1", "D93F0B", "High"),
    ("priority:p2", "0E8A16", "Normal"),
]


def ensure_labels() -> Dict[str, Any]:
    """Create or update the standard issue labels so issue creation can apply them."""
    done = []
    for name, color, desc in STANDARD_LABELS:
        res = _gh(["label", "create", name, "--color", color, "--description", desc, "--force"])
        if res.get("ok"):
            done.append(name)
    return {"ok": len(done) == len(STANDARD_LABELS), "labels": done}


def record_transition(issue_number, column) -> None:
    """Append a board transition (column + timestamp) to the project memory.

    Builds a per-card timeline of when it entered each column, so the start and
    finish dates per stage (and cycle time) can be derived. Best-effort.
    """
    try:
        import datetime
        from solomon_harness.tools.database_client import DatabaseClient

        with DatabaseClient(harness_dir=os.getcwd()) as db:
            key = f"board_history:{issue_number}"
            history = []
            raw = db.get_memory(key)
            if raw:
                try:
                    history = json.loads(raw)
                except Exception:
                    history = []
            history.append({
                "column": column,
                "entered_at": datetime.datetime.now().isoformat(timespec="seconds"),
            })
            db.save_memory(key=key, value=json.dumps(history), category="board_history")
    except Exception:
        pass


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="solomon GitHub board helper")
    sub = parser.add_subparsers(dest="command")

    p_board = sub.add_parser("ensure-board", help="Create the delivery board if missing")
    p_board.add_argument("--title", default=None)
    p_board.add_argument("--owner", default=None)

    sub.add_parser("ensure-labels", help="Create the standard issue labels")

    p_status = sub.add_parser("set-status", help="Move an issue card to a column")
    p_status.add_argument("--issue", type=int, required=True)
    p_status.add_argument("--status", required=True)
    p_status.add_argument("--title", default=None)

    p_add = sub.add_parser("add-issue", help="Add an issue to the board")
    p_add.add_argument("--issue", type=int, required=True)
    p_add.add_argument("--title", default=None)

    args = parser.parse_args(argv)

    if args.command == "ensure-board":
        result = ensure_project_board(title=args.title, owner=args.owner)
        # Ensure the link even when the board already existed (cheap, idempotent).
        if result.get("ok") and not result.get("created"):
            num = (result.get("project") or {}).get("number")
            owner = result.get("owner")
            linked = _link_project_to_repo(str(owner) if owner is not None else "", num, repo_name_with_owner())
            result["linked_to_repo"] = bool(linked.get("ok"))
        if result.get("ok"):
            num = (result.get("project") or {}).get("number")
            print(json.dumps(result, indent=2))
            # GitHub's API has no view mutation, so a fresh board has only a table
            # view. The columns live on the Status field; the layout is manual.
            print(
                "\nColumns are configured on the Status field: "
                + " -> ".join(BOARD_COLUMNS)
                + f"\nGitHub's API cannot create or name views. Open project #{num} and "
                "set its view to Board layout grouped by Status to see the columns."
            )
            return 0
    elif args.command == "ensure-labels":
        result = ensure_labels()
    elif args.command == "set-status":
        result = set_issue_status(args.issue, args.status, title=args.title)
        if result.get("ok"):
            record_transition(args.issue, args.status)
    elif args.command == "add-issue":
        result = add_issue_to_board(args.issue, title=args.title)
    else:
        parser.print_help()
        return 1

    print(json.dumps(result, indent=2))
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    sys.exit(main())
