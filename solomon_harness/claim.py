"""Per-issue claim/lease management.

Guarantees mutual exclusion at the issue level so parallel/concurrent sessions
do not double-pick or collide on the same issue.
"""

import json
import os
import socket
import datetime
from typing import Any, Dict, Optional

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
