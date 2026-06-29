"""Session-start board digest: one screen of facts, no next-step computed.

Folded into ``solomon-harness run`` (the SessionStart hook), so every session
opens with the whole board in one place instead of stitching memory rows by hand.
It renders only what the harness already owns — the resume point, open issues,
the last loop run, and PRs awaiting review — and ends by pointing at
``/solomon-loop``. The next step is decided there, by the canonical prose ladder,
never computed in Python (which would fork the ladder and drift).
"""

import json
import re
import subprocess
import threading
import sys
from typing import Any, Dict, List, Optional

from solomon_harness.tools.database_client import is_terminal

_MAX_LIST = 5


def _best_effort_prs(workspace_root: str, timeout: float = 2.0) -> Optional[List[Dict[str, Any]]]:
    """Fetch open PRs via gh; return None when gh is unavailable or slow.

    Best-effort by design: the SessionStart hook must never fail or hang on a
    missing/slow ``gh``.
    """
    try:
        proc = subprocess.run(
            ["gh", "pr", "list", "--state", "open", "--limit", "20",
             "--json", "number,title,reviewDecision,isDraft"],
            cwd=workspace_root, capture_output=True, text=True, timeout=timeout, check=False,
        )
        if proc.returncode != 0:
            return None
        return json.loads(proc.stdout or "[]")
    except Exception:
        return None


