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
import logging
import os
import subprocess
import sys
from typing import Any, Dict, List, Optional

# The board columns have one canonical definition in the memory adapter (the
# lowest-level module); importing it here keeps github.py and cockpit_read.py from
# re-declaring the names and drifting (ADR-0006). database_client takes no
# dependency on this module, so this import direction carries no cycle.
# normalize_person_key lives in the same adapter (ADR-0012): the person key is
# normalized on write at this capture seam, below every read consumer.
from solomon_harness.tools.database_client import BOARD_COLUMNS, normalize_person_key

# Fallback board title when the repository name cannot be resolved.
DEFAULT_BOARD_TITLE = "solomon"

# Wall-clock ceiling for any single gh subprocess. The merge path now routes
# through gh (record_terminal_status -> capture_issue_assignee -> _gh), so an
# unbounded gh that hangs would block the merge; a timeout degrades it to a
# failed call instead (the assignee then reads back as unassigned).
GH_TIMEOUT_SECONDS = 15


def _gh(args: List[str], parse_json: bool = False) -> Dict[str, Any]:
    """Run a gh command and return {'ok', 'data'|'stdout', 'error'}.

    Retries once on a transient failure (a non-zero exit or a timeout): a momentary
    keyring race with a concurrent driver, or a network blip, can fail one call
    while the very next one succeeds (bug #138). The retry, and only the retry,
    heals a credential blip by injecting a freshly resolved token (see
    :func:`_heal_token_env`). A missing gh (FileNotFoundError) is deterministic and
    is not retried; a JSON parse error only follows a successful call and is
    likewise not retried. The retry at most doubles a single call's worst-case time.
    """
    cmd = ["gh", *args]
    # Reached only if both attempts fail transiently; each failing attempt overwrites
    # it with the specific error, so the generic default is a defensive fallback.
    transient_error: Dict[str, Any] = {"ok": False, "error": "gh command failed."}
    for attempt in range(2):
        env = _heal_token_env() if attempt == 1 else None
        try:
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                check=False,
                timeout=GH_TIMEOUT_SECONDS,
                env=env,
            )
        except FileNotFoundError:
            return {"ok": False, "error": "gh CLI not found; install GitHub CLI and authenticate."}
        except subprocess.TimeoutExpired:
            # A fixed message, never str(exc): treat a hung gh as a transient failed
            # call so the caller degrades gracefully instead of blocking or raising.
            transient_error = {"ok": False, "error": f"gh command timed out after {GH_TIMEOUT_SECONDS}s."}
            continue
        if proc.returncode != 0:
            transient_error = {"ok": False, "error": (proc.stderr or proc.stdout).strip()}
            continue
        return _parse_gh_stdout(proc.stdout, parse_json)
    return transient_error


def _parse_gh_stdout(stdout: str, parse_json: bool) -> Dict[str, Any]:
    """Shape a successful gh stdout into the public _gh result dict."""
    out = stdout.strip()
    if not parse_json:
        return {"ok": True, "stdout": out}
    try:
        return {"ok": True, "data": json.loads(out) if out else None}
    except json.JSONDecodeError as exc:
        return {"ok": False, "error": f"could not parse gh JSON output: {exc}"}


def _resolve_gh_token() -> Optional[str]:
    """Best-effort resolve a token via ``gh auth token`` for the heal retry.

    Returns the token, or None when gh cannot resolve one (the retry then runs
    without injection, still a useful network retry). Bounded by the same timeout
    and tolerant of any failure: resolving a token must never break the retry.
    """
    try:
        proc = subprocess.run(
            ["gh", "auth", "token"],
            capture_output=True,
            text=True,
            check=False,
            timeout=GH_TIMEOUT_SECONDS,
        )
    except Exception:  # noqa: BLE001 - best-effort heal; any failure falls back to a plain retry
        return None
    if proc.returncode != 0:
        return None
    return proc.stdout.strip() or None


