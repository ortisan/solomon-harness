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
    python -m solomon_harness.github merge --pr M --issue N
"""

import argparse
import json
import logging
import os
import subprocess
import sys
from typing import TYPE_CHECKING, Any, Dict, List, Optional

if TYPE_CHECKING:
    from solomon_harness.claim import ClaimStore

# The board columns have one canonical definition in the memory adapter (the
# lowest-level module); importing it here keeps github.py and cockpit_read.py from
# re-declaring the names and drifting (ADR-0006). database_client takes no
# dependency on this module, so this import direction carries no cycle.
# normalize_person_key lives in the same adapter (ADR-0012): the person key is
# normalized on write at this capture seam, below every read consumer.
from solomon_harness.tools.database_client import BOARD_COLUMNS, normalize_person_key

logger = logging.getLogger(__name__)

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


def merge_pr_and_close(
    pr_number: int, issue_number: int, claim_store: Optional["ClaimStore"] = None
) -> Dict[str, Any]:
    """Squash-merge an approved PR, then complete the Done transition (#172, ADR-0020).

    This is the single owning call for the merge-to-Done transition: on a
    successful merge it moves the board card to Done and writes the terminal
    status through to memory (the ADR-0006 write-through) in the same call, so
    no separate ``reconcile`` is needed. On a failed merge (not mergeable,
    conflicts) it leaves the board and memory untouched -- no partial state.
    Callers are responsible for the human-approval gate (ADR-0020): this
    function performs the merge unconditionally once called.

    If the merge succeeds but the board move fails (``set_issue_status`` has
    several independent failure modes: an unresolved board item, a missing
    project id, a missing Status field or option), the PR is already merged
    and GitHub has already closed the issue via its ``Closes #`` trailer, so
    the memory write-through still fires -- only the board column needs a
    retry. The result reports ``ok: False`` with ``merged: True`` so a caller
    can tell that apart from nothing having happened at all.

    ``claim_store`` defaults to a ``GitClaimStore`` over the resolved
    workspace root; a caller may inject a different ``ClaimStore``.
    """
    res = _gh(["pr", "merge", str(pr_number), "--squash"])
    if not res.get("ok"):
        return {"ok": False, "error": res.get("error", "gh pr merge failed.")}

    # Release the per-issue claim on merge (best-effort). Reuse the canonical
    # workspace-root resolver rather than hand-rolling a fourth `.git` walk,
    # and log on failure instead of swallowing it silently -- a stale claim
    # ref self-heals via the 30-minute TTL, but a genuine release failure
    # should leave a diagnostic trail like every other best-effort path here.
    try:
        from solomon_harness.skills import get_workspace_root

        store = claim_store
        if store is None:
            from solomon_harness.claim import GitClaimStore

            store = GitClaimStore(get_workspace_root())
        if not store.release(issue_number, force=True):
            logger.warning(
                "issue #%s: claim release on merge did not confirm; the stale "
                "ref self-heals via the claim TTL.",
                issue_number,
            )
    except Exception as exc:  # noqa: BLE001 - best-effort, never break the merge result
        logger.warning(
            "issue #%s: best-effort claim release on merge failed (%s).",
            issue_number,
            exc,
        )

    status_res = set_issue_status(issue_number, "Done")
    record_terminal_status(issue_number)
    if not status_res.get("ok"):
        return {
            "ok": False,
            "error": status_res.get("error", "board move to Done failed after a successful merge."),
            "merged": True,
            "pr": pr_number,
            "issue": issue_number,
        }
    return {"ok": True, "pr": pr_number, "issue": issue_number}


def list_open_issues(
    workspace_root: str, limit: int = 200, claim_store: Optional["ClaimStore"] = None
) -> Dict[str, Any]:
    """List open issues via gh, excluding those actively claimed by another session (ADR-0027).

    The claim-aware read for any scan path that lists open issues directly
    off the board (rather than through ``MemoryService.get_open_issues``,
    which applies the same claim filter over the memory-backed issue list):
    the /solomon-workflow scan step reads ``gh issue list --state open``
    directly, and without this filter a claimed issue could still surface
    there even though `start` would refuse it moments later.

    Best-effort: a gh failure returns ``ok: False`` with the underlying
    error; a claims-fetch failure inside the filter degrades to the
    unfiltered gh result (logged, not silently dropped -- see
    ``claim.filter_unclaimed``).

    ``claim_store`` defaults to a ``GitClaimStore(workspace_root)``; a caller
    may inject a different ``ClaimStore``.
    """
    res = _gh(
        ["issue", "list", "--state", "open", "--limit", str(limit), "--json", "number,title"],
        parse_json=True,
    )
    if not res.get("ok"):
        return {"ok": False, "error": res.get("error", "gh issue list failed.")}

    raw_issues = res.get("data") or []
    numbers: List[int] = [
        item["number"]
        for item in raw_issues
        if isinstance(item, dict) and isinstance(item.get("number"), int)
    ]

    if claim_store is None:
        from solomon_harness.claim import GitClaimStore

        claim_store = GitClaimStore(workspace_root)

    unclaimed_numbers = set(claim_store.filter_unclaimed(numbers))
    issues = [item for item in raw_issues if item.get("number") in unclaimed_numbers]
    return {"ok": True, "issues": issues}


def create_pull_request(draft: bool, base: str, title: str, body: str) -> Dict[str, Any]:
    """Create a pull request using gh CLI."""
    cmd = ["pr", "create", "--base", base, "--title", title, "--body", body]
    if draft:
        cmd.append("--draft")
    res = _gh(cmd)
    if not res.get("ok"):
        return {"ok": False, "error": res.get("error", "gh pr create failed.")}
    return {"ok": True, "url": res.get("stdout", "").strip()}


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


def record_status_write_through(issue_number, column) -> None:
    """Write a board transition's canonical status through to the project memory.

    Fired on every board transition (ADR-0033, amending ADR-0006 decision point 2,
    which gated this on Done alone and so left code_review and qa unreachable —
    a row read in_progress for the whole review/QA phase). It runs at the single
    CLI set-status dispatch seam, so start, review and any future caller are covered
    without each one issuing its own log_issue.

    It read-modify-writes through the unchanged log_issue contract (UPSERT on
    github_id): it reads the current row and, only when that row exists, is not
    already terminal, and would actually change, re-writes it with the column's
    canonical token while preserving the title, type, milestone and assignee.
    log_issue normalizes on write, but the token is normalized here too so the
    no-op comparison below is made against the value that will actually be stored.
    A missing assignee is fetched from GitHub only for a terminal destination;
    intermediate transitions preserve the missing value without an API call.

    The is_terminal short-circuit is load-bearing beyond idempotence: it stops a
    card dragged back from Done to an earlier column from un-delivering the issue
    in memory. GitHub stays the source of truth (ADR-0006 decision point 3).

    Best-effort: it MUST NOT raise — the Done column runs on the merge critical
    path — so any failure is caught and logged as a warning, leaving the row at its
    prior value for reconcile to repair.
    """
    try:
        from solomon_harness.tools.database_client import (
            DatabaseClient,
            is_terminal,
            normalize_status,
        )

        github_id = str(issue_number)
        status = normalize_status(column)
        if status is None:
            # No column means no status to assert; never invent one.
            return
        # Targets whatever backend DatabaseClient resolves (the shared SurrealDB in
        # normal operation; the SQLite fallback only when SurrealDB is unreachable).
        # Unlike reconcile, this single best-effort mirror write does not gate on the
        # backend: it needs no bulk-repair guard, and reconcile against the shared
        # store remains the convergence backstop (ADR-0006).
        with DatabaseClient(harness_dir=os.getcwd()) as db:
            row = db.get_issue(github_id)
            if row is None or is_terminal(row.get("status")):
                return
            if normalize_status(row.get("status")) == status:
                return
            # Preserve an assignee already captured on the row. Only delivery may
            # capture a missing value from GitHub (the person key, ADR-0012), which
            # keeps intermediate status writes free of an added GitHub API call.
            # The capture is best-effort and never raises, so it cannot break merge.
            assignee = row.get("assignee")
            if not assignee and is_terminal(status):
                assignee = capture_issue_assignee(issue_number)
            db.log_issue(
                github_id,
                row.get("title"),
                row.get("type_"),
                status,
                row.get("milestone_id"),
                assignee=assignee,
            )
    except Exception as exc:  # noqa: BLE001 - never break the merge critical path
        # Log the exception type, not str(exc): a backend error message can carry
        # store internals and must not leak into logs (STRIDE: info disclosure).
        logging.warning(
            "status write-through for issue %s failed: %s",
            issue_number,
            type(exc).__name__,
        )


def record_terminal_status(issue_number) -> None:
    """Write the delivered issue's terminal status ("closed") through to memory.

    The Done-shaped alias of :func:`record_status_write_through`, kept as the name
    the merge path calls (ADR-0020) so delivery has one obvious entry point. Same
    best-effort, idempotent guarantees.
    """
    record_status_write_through(issue_number, "Done")


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

    p_merge = sub.add_parser(
        "merge", help="Squash-merge an approved PR and complete the Done transition (#172)"
    )
    p_merge.add_argument("--pr", type=int, required=True)
    p_merge.add_argument("--issue", type=int, required=True)

    p_list = sub.add_parser(
        "list-open-issues",
        help="List open issues, excluding ones actively claimed by another session (ADR-0027)",
    )
    p_list.add_argument("--workspace", default=os.getcwd())
    p_list.add_argument("--limit", type=int, default=200)

    p_pr_create = sub.add_parser("pr-create", help="Create a Pull Request")
    p_pr_create.add_argument("--draft", action="store_true")
    p_pr_create.add_argument("--base", default="main")
    p_pr_create.add_argument("--title", required=True)
    p_pr_create.add_argument("--body", required=True)

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
            # Write every transition's canonical status through to memory, not only
            # Done, so memory-only consumers can tell "coding" from "in review" and
            # code_review/qa are reachable at all (ADR-0033 amends ADR-0006).
            record_status_write_through(args.issue, args.status)
    elif args.command == "add-issue":
        result = add_issue_to_board(args.issue, title=args.title)
    elif args.command == "list-open-issues":
        result = list_open_issues(args.workspace, limit=args.limit)
    elif args.command == "merge":
        result = merge_pr_and_close(args.pr, args.issue)
    elif args.command == "pr-create":
        result = create_pull_request(draft=args.draft, base=args.base, title=args.title, body=args.body)
    else:
        parser.print_help()
        return 1

    print(json.dumps(result, indent=2))
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    sys.exit(main())