def _awaiting_review(prs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Open, non-draft PRs that no human has approved yet."""
    out = []
    for p in prs:
        if p.get("isDraft"):
            continue
        if p.get("reviewDecision") in (None, "", "REVIEW_REQUIRED"):
            out.append(p)
    return out


def _safe_id(val: Any) -> Optional[str]:
    """Sanitize the ID to prevent command injection, allowing only alphanumeric, underscores, and dashes."""
    if val is None:
        return None
    s = str(val).strip()
    if re.match(r'^[a-zA-Z0-9_-]+$', s):
        return s
    return None


def _sanitize_title(title: Any) -> str:
    """Sanitize titles to prevent ANSI and terminal control sequence injections."""
    if title is None:
        return ""
    s = str(title)
    # Remove ANSI escape sequences
    s = re.sub(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])', '', s)
    # Filter printable characters only
    s = "".join(ch for ch in s if ch.isprintable())
    return s


def build_digest(
    resume: Optional[Dict[str, Any]],
    open_issues: List[Dict[str, Any]],
    last_loop_run: Optional[Dict[str, Any]],
    prs: Optional[List[Dict[str, Any]]],
    backend: str = "surrealdb",
) -> List[str]:
    """Render the digest lines from already-collected facts (pure).

    ``backend`` is the memory backend the facts were read from. When it is the
    SQLite fallback (SurrealDB unreachable), the digest leads with a banner so a
    stale or seeded local store is never silently presented as the canonical
    board — the failure mode that made a fixture row (``gh-1``) look like the
    real project state at session start.
    """
    lines: List[str] = []

    if backend == "sqlite":
        lines.append(
            "NOTE: memory is on the SQLite fallback (SurrealDB unreachable). "
            "The board below is the local fallback and may be stale."
        )

    if resume:
        lines.append(
            f"Resume: {resume.get('type')} | {resume.get('agent')} | "
            f"{_sanitize_title(resume.get('task'))} | {resume.get('status')}"
        )
    else:
        lines.append("Resume: no prior activity recorded.")

    if last_loop_run:
        r = last_loop_run
        lines.append(
            f"Last loop: /solomon-{r.get('stage')} {r.get('target', '')} -> "
            f"{r.get('status')} ({r.get('created_at', '')})"
        )

    # Defensive terminal filter (ADR-0006): get_open_issues already excludes
    # delivered work, but the digest must never render a terminal row even if
    # handed a stale list, so it drops closed/done/Done here through the shared
    # predicate. A row with no status is not terminal and is kept.
    issues = [i for i in (open_issues or []) if not is_terminal(i.get("status"))]
    lines.append(f"Open issues: {len(issues)}")
    for i in issues[:_MAX_LIST]:
        lines.append(f"  - [{_sanitize_title(i.get('github_id'))}] {_sanitize_title(i.get('title'))}")
    if len(issues) > _MAX_LIST:
        lines.append(f"  ... and {len(issues) - _MAX_LIST} more")

    if prs is None:
        lines.append("PRs awaiting review: (gh unavailable)")
    else:
        awaiting = _awaiting_review(prs)
        lines.append(f"PRs awaiting review: {len(awaiting)}")
        for p in awaiting[:_MAX_LIST]:
            lines.append(f"  - #{p.get('number')} {_sanitize_title(p.get('title'))}")

    # Determine if there is anything pending
    pending = None

    # Check for approved PRs
    approved_prs = []
    if prs:
        for p in prs:
            if p.get("isDraft"):
                continue
            if p.get("reviewDecision") == "APPROVED":
                approved_prs.append(p)

    if approved_prs:
        pr = approved_prs[0]
        pr_num = _safe_id(pr.get('number'))
        if pr_num:
            pending = {
                "command": f"/solomon-release {pr_num}",
                "description": f"Release approved PR #{pr_num}: {_sanitize_title(pr.get('title'))}"
            }
    elif prs and awaiting:
        pr = awaiting[0]
        pr_num = _safe_id(pr.get('number'))
        if pr_num:
            pending = {
                "command": f"/solomon-review {pr_num}",
                "description": f"Review open PR #{pr_num}: {_sanitize_title(pr.get('title'))}"
            }
    else:
        # Check in-progress/review/qa issues from memory
        in_flight_issues = [
            i for i in issues
            if i.get("status") in ("in_progress", "In Progress", "code_review", "Code Review", "qa", "QA")
        ]
        if in_flight_issues:
            issue = in_flight_issues[0]
            issue_id = _safe_id(issue.get('github_id'))
            if issue_id:
                status = str(issue.get("status")).lower().replace(" ", "_")
                if status == "in_progress":
                    cmd = f"/solomon-start {issue_id}"
                    desc = f"Resume implementation for issue #{issue_id}: {_sanitize_title(issue.get('title'))}"
                else:
                    cmd = f"/solomon-review {issue_id}"
                    desc = f"Review/QA issue #{issue_id}: {_sanitize_title(issue.get('title'))}"
                pending = {
                    "command": cmd,
                    "description": desc
                }
        elif resume and resume.get("status") == "active":
            task_str = resume.get("task", "")
            cmd = "/solomon-loop"
            if "start" in str(task_str).lower():
                m = re.search(r'#(\d+)', str(task_str))
                if not m:
                    m = re.search(r'\b(?:issue|pr|task)\s*#?(\d+)', str(task_str), re.IGNORECASE)
                if m:
                    safe_val = _safe_id(m.group(1))
                    if safe_val:
                        cmd = f"/solomon-start {safe_val}"
                else:
                    # Fallback to single digit sequence if only one exists
                    matches = re.findall(r'\d+', str(task_str))
                    if len(matches) == 1:
                        safe_val = _safe_id(matches[0])
                        if safe_val:
                            cmd = f"/solomon-start {safe_val}"
            pending = {
                "command": cmd,
                "description": f"Resume last activity: {resume.get('agent')} is working on '{_sanitize_title(task_str)}'"
            }
        else:
            # Check Ready issues
            ready_issues = [
                i for i in issues
                if str(i.get("status")).lower() == "ready"
            ]
            if ready_issues:
                issue = ready_issues[0]
                issue_id = _safe_id(issue.get('github_id'))
                if issue_id:
                    pending = {
                        "command": f"/solomon-start {issue_id}",
                        "description": f"Start development on Ready issue #{issue_id}: {_sanitize_title(issue.get('title'))}"
                    }

    lines.append("")
    if pending:
        lines.append(f"We found a pending task: {pending['description']}")
        lines.append("Options to proceed:")
        lines.append(f"  1. Single Step (Recommended): Run {pending['command']}")
        lines.append("  2. Autonomous Mode: Advance eligible tasks in sequence")
        lines.append("  3. Other: Free-text entry")
    else:
        lines.append("No pending tasks found in memory.")

    # Filter issues to show (exclude only the one that is currently selected as pending to prevent task elision)
    pending_github_id = None
    if pending and "command" in pending:
        m_id = re.search(r'/solomon-\w+\s+([a-zA-Z0-9_-]+)', pending["command"])
        if m_id:
            pending_github_id = m_id.group(1)

    non_pending_issues = [
        i for i in issues
        if _safe_id(i.get("github_id")) != pending_github_id
    ]

    if non_pending_issues:
        lines.append("GitHub Open Issues:")
        for i in non_pending_issues[:_MAX_LIST]:
            lines.append(f"  - [{_sanitize_title(i.get('github_id'))}] {_sanitize_title(i.get('title'))} ({i.get('status') or 'Backlog'})")
        if len(non_pending_issues) > _MAX_LIST:
            lines.append(f"  ... and {len(non_pending_issues) - _MAX_LIST} more")

        lines.append("")
        lines.append("Options to proceed:")
        option_idx = 1
        for i in non_pending_issues[:3]:
            status = str(i.get("status")).lower()
            issue_id = _safe_id(i.get("github_id"))
            if issue_id:
                if status == "backlog":
                    cmd = f"/solomon-refine {issue_id}"
                elif status in ("ideas", "idea"):
                    cmd = f"/solomon-issue {issue_id}"
                elif status in ("ready", "in_progress", "in progress"):
                    cmd = f"/solomon-start {issue_id}"
                elif status in ("code_review", "code review", "qa"):
                    cmd = f"/solomon-review {issue_id}"
                else:
                    cmd = f"/solomon-issue {issue_id}"
                lines.append(f"  {option_idx}. Refine/Start Issue #{issue_id}: {cmd}")
                option_idx += 1

        lines.append(f"  {option_idx}. Capture a new product idea: /solomon-idea")
        option_idx += 1
        lines.append(f"  {option_idx}. Create a new feature/story issue: /solomon-issue")
        option_idx += 1
        lines.append(f"  {option_idx}. Create a new bug report: /solomon-bug")
        option_idx += 1
        lines.append(f"  {option_idx}. Other: Free-text entry")
    elif not pending:
        lines.append("No open issues found on GitHub.")
        lines.append("")
        lines.append("Options to proceed:")
        lines.append("  1. Capture a new product idea: /solomon-idea")
        lines.append("  2. Create a new feature/story issue: /solomon-issue")
        lines.append("  3. Create a new bug report: /solomon-bug")
        lines.append("  4. Other: Free-text entry")

    return lines


def _run_with_timeout(func, *args, timeout: float = 1.5, default=None):
    """Executes a function in a background thread to prevent local DoS if SurrealDB is unresponsive.

    Since the CLI process prints the digest and exits immediately, daemon threads
    that hang will be terminated automatically by the OS on process exit.
    """
    result = {"val": default, "done": False}

    def worker():
        try:
            result["val"] = func(*args)
            result["done"] = True
        except Exception:
            pass

    t = threading.Thread(target=worker, daemon=True)
    t.start()
    t.join(timeout)
    if t.is_alive():
        sys.stderr.write(f"WARNING: database operation {func.__name__} timed out after {timeout} seconds.\n")
    return result["val"]


def gather_digest(workspace_root: str, db: Any, fetch_github: bool = True) -> List[str]:
    """Collect facts from memory (and best-effort gh) and render the digest with timeout protection."""
    resume = _run_with_timeout(db.get_latest_activity, timeout=0.5, default=None)
    open_issues = _run_with_timeout(db.get_open_issues, timeout=0.5, default=[]) or []
    runs = _run_with_timeout(db.list_loop_runs, 1, timeout=0.5, default=[]) or []
    last_loop = runs[0] if runs else None
    prs = _best_effort_prs(workspace_root) if fetch_github else None
    # Read the backend AFTER the queries: a mid-call ConnectionLost can flip the
    # client to the SQLite fallback, and the banner must reflect where the facts
    # above actually came from.
    backend = getattr(db, "backend", "surrealdb")
    return build_digest(resume, open_issues, last_loop, prs, backend=backend)