def _heal_token_env() -> Optional[Dict[str, str]]:
    """The environment for the heal retry, or None to inherit the parent's.

    Only when the env carries neither GITHUB_TOKEN nor GH_TOKEN does it resolve a
    fresh token and return a copy of ``os.environ`` with GH_TOKEN set, healing a
    credential blip. When a token is already present, or none can be resolved, it
    returns None so the retry inherits the existing environment unchanged.
    """
    if os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN"):
        return None
    token = _resolve_gh_token()
    if not token:
        return None
    env = os.environ.copy()
    env["GH_TOKEN"] = token
    return env


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


def _list_title_matches(owner: str, title: str) -> Optional[List[Dict[str, Any]]]:
    """Return the owner's projects whose title matches, or None when the listing
    call itself failed.

    The None/empty distinction is load-bearing: a transient gh failure must read
    as "could not look", not "board absent", or a find-or-create caller mints a
    duplicate board on every blip (bug #76).
    """
    res = _gh(
        ["project", "list", "--owner", owner, "--limit", "100", "--format", "json"],
        parse_json=True,
    )
    if not res["ok"]:
        return None
    projects = (res.get("data") or {}).get("projects", [])
    return [p for p in projects if p.get("title") == title]


def _oldest(matches: List[Dict[str, Any]]) -> Dict[str, Any]:
    """The lowest-numbered (oldest) project: gh lists newest first, so first-match
    would route every transition to a stray duplicate instead of the canonical board."""
    if len(matches) > 1:
        oldest = min(matches, key=lambda p: p.get("number") or 0)
        logging.warning(
            "found %d projects sharing one title; using the oldest (#%s). "
            "Delete the duplicates so card moves cannot land on the wrong board.",
            len(matches),
            oldest.get("number"),
        )
        return oldest
    return matches[0]


def find_project(owner: str, title: str) -> Optional[Dict[str, Any]]:
    """Return the project dict whose title matches, or None."""
    matches = _list_title_matches(owner, title)
    if not matches:
        return None
    return _oldest(matches)


def ensure_project_board(
    title: Optional[str] = None, owner: Optional[str] = None, create: bool = True
) -> Dict[str, Any]:
    """Find the per-repository delivery board, creating it only when asked.

    Only the explicit ``ensure-board`` command keeps ``create=True``; the
    per-issue paths (add-issue, set-status) pass ``create=False`` so a routine
    card move can never mint a board (bug #76).
    """
    owner = owner or repo_owner()
    if not owner:
        return {"ok": False, "error": "could not resolve the repository owner via gh."}

    title = title or board_title()
    repo_with_owner = repo_name_with_owner()

    matches = _list_title_matches(owner, title)
    if matches is None:
        return {
            "ok": False,
            "error": "could not list the owner's projects; refusing to create a board on a failed lookup.",
        }
    if matches:
        return {"ok": True, "created": False, "owner": owner, "project": _oldest(matches)}
    if not create:
        return {
            "ok": False,
            "error": (
                f"board '{title}' not found; run `python -m solomon_harness.github "
                "ensure-board` to create it."
            ),
        }

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
    """Add an issue to the board, returning the created item.

    Never creates the board: a per-issue operation against a missing board is a
    setup error to surface, not a reason to mint a project (bug #76).
    """
    board = ensure_project_board(title=title, owner=owner, create=False)
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

    Writes BOTH representations (expand/contract, ADR-0016): the first-class
    transitions row via ``record_status_transition`` (from_status chained from
    the tail of the existing timeline) and the legacy ``board_history:*`` JSON
    blob, kept for one release so downgraded readers keep working. Timestamps
    are UTC; the previous naive local clock skewed the timeline with the host
    timezone (finding F4).
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
            previous = None
            if history and isinstance(history[-1], dict):
                previous = history[-1].get("column")
            history.append({
                "column": column,
                "entered_at": datetime.datetime.now(datetime.timezone.utc).isoformat(
                    timespec="seconds"
                ),
            })
            db.save_memory(key=key, value=json.dumps(history), category="board_history")
            db.record_status_transition(
                issue_number,
                previous,
                column,
                actor=os.environ.get("GITHUB_ACTOR") or os.environ.get("USER"),
            )
    except Exception:
        pass


