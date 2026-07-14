"""Per-issue claim/lease management.

Guarantees mutual exclusion at the issue level so parallel/concurrent sessions
do not double-pick or collide on the same issue.
"""

import json
import os
import socket
import datetime
import subprocess
from typing import Any, Dict, Optional, Tuple

from solomon_harness.subprocess_env import clean_git_env

CLAIM_TTL_SECONDS = 1800.0  # 30 minutes

def get_current_session_id() -> str:
    """Derive the unique session ID, propagating any host-injected environment variable."""
    host = socket.gethostname()
    pid = os.getpid()
    return os.environ.get(
        "SOLOMON_SESSION_ID", os.environ.get("CLAUDE_SESSION_ID", f"{host}:{pid}")
    )

def parse_claim_commit_message(message: str) -> Optional[Dict[str, Any]]:
    """Parse JSON claim metadata from a git commit message."""
    if not message:
        return None
    try:
        data = json.loads(message.strip())
        if isinstance(data, dict) and "session_id" in data:
            return data
    except (json.JSONDecodeError, TypeError):
        pass
    return None

def is_claim_active(
    claim_data: Dict[str, Any],
    current_session_id: str,
    now: Optional[datetime.datetime] = None,
    has_open_pr: bool = False,
) -> bool:
    """Determine whether the claim is currently active and held by another session.
    
    A claim is active if:
    - It is owned by a different session ID.
    - AND either:
      - The time since heartbeat_at (or acquired_at) is within the 30-minute TTL.
      - OR the issue has an open, in-review pull request (preventing reclaim).
    """
    if not claim_data:
        return False
    
    owner_id = claim_data.get("session_id")
    if owner_id == current_session_id:
        return False  # Same session re-entry is always allowed
        
    if has_open_pr:
        return True  # Block reclaim when there is an open PR
        
    # Check TTL
    if now is None:
        now = datetime.datetime.now(datetime.timezone.utc)
        
    heartbeat_str = claim_data.get("heartbeat_at") or claim_data.get("acquired_at")
    if not heartbeat_str:
        return False
        
    try:
        # Support both offset-naive and offset-aware ISO strings defensively
        heartbeat = datetime.datetime.fromisoformat(heartbeat_str.replace("Z", "+00:00"))
        if heartbeat.tzinfo is None:
            heartbeat = heartbeat.replace(tzinfo=datetime.timezone.utc)
        if now.tzinfo is None:
            now = now.replace(tzinfo=datetime.timezone.utc)
            
        elapsed = (now - heartbeat).total_seconds()
        return elapsed <= CLAIM_TTL_SECONDS
    except ValueError:
        return False

def get_claim_ref(workspace_root: str, issue_number: int) -> Optional[Tuple[str, Dict[str, Any]]]:
    """Fetch the claim ref from origin and return (sha, parsed_metadata) or None."""
    ref = f"refs/claims/issue-{issue_number}"
    remote_ref = f"refs/remotes/origin/claims/issue-{issue_number}"
    env = clean_git_env(workspace_root)
    
    res = subprocess.run(
        ["git", "fetch", "-q", "origin", f"+{ref}:{remote_ref}"],
        cwd=workspace_root,
        capture_output=True,
        text=True,
        env=env,
    )
    if res.returncode != 0:
        return None
        
    sha_res = subprocess.run(
        ["git", "rev-parse", remote_ref],
        cwd=workspace_root,
        capture_output=True,
        text=True,
        env=env,
    )
    if sha_res.returncode != 0:
        return None
    sha_stdout = getattr(sha_res, "stdout", "") or ""
    sha = sha_stdout.strip()
    
    msg_res = subprocess.run(
        ["git", "log", "-1", "--format=%B", remote_ref],
        cwd=workspace_root,
        capture_output=True,
        text=True,
        env=env,
    )
    if msg_res.returncode != 0:
        return None
        
    msg_stdout = getattr(msg_res, "stdout", "") or ""
    claim_dict = parse_claim_commit_message(msg_stdout.strip())
    if claim_dict:
        return sha, claim_dict
    return None

def has_active_pr_or_review(workspace_root: str, issue_number: int) -> bool:
    """Check if the issue is closed or has active review status on the project board."""
    from solomon_harness.github import repo_owner, board_title, find_project, _gh
    
    # Check closed state
    res = _gh(["issue", "view", str(issue_number), "--json", "state"], parse_json=True)
    if res.get("ok") and res.get("data"):
        if res["data"].get("state") == "CLOSED":
            return False
            
    # Check board columns status
    try:
        owner = repo_owner()
        title = board_title()
        if not owner or not title:
            return False
        project = find_project(owner, title)
        if project:
            res = _gh(["project", "item-list", str(project.get("number")), "--owner", owner, "--format", "json"], parse_json=True)
            items = res.get("data", {}).get("items", [])
            for item in items:
                content = item.get("content", {})
                if content.get("number") == issue_number:
                    status = item.get("status")
                    if status in ("Code Review", "QA"):
                        return True
    except Exception:
        pass
    return False

def get_claim(workspace_root: str, issue_number: int) -> Optional[Dict[str, Any]]:
    """Return the parsed claim metadata dict for the issue, or None."""
    ref_info = get_claim_ref(workspace_root, issue_number)
    if ref_info:
        return ref_info[1]
    return None

