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
from typing import Any, Dict, List, Optional

from solomon_harness.tools.database_client import is_terminal

_MAX_LIST = 5


def _best_effort_prs(workspace_root: str, timeout: float = 5.0) -> Optional[List[Dict[str, Any]]]:
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


def build_digest(
    resume: Optional[Dict[str, Any]],
    open_issues: List[Dict[str, Any]],
    last_loop_run: Optional[Dict[str, Any]],
    prs: Optional[List[Dict[str, Any]]],
) -> List[str]:
    """Render the digest lines from already-collected facts (pure)."""
    lines: List[str] = []

    if resume:
        lines.append(
            f"Resume: {resume.get('type')} | {resume.get('agent')} | "
            f"{resume.get('task')} | {resume.get('status')}"
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
        lines.append(f"  - [{i.get('github_id')}] {i.get('title')}")
    if len(issues) > _MAX_LIST:
        lines.append(f"  ... and {len(issues) - _MAX_LIST} more")

    if prs is None:
        lines.append("PRs awaiting review: (gh unavailable)")
    else:
        awaiting = _awaiting_review(prs)
        lines.append(f"PRs awaiting review: {len(awaiting)}")
        for p in awaiting[:_MAX_LIST]:
            lines.append(f"  - #{p.get('number')} {p.get('title')}")

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
        pending = {
            "command": f"/solomon-release {pr.get('number')}",
            "description": f"Release approved PR #{pr.get('number')}: {pr.get('title')}"
        }
    elif prs and awaiting:
        pr = awaiting[0]
        pending = {
            "command": f"/solomon-review {pr.get('number')}",
            "description": f"Review open PR #{pr.get('number')}: {pr.get('title')}"
        }
    else:
        # Check in-progress/review/qa issues from memory
        in_flight_issues = [
            i for i in issues
            if i.get("status") in ("in_progress", "In Progress", "code_review", "Code Review", "qa", "QA")
        ]
        if in_flight_issues:
            issue = in_flight_issues[0]
            status = str(issue.get("status")).lower().replace(" ", "_")
            if status == "in_progress":
                cmd = f"/solomon-start {issue.get('github_id')}"
                desc = f"Resume implementation for issue #{issue.get('github_id')}: {issue.get('title')}"
            else:
                cmd = f"/solomon-review {issue.get('github_id')}"
                desc = f"Review/QA issue #{issue.get('github_id')}: {issue.get('title')}"
            pending = {
                "command": cmd,
                "description": desc
            }
        elif resume and resume.get("status") == "active":
            task_str = resume.get("task", "")
            cmd = "/solomon-loop"
            if "start" in str(task_str).lower():
                m = re.search(r'\d+', str(task_str))
                if m:
                    cmd = f"/solomon-start {m.group(0)}"
            pending = {
                "command": cmd,
                "description": f"Resume last activity: {resume.get('agent')} is working on '{task_str}'"
            }
        else:
            # Check Ready issues
            ready_issues = [
                i for i in issues
                if str(i.get("status")).lower() == "ready"
            ]
            if ready_issues:
                issue = ready_issues[0]
                pending = {
                    "command": f"/solomon-start {issue.get('github_id')}",
                    "description": f"Start development on Ready issue #{issue.get('github_id')}: {issue.get('title')}"
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
        # Filter issues to show (e.g. Backlog or Ideas)
        non_pending_issues = [
            i for i in issues
            if str(i.get("status")).lower() in ("backlog", "ideas", "idea", "none", "null", "")
        ]
        if non_pending_issues:
            lines.append("GitHub Open Issues:")
            for i in non_pending_issues[:_MAX_LIST]:
                lines.append(f"  - [{i.get('github_id')}] {i.get('title')} ({i.get('status') or 'Backlog'})")
            if len(non_pending_issues) > _MAX_LIST:
                lines.append(f"  ... and {len(non_pending_issues) - _MAX_LIST} more")

            lines.append("")
            lines.append("Options to proceed:")
            option_idx = 1
            for i in non_pending_issues[:3]:
                status = str(i.get("status")).lower()
                cmd = f"/solomon-refine {i.get('github_id')}" if status == "backlog" else f"/solomon-issue {i.get('github_id')}"
                lines.append(f"  {option_idx}. Refine/Start Issue #{i.get('github_id')}: {cmd}")
                option_idx += 1

            lines.append(f"  {option_idx}. Capture a new product idea: /solomon-idea")
            option_idx += 1
            lines.append(f"  {option_idx}. Create a new feature/story issue: /solomon-issue")
            option_idx += 1
            lines.append(f"  {option_idx}. Create a new bug report: /solomon-bug")
            option_idx += 1
            lines.append(f"  {option_idx}. Other: Free-text entry")
        else:
            lines.append("No open issues found on GitHub.")
            lines.append("")
            lines.append("Options to proceed:")
            lines.append("  1. Capture a new product idea: /solomon-idea")
            lines.append("  2. Create a new feature/story issue: /solomon-issue")
            lines.append("  3. Create a new bug report: /solomon-bug")
            lines.append("  4. Other: Free-text entry")

    return lines


def gather_digest(workspace_root: str, db: Any, fetch_github: bool = True) -> List[str]:
    """Collect facts from memory (and best-effort gh) and render the digest."""

    def _safe(fn, *a, default=None):
        try:
            return fn(*a)
        except Exception:
            return default

    resume = _safe(db.get_latest_activity)
    open_issues = _safe(db.get_open_issues, default=[]) or []
    runs = _safe(db.list_loop_runs, 1, default=[]) or []
    last_loop = runs[0] if runs else None
    prs = _best_effort_prs(workspace_root) if fetch_github else None
    return build_digest(resume, open_issues, last_loop, prs)