def capture_issue_assignee(issue_number) -> Optional[str]:
    """Capture an issue's GitHub assignee as the canonical person key (ADR-0012).

    Reads the assignees at sync/write time (epic #44 forbids a live read at query
    time) via ``gh issue view <n> --json assignees``, defensively extracts the
    first assignee's email and login from the GitHub JSON here (this capture site
    owns the source shape), and maps those two scalars through
    :func:`normalize_person_key`. PII-minimal: only the normalized key is derived;
    name, avatar, and other profile fields are never read out.

    Best-effort: a gh failure, an unparseable shape, or any other error is caught,
    logged by exception type only (never ``str(exc)``, which can leak internals),
    and yields None (the unassigned key). It MUST NOT raise on the merge path.
    """
    try:
        res = _gh(
            ["issue", "view", str(issue_number), "--json", "assignees"],
            parse_json=True,
        )
        if not res.get("ok"):
            return None
        assignees = (res.get("data") or {}).get("assignees") or []
        if not assignees:
            return None
        first = assignees[0]
        email = first.get("email") if isinstance(first, dict) else None
        login = first.get("login") if isinstance(first, dict) else None
        return normalize_person_key(email, login)
    except Exception as exc:  # noqa: BLE001 - best-effort; never break the sync path
        logging.warning(
            "assignee capture for issue %s failed: %s",
            issue_number,
            type(exc).__name__,
        )
        return None


def record_terminal_status(issue_number) -> None:
    """Write the delivered issue's terminal status through to the project memory.

    Fired on the Done board transition (the merge critical path) so the memory row
    converges to GitHub the moment a card is delivered, instead of waiting for
    reconcile. It read-modify-writes through the unchanged 5-arg log_issue (UPSERT
    on github_id): it reads the current row and, only when that row exists and is
    not already terminal, re-writes it as "closed" while preserving the title, type
    and milestone. Best-effort and idempotent (ADR-0006): it MUST NOT raise on the
    merge path, so any failure is caught and logged as a warning, leaving the row
    at its pre-delivery value for reconcile to repair.
    """
    try:
        from solomon_harness.tools.database_client import DatabaseClient, is_terminal

        github_id = str(issue_number)
        # Targets whatever backend DatabaseClient resolves (the shared SurrealDB in
        # normal operation; the SQLite fallback only when SurrealDB is unreachable).
        # Unlike reconcile, this single best-effort mirror write does not gate on the
        # backend: it needs no bulk-repair guard, and reconcile against the shared
        # store remains the convergence backstop (ADR-0006).
        with DatabaseClient(harness_dir=os.getcwd()) as db:
            row = db.get_issue(github_id)
            if row is None or is_terminal(row.get("status")):
                return
            # Preserve an assignee already captured on the row; only when it is
            # absent capture it fresh from GitHub (the person key, ADR-0012). The
            # capture is best-effort and never raises, so it cannot break the merge.
            assignee = row.get("assignee") or capture_issue_assignee(issue_number)
            db.log_issue(
                github_id,
                row.get("title"),
                row.get("type_"),
                "closed",
                row.get("milestone_id"),
                assignee=assignee,
            )
    except Exception as exc:  # noqa: BLE001 - never break the merge critical path
        # Log the exception type, not str(exc): a backend error message can carry
        # store internals and must not leak into logs (STRIDE: info disclosure).
        logging.warning(
            "terminal write-through for issue %s failed: %s",
            issue_number,
            type(exc).__name__,
        )


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
            # On delivery (Done) also write the terminal status through to memory
            # so memory-only consumers converge to GitHub immediately (ADR-0006).
            if args.status == "Done":
                record_terminal_status(args.issue)
    elif args.command == "add-issue":
        result = add_issue_to_board(args.issue, title=args.title)
    else:
        parser.print_help()
        return 1

    print(json.dumps(result, indent=2))
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    sys.exit(main())