def claim_issue(workspace_root: str, issue_number: int, current_session_id: Optional[str] = None) -> bool:
    """Atomically claim the issue using git CAS branch lease pushing."""
    if current_session_id is None:
        current_session_id = get_current_session_id()
        
    ref_info = get_claim_ref(workspace_root, issue_number)
    has_pr = has_active_pr_or_review(workspace_root, issue_number)
    
    existing_sha = None
    if ref_info:
        existing_sha = ref_info[0]
        active_claim = ref_info[1]
        if is_claim_active(active_claim, current_session_id, has_open_pr=has_pr):
            return False
            
    now_str = datetime.datetime.now(datetime.timezone.utc).isoformat()
    claim_data = {
        "session_id": current_session_id,
        "acquired_at": now_str,
        "heartbeat_at": now_str,
    }
    
    env = clean_git_env(workspace_root)
    mktree_res = subprocess.run(
        ["git", "mktree"],
        input="",
        cwd=workspace_root,
        capture_output=True,
        text=True,
        env=env,
    )
    if mktree_res.returncode != 0:
        return False
    mktree_stdout = getattr(mktree_res, "stdout", "") or ""
    tree_sha = mktree_stdout.strip()

    commit_res = subprocess.run(
        ["git", "commit-tree", "-m", json.dumps(claim_data), tree_sha],
        cwd=workspace_root,
        capture_output=True,
        text=True,
        env=env,
    )
    if commit_res.returncode != 0:
        return False
    new_sha_stdout = getattr(commit_res, "stdout", "") or ""
    new_sha = new_sha_stdout.strip()
    
    ref = f"refs/claims/issue-{issue_number}"
    if existing_sha:
        push_cmd = ["git", "push", f"--force-with-lease={ref}:{existing_sha}", "origin", f"{new_sha}:{ref}"]
    else:
        push_cmd = ["git", "push", f"--force-with-lease={ref}:", "origin", f"{new_sha}:{ref}"]
        
    push_res = subprocess.run(
        push_cmd,
        cwd=workspace_root,
        capture_output=True,
        text=True,
        env=env,
    )
    if push_res.returncode != 0:
        return False
        
    # Assign issue to harness user on GitHub
    from solomon_harness.github import _gh
    _gh(["issue", "edit", str(issue_number), "--add-assignee", "@me"])
    
    return True

def release_claim(workspace_root: str, issue_number: int, current_session_id: Optional[str] = None, force: bool = False) -> bool:
    """Release the issue claim, removing the git remote ref and assignee."""
    if current_session_id is None:
        current_session_id = get_current_session_id()
        
    ref_info = get_claim_ref(workspace_root, issue_number)
    if not ref_info:
        # Clean up assignee just in case
        from solomon_harness.github import _gh
        _gh(["issue", "edit", str(issue_number), "--remove-assignee", "@me"])
        return True
        
    sha, claim_data = ref_info
    has_pr = has_active_pr_or_review(workspace_root, issue_number)
    if not force and claim_data.get("session_id") != current_session_id and is_claim_active(claim_data, current_session_id, has_open_pr=has_pr):
        return False
        
    ref = f"refs/claims/issue-{issue_number}"
    env = clean_git_env(workspace_root)
    push_res = subprocess.run(
        ["git", "push", f"--force-with-lease={ref}:{sha}", "origin", f":{ref}"],
        cwd=workspace_root,
        capture_output=True,
        text=True,
        env=env,
    )
    if push_res.returncode != 0:
        return False
        
    from solomon_harness.github import _gh
    _gh(["issue", "edit", str(issue_number), "--remove-assignee", "@me"])
    return True

def fetch_all_claims(workspace_root: str) -> Dict[int, Dict[str, Any]]:
    """Fetch all claim references from the remote and return a dict of active claims."""
    env = clean_git_env(workspace_root)
    subprocess.run(
        ["git", "fetch", "-q", "origin", "+refs/claims/*:refs/remotes/origin/claims/*"],
        cwd=workspace_root,
        capture_output=True,
        text=True,
        env=env,
    )
    
    res = subprocess.run(
        ["git", "for-each-ref", "refs/remotes/origin/claims/", "--format=%(refname) %(objectname)"],
        cwd=workspace_root,
        capture_output=True,
        text=True,
        env=env,
    )
    
    claims: Dict[int, Dict[str, Any]] = {}
    if res.returncode != 0 or not res.stdout.strip():
        return claims
        
    for line in res.stdout.strip().splitlines():
        parts = line.strip().split()
        if len(parts) != 2:
            continue
        refname, sha = parts
        basename = refname.split("/")[-1]
        if not basename.startswith("issue-"):
            continue
        try:
            issue_num = int(basename.split("-")[1])
        except (IndexError, ValueError):
            continue
            
        msg_res = subprocess.run(
            ["git", "log", "-1", "--format=%B", refname],
            cwd=workspace_root,
            capture_output=True,
            text=True,
            env=env,
        )
        if msg_res.returncode == 0:
            claim_dict = parse_claim_commit_message(msg_res.stdout.strip())
            if claim_dict:
                claims[issue_num] = claim_dict
    return claims
