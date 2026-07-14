"""Per-issue claim/lease management.

Guarantees mutual exclusion at the issue level so parallel/concurrent sessions
do not double-pick or collide on the same issue.

Storage and read path (ADR-0027): the git ref ``refs/claims/issue-N`` (CAS via
``git push --force-with-lease``) is the sole AUTHORITATIVE source of truth for
the mutual-exclusion decision -- it is the only substrate visible across
worktrees and under the SQLite memory fallback. Every function in this module
that decides whether a claim can be taken, stolen, or released
(``claim_issue``, ``release_claim``, ``is_claim_active``) consults only the
git ref. The project memory (SurrealDB/SQLite via ``DatabaseClient``) gets a
BEST-EFFORT MIRROR only (``_mirror_claim`` / ``_clear_claim_mirror`` /
``get_claim_holder``): it exists so the current holder is queryable through
the memory MCP tools and the session-start digest without a live git fetch,
and a mirror-layer failure never blocks, fails, or gates a claim decision.
"""

import json
import logging
import os
import socket
import datetime
import subprocess
import uuid
from typing import Any, Dict, Iterable, List, Optional, Tuple

from solomon_harness.subprocess_env import clean_git_env

logger = logging.getLogger(__name__)

CLAIM_TTL_SECONDS = 1800.0  # 30 minutes

# How often the heartbeat thread (spawned by workflows.run_stage after a
# successful `start` claim) re-touches heartbeat_at on the claim ref, keeping
# a stage that runs longer than CLAIM_TTL_SECONDS from becoming reclaimable
# mid-implementation (the #24 double-pick). Overridable for tests.
CLAIM_HEARTBEAT_INTERVAL_SECONDS = float(
    os.environ.get("SOLOMON_CLAIM_HEARTBEAT_INTERVAL_SECONDS", "600")
)

# Cache for the no-env default session id (host:pid:entropy), computed once
# per process so repeated calls within one process stay stable -- see
# get_current_session_id.
_SESSION_ID_CACHE: Optional[str] = None

# Bounded timeout for every git subprocess this module spawns. A stalled origin
# (credential prompt, DNS hang, dead network) must never hang the `start` stage
# -- and, worse, the repo-wide single-driver lock the stage holds while the
# claim gate runs (the ADR-0021-class "loop hung indefinitely holding the lock"
# incident). A TimeoutExpired is caught and reported as a failed call so every
# caller degrades through its existing returncode check instead of raising
# through run_stage's claim gate (which runs before the try/finally and would
# leak the lock).
GIT_SUBPROCESS_TIMEOUT_SECONDS = 15.0


def _run_git(
    args: List[str],
    workspace_root: str,
    env: Dict[str, str],
    input_text: Optional[str] = None,
) -> "subprocess.CompletedProcess[str]":
    """Run a git subprocess with a bounded timeout; a timeout degrades to a failed call (rc=1)."""
    try:
        return subprocess.run(
            args,
            cwd=workspace_root,
            capture_output=True,
            text=True,
            env=env,
            input=input_text,
            timeout=GIT_SUBPROCESS_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired:
        logger.warning(
            "git %s timed out after %ss in %s; treating as a failed call so the "
            "stage and the single-driver lock never hang.",
            (args[1] if len(args) > 1 else "?"),
            GIT_SUBPROCESS_TIMEOUT_SECONDS,
            workspace_root,
        )
        return subprocess.CompletedProcess(args, 1, stdout="", stderr="git subprocess timed out")


def get_current_session_id() -> str:
    """Derive the unique session ID, propagating any host-injected environment variable.

    SOLOMON_SESSION_ID (or CLAUDE_SESSION_ID) must be unique per logical
    session: it is what lets the SAME session re-enter its own claim across
    separate process invocations (a host tool that shells out per stage,
    each a new process). A host that injects a fixed value shared by two
    independent logical sessions will make them collide as "the same
    session" for re-entry purposes, defeating mutual exclusion -- so any
    caller setting this variable must mint a fresh value per session, not a
    constant.

    When neither is set, the default is ``host:pid:entropy`` -- a short
    random suffix appended so two no-env processes on the same host never
    collide even after pid reuse. Computed once and cached for the lifetime
    of the process, so repeated calls (this function is called many times
    per stage) return the same id and re-entry within one process is stable.
    """
    global _SESSION_ID_CACHE
    env_id = os.environ.get("SOLOMON_SESSION_ID", os.environ.get("CLAUDE_SESSION_ID"))
    if env_id:
        return env_id
    if _SESSION_ID_CACHE is None:
        host = socket.gethostname()
        pid = os.getpid()
        _SESSION_ID_CACHE = f"{host}:{pid}:{uuid.uuid4().hex[:8]}"
    return _SESSION_ID_CACHE

def parse_claim_commit_message(message: str) -> Optional[Dict[str, Any]]:
    """Parse JSON claim metadata from a git commit message.

    Type-validates the fields a hostile or corrupted ref could poison (M10):
    ``session_id`` must be a string, and ``acquired_at``/``heartbeat_at``, if
    present, must be strings too. A malformed ref (e.g. a non-string
    heartbeat_at) is rejected here rather than left to crash a later
    ``.replace()`` call in ``is_claim_active`` uncaught in the `start` gate.
    """
    if not message:
        return None
    try:
        data = json.loads(message.strip())
    except (json.JSONDecodeError, TypeError):
        return None
    if not isinstance(data, dict) or "session_id" not in data:
        return None
    if not isinstance(data.get("session_id"), str):
        return None
    for field in ("acquired_at", "heartbeat_at"):
        value = data.get(field)
        if value is not None and not isinstance(value, str):
            return None
    return data

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
        if elapsed < 0:
            # A future heartbeat (clock skew, or a crafted ref) must never
            # read as fresh forever (M9): treat as malformed/expired rather
            # than active via the TTL path.
            return False
        return elapsed <= CLAIM_TTL_SECONDS
    except (ValueError, TypeError, AttributeError):
        # Broadened defensively (M10) alongside parse_claim_commit_message's
        # type validation: a hostile/corrupted claim dict (e.g. a non-string
        # heartbeat_at that slipped past parsing) must degrade to "not
        # active" here too, never crash the `start` gate.
        return False

def get_claim_ref(workspace_root: str, issue_number: int) -> Optional[Tuple[str, Optional[Dict[str, Any]]]]:
    """Fetch the claim ref from origin and return its state.

    Returns ``None`` when no claim ref exists or it cannot be fetched,
    ``(sha, claim_dict)`` for a well-formed claim, and ``(sha, None)`` when
    the ref EXISTS but its content is malformed. The malformed case must stay
    distinguishable from "no ref": collapsing the two made a poisoned ref
    permanently unclaimable (the CAS then used the ref-must-not-exist lease
    and always lost) while ``claim release`` reported success without ever
    deleting the real ref. Callers treat a malformed ref as recoverable --
    reclaimable and deletable via CAS against its sha.
    """
    ref = f"refs/claims/issue-{issue_number}"
    remote_ref = f"refs/remotes/origin/claims/issue-{issue_number}"
    env = clean_git_env(workspace_root)

    res = _run_git(["git", "fetch", "-q", "origin", f"+{ref}:{remote_ref}"], workspace_root, env)
    if res.returncode != 0:
        return None

    sha_res = _run_git(["git", "rev-parse", remote_ref], workspace_root, env)
    if sha_res.returncode != 0:
        return None
    sha_stdout = getattr(sha_res, "stdout", "") or ""
    sha = sha_stdout.strip()

    msg_res = _run_git(["git", "log", "-1", "--format=%B", remote_ref], workspace_root, env)
    if msg_res.returncode != 0:
        return None

    msg_stdout = getattr(msg_res, "stdout", "") or ""
    claim_dict = parse_claim_commit_message(msg_stdout.strip())
    if claim_dict is None:
        logger.warning(
            "issue #%s: claim ref exists but its content is malformed; "
            "treating it as a recoverable (reclaimable, deletable) claim.",
            issue_number,
        )
        return sha, None
    return sha, claim_dict

def _pr_liveness(
    workspace_root: str,
    issue_number: int,
    board_items: Optional[List[Dict[str, Any]]] = None,
) -> Tuple[bool, bool]:
    """Determine whether the issue is PR/review-protected against reclaim.

    Returns ``(protected, uncertain)``:

    - ``protected`` is True only when confirmed: the issue's board card sits
      in Code Review or QA. This is the same signal ``has_active_pr_or_review``
      has always reported.
    - ``uncertain`` is True only when a ``gh`` call needed to answer the
      question itself failed (``ok: False`` or an unexpected error) --
      distinct from a call that succeeded and simply found nothing (a closed
      issue, no board, no matching card). A gh failure must never be
      silently read as "not protected": ``claim_issue``'s reclaim path and
      ``release_claim``'s non-force path fail closed on ``uncertain`` (B5b)
      so a transient gh outage can never let a live claim be stolen or
      casually released.

    ``board_items`` lets a caller that checks many issues fetch the board
    once via ``fetch_board_items`` and share it; ``None`` fetches here.
    """
    from solomon_harness.github import _gh

    issue_res = _gh(["issue", "view", str(issue_number), "--json", "state"], parse_json=True)
    if not issue_res.get("ok"):
        logger.warning(
            "issue #%s: could not read GitHub issue state (%s); PR/review "
            "liveness is uncertain.",
            issue_number,
            issue_res.get("error"),
        )
        return False, True
    data = issue_res.get("data")
    if data and data.get("state") == "CLOSED":
        return False, False

    if board_items is None:
        board_items = fetch_board_items(workspace_root)
    if board_items is None:
        return False, True
    for item in board_items:
        content = item.get("content", {})
        if content.get("number") == issue_number:
            status = item.get("status")
            if status in ("Code Review", "QA"):
                return True, False
    return False, False


def fetch_board_items(workspace_root: str) -> Optional[List[Dict[str, Any]]]:
    """Fetch the project board item list once, for reuse across liveness checks.

    Returns the item list ([] when there is verifiably no board to consult),
    or ``None`` when a ``gh`` call needed to answer failed -- the uncertain
    state, which safety callers treat fail-closed. Exists so a scan over N
    claimed issues costs one board fetch, not N (the board list was
    re-fetched per issue before, an N+1 on the session-start hot path).
    """
    from solomon_harness.github import repo_owner, board_title, find_project, _gh

    try:
        owner = repo_owner()
        title = board_title()
        if not owner or not title:
            return []
        project = find_project(owner, title)
        if not project:
            return []
        board_res = _gh(
            ["project", "item-list", str(project.get("number")), "--owner", owner, "--format", "json"],
            parse_json=True,
        )
        if not board_res.get("ok"):
            logger.warning(
                "could not list board items (%s); PR/review liveness is uncertain.",
                board_res.get("error"),
            )
            return None
        return (board_res.get("data") or {}).get("items", [])
    except Exception as exc:  # noqa: BLE001 - degrade, but never silently
        logger.warning("board fetch for liveness degraded (%s); treating as uncertain.", exc)
        return None


def has_active_pr_or_review(
    workspace_root: str,
    issue_number: int,
    board_items: Optional[List[Dict[str, Any]]] = None,
) -> bool:
    """Check if the issue is closed or has active review status on the project board.

    Returns True only when confirmed protected. A ``gh`` failure degrades to
    False here -- the pre-existing, advisory-only contract this bool has
    always had for its read-only callers (the claim-gate status message in
    ``run_stage``, the best-effort issue filters). The RECLAIM and non-force
    RELEASE decisions do not rely on this bool alone: see ``_pr_liveness``,
    which they call directly to get the ``uncertain`` flag too.
    ``board_items`` lets a caller checking many issues fetch the board once
    via ``fetch_board_items`` and share it.
    """
    protected, _uncertain = _pr_liveness(workspace_root, issue_number, board_items=board_items)
    return protected

def get_claim(workspace_root: str, issue_number: int) -> Optional[Dict[str, Any]]:
    """Return the parsed claim metadata dict for the issue, or None."""
    ref_info = get_claim_ref(workspace_root, issue_number)
    if ref_info:
        return ref_info[1]
    return None


def _mktree_commit(workspace_root: str, claim_data: Dict[str, Any], env: Dict[str, str]) -> Optional[str]:
    """Build an empty-tree commit carrying ``claim_data`` as its message; return its sha, or None on failure."""
    mktree_res = _run_git(["git", "mktree"], workspace_root, env, input_text="")
    if mktree_res.returncode != 0:
        return None
    tree_sha = (getattr(mktree_res, "stdout", "") or "").strip()

    commit_res = _run_git(["git", "commit-tree", "-m", json.dumps(claim_data), tree_sha], workspace_root, env)
    if commit_res.returncode != 0:
        return None
    return (getattr(commit_res, "stdout", "") or "").strip()


def _audit_claim_event(workspace_root: str, issue_number: int, event: str, session_id: str, detail: str = "") -> None:
    """Durable, best-effort audit of a claim lifecycle event.

    The mirror key is last-write-wins state; this appends one row per event
    (granted, reclaimed, denied, released, force-released, denied-release,
    heartbeat-lost, malformed-recovered) so a takeover or refusal can be
    reconstructed after the fact -- the forensic trail the concurrent-driver
    incidents needed. Also emitted at INFO level so the process log carries
    the same trail. Never raises and never gates a claim decision.
    """
    logger.info("claim %s: issue #%s session %s %s", event, issue_number, session_id, detail)
    try:
        from solomon_harness.tools.database_client import DatabaseClient

        stamp = datetime.datetime.now(datetime.timezone.utc).isoformat()
        with DatabaseClient(harness_dir=workspace_root) as db:
            db.save_memory(
                key=f"claim-event:issue-{issue_number}:{stamp}",
                value=json.dumps(
                    {
                        "issue": issue_number,
                        "event": event,
                        "session_id": session_id,
                        "detail": detail,
                        "at": stamp,
                    }
                ),
                category="claim_event",
            )
    except Exception as exc:  # noqa: BLE001 - audit is best-effort, never gates a claim
        logger.warning("issue #%s: claim audit write failed (%s).", issue_number, exc)


def _mirror_claim(workspace_root: str, issue_number: int, claim_data: Dict[str, Any]) -> None:
    """Best-effort write-through of the claim into the project memory (ADR-0027).

    The git ref on ``refs/claims/*`` stays the sole authoritative source of
    truth for the mutual-exclusion decision -- claim_issue/release_claim
    never consult this mirror to decide anything. It exists only so the
    current holder is queryable via the memory MCP tools and the
    session-start digest without a live git fetch (see get_claim_holder).
    Never raises: any failure (SurrealDB unreachable, SQLite locked, an
    unexpected schema) is logged and swallowed so a memory-layer outage can
    never affect a claim's boolean result.
    """
    try:
        from solomon_harness.tools.database_client import DatabaseClient

        with DatabaseClient(harness_dir=workspace_root) as db:
            db.save_memory(
                key=f"claim:issue-{issue_number}",
                value=json.dumps({"issue": issue_number, **claim_data}),
                category="claim",
            )
    except Exception as exc:  # noqa: BLE001 - best-effort mirror, never break the claim path
        logger.warning(
            "issue #%s: best-effort claim mirror write failed (%s); the git "
            "claim ref remains authoritative.",
            issue_number,
            exc,
        )


def _clear_claim_mirror(workspace_root: str, issue_number: int) -> None:
    """Best-effort clear of the claim mirror on release. Never raises."""
    try:
        from solomon_harness.tools.database_client import DatabaseClient

        with DatabaseClient(harness_dir=workspace_root) as db:
            db.save_memory(key=f"claim:issue-{issue_number}", value="", category="claim")
    except Exception as exc:  # noqa: BLE001 - best-effort mirror, never break the release path
        logger.warning(
            "issue #%s: best-effort claim mirror clear failed (%s).",
            issue_number,
            exc,
        )


def get_claim_holder(workspace_root: str, issue_number: int) -> Optional[Dict[str, Any]]:
    """Best-effort read of the claim holder from the memory mirror (not git).

    For the digest / get_latest_activity consumers that want to display the
    current holder without a live git fetch. This is the best-effort mirror,
    NOT the authoritative source: claim_issue/release_claim/is_claim_active
    always decide against the git ref, never against this. Returns None when
    unclaimed, unreadable, or the memory layer is degraded.
    """
    try:
        from solomon_harness.tools.database_client import DatabaseClient

        with DatabaseClient(harness_dir=workspace_root) as db:
            raw = db.get_memory(f"claim:issue-{issue_number}")
    except Exception as exc:  # noqa: BLE001 - best-effort read, degrade quietly
        logger.warning(
            "issue #%s: could not read the claim mirror (%s).",
            issue_number,
            exc,
        )
        return None
    if not raw:
        return None
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return None


def claim_issue(workspace_root: str, issue_number: int, current_session_id: Optional[str] = None) -> bool:
    """Atomically claim the issue using git CAS branch lease pushing."""
    if current_session_id is None:
        current_session_id = get_current_session_id()

    ref_info = get_claim_ref(workspace_root, issue_number)

    existing_sha = None
    reclaiming_malformed = False
    if ref_info:
        existing_sha = ref_info[0]
        active_claim = ref_info[1]
        if active_claim is None:
            # A malformed ref carries no owner to respect and no heartbeat to
            # honor: reclaim it via CAS against its sha (the lease still makes
            # exactly one concurrent reclaimer win). Leaving it in place made
            # the issue permanently unclaimable.
            reclaiming_malformed = True
        else:
            protected, uncertain = _pr_liveness(workspace_root, issue_number)
            if uncertain and active_claim.get("session_id") != current_session_id:
                # Fail closed (B5b): a transient gh error must never let a live
                # claim be reclaimed. Only an EXISTING claim is protected this
                # way -- a fresh claim on a verifiably-unclaimed issue (ref_info
                # is None) never reaches this branch and still proceeds, and
                # same-session re-entry is unaffected (it never needed liveness).
                logger.warning(
                    "issue #%s: PR/review liveness could not be determined; "
                    "refusing to reclaim the existing claim held by session %s.",
                    issue_number,
                    active_claim.get("session_id"),
                )
                _audit_claim_event(
                    workspace_root, issue_number, "denied", current_session_id,
                    detail=f"liveness uncertain; holder {active_claim.get('session_id')}",
                )
                return False
            if is_claim_active(active_claim, current_session_id, has_open_pr=protected):
                _audit_claim_event(
                    workspace_root, issue_number, "denied", current_session_id,
                    detail=f"active claim held by {active_claim.get('session_id')}",
                )
                return False

    now_str = datetime.datetime.now(datetime.timezone.utc).isoformat()
    claim_data = {
        "session_id": current_session_id,
        "acquired_at": now_str,
        "heartbeat_at": now_str,
    }

    env = clean_git_env(workspace_root)
    new_sha = _mktree_commit(workspace_root, claim_data, env)
    if not new_sha:
        return False

    ref = f"refs/claims/issue-{issue_number}"
    if existing_sha:
        push_cmd = ["git", "push", f"--force-with-lease={ref}:{existing_sha}", "origin", f"{new_sha}:{ref}"]
    else:
        push_cmd = ["git", "push", f"--force-with-lease={ref}:", "origin", f"{new_sha}:{ref}"]

    push_res = _run_git(push_cmd, workspace_root, env)
    if push_res.returncode != 0:
        return False

    _mirror_claim(workspace_root, issue_number, claim_data)
    if reclaiming_malformed:
        event, detail = "malformed-recovered", "reclaimed over a malformed claim ref"
    elif existing_sha:
        event, detail = "reclaimed", "took over a stale claim"
    else:
        event, detail = "granted", ""
    _audit_claim_event(workspace_root, issue_number, event, current_session_id, detail=detail)

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
        # Clean up assignee and any stale mirror entry just in case.
        _clear_claim_mirror(workspace_root, issue_number)
        from solomon_harness.github import _gh
        _gh(["issue", "edit", str(issue_number), "--remove-assignee", "@me"])
        return True

    sha, claim_data = ref_info
    if claim_data is None:
        # Malformed ref: there is no owner to protect, but the release must
        # actually DELETE the ref -- reporting success while the poisoned ref
        # survives was the false-recovery bug. force is irrelevant here.
        pass
    elif not force and claim_data.get("session_id") != current_session_id:
        protected, uncertain = _pr_liveness(workspace_root, issue_number)
        if uncertain:
            # Fail closed, mirroring claim_issue's reclaim path: when the
            # PR/review liveness of a foreign claim cannot be determined, a
            # non-force release must refuse rather than assume unprotected --
            # otherwise a transient gh outage lets the release door defeat the
            # same invariant the reclaim door guards (B5b).
            logger.warning(
                "issue #%s: PR/review liveness could not be determined; "
                "refusing to release the claim held by session %s without "
                "--force.",
                issue_number,
                claim_data.get("session_id"),
            )
            _audit_claim_event(
                workspace_root, issue_number, "denied-release", current_session_id,
                detail=f"liveness uncertain; holder {claim_data.get('session_id')}",
            )
            return False
        if is_claim_active(claim_data, current_session_id, has_open_pr=protected):
            _audit_claim_event(
                workspace_root, issue_number, "denied-release", current_session_id,
                detail=f"active claim held by {claim_data.get('session_id')}",
            )
            return False

    ref = f"refs/claims/issue-{issue_number}"
    env = clean_git_env(workspace_root)
    push_res = _run_git(["git", "push", f"--force-with-lease={ref}:{sha}", "origin", f":{ref}"], workspace_root, env)
    if push_res.returncode != 0:
        return False

    _clear_claim_mirror(workspace_root, issue_number)
    _audit_claim_event(
        workspace_root, issue_number,
        "force-released" if force else "released",
        current_session_id,
        detail="malformed ref deleted" if claim_data is None else "",
    )

    from solomon_harness.github import _gh
    _gh(["issue", "edit", str(issue_number), "--remove-assignee", "@me"])
    return True


def refresh_claim(workspace_root: str, issue_number: int, session_id: str) -> bool:
    """Re-touch an existing claim's heartbeat_at, keeping it fresh past the TTL (B5a).

    Called periodically by the heartbeat thread ``workflows.run_stage`` spawns
    after a successful ``start`` claim, so a stage that runs longer than
    CLAIM_TTL_SECONDS before opening a PR does not become reclaimable
    mid-implementation (the #24 double-pick).

    Return contract -- the heartbeat loop stops only on a ``False``:

    - ``False`` ONLY when the claim is *confirmed* to belong to another
      session now (a different ``session_id`` read off the ref). That is the
      one case where continuing to heartbeat is pointless.
    - ``True`` when refreshed successfully, OR on a *transient* technical
      failure (ref not fetchable, commit not buildable, or the
      force-with-lease push did not land). A transient failure must NOT stop
      the heartbeat: the claim ref is still ours on origin, only this refresh
      did not go through, so the loop retries next interval. Conflating a
      transient git/network blip with a real takeover is exactly what would
      let a lapsed heartbeat reopen the #24 double-pick -- a genuine takeover
      is caught on the next tick, when the ref reads a foreign owner.
    """
    ref_info = get_claim_ref(workspace_root, issue_number)
    if not ref_info:
        # Transient fetch failure or a momentarily-absent ref -- not a
        # confirmed takeover. Keep heartbeating; retry next tick.
        logger.warning(
            "issue #%s: claim ref not readable while refreshing the heartbeat "
            "for session %s (transient?); will retry next interval.",
            issue_number,
            session_id,
        )
        return True
    sha, claim_data = ref_info
    if claim_data is None:
        # The ref now carries malformed content: whatever happened, it is no
        # longer provably this session's claim -- a confirmed loss, not a
        # transient blip.
        logger.warning(
            "issue #%s: claim ref content is no longer parseable while "
            "refreshing for session %s; stopping the heartbeat.",
            issue_number,
            session_id,
        )
        _audit_claim_event(workspace_root, issue_number, "heartbeat-lost", session_id, detail="ref content malformed")
        return False
    if claim_data.get("session_id") != session_id:
        logger.warning(
            "issue #%s: claim is now held by session %s, not %s; stopping "
            "the heartbeat.",
            issue_number,
            claim_data.get("session_id"),
            session_id,
        )
        _audit_claim_event(
            workspace_root, issue_number, "heartbeat-lost", session_id,
            detail=f"claim now held by {claim_data.get('session_id')}",
        )
        return False

    refreshed = dict(claim_data)
    refreshed["heartbeat_at"] = datetime.datetime.now(datetime.timezone.utc).isoformat()

    env = clean_git_env(workspace_root)
    new_sha = _mktree_commit(workspace_root, refreshed, env)
    if not new_sha:
        return True  # transient: could not build the commit; retry next tick.

    ref = f"refs/claims/issue-{issue_number}"
    push_res = _run_git(
        ["git", "push", f"--force-with-lease={ref}:{sha}", "origin", f"{new_sha}:{ref}"],
        workspace_root,
        env,
    )
    if push_res.returncode != 0:
        # A lost force-with-lease race or a transient push failure -- we cannot
        # tell which without re-reading, so keep heartbeating; the next tick's
        # ownership check turns a genuine takeover into the False stop above.
        logger.warning(
            "issue #%s: heartbeat refresh did not land (race or transient "
            "failure); will re-check ownership next interval.",
            issue_number,
        )
        return True

    _mirror_claim(workspace_root, issue_number, refreshed)
    return True

def fetch_all_claims(workspace_root: str) -> Dict[int, Dict[str, Any]]:
    """Fetch all claim references from the remote and return a dict of active claims."""
    env = clean_git_env(workspace_root)
    _run_git(["git", "fetch", "-q", "origin", "+refs/claims/*:refs/remotes/origin/claims/*"], workspace_root, env)

    res = _run_git(
        ["git", "for-each-ref", "refs/remotes/origin/claims/", "--format=%(refname) %(objectname)"],
        workspace_root,
        env,
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
            
        msg_res = _run_git(["git", "log", "-1", "--format=%B", refname], workspace_root, env)
        if msg_res.returncode == 0:
            claim_dict = parse_claim_commit_message(msg_res.stdout.strip())
            if claim_dict:
                claims[issue_num] = claim_dict
    return claims


def filter_unclaimed(
    workspace_root: str,
    issue_numbers: Iterable[int],
    current_session_id: Optional[str] = None,
) -> List[int]:
    """Filter issue numbers down to those not actively claimed by another session.

    The claim-aware filtering helper for any board-scan path that lists
    issue numbers directly (e.g. ``solomon_harness.github.list_open_issues``,
    which backs the workflow scan's direct ``gh issue list`` read) rather
    than through ``MemoryService.get_open_issues`` -- which already applies
    this same ``fetch_all_claims`` + ``is_claim_active`` pair over the
    memory-backed issue list. An issue actively claimed by another session is
    dropped; everything else (unclaimed, or claimed by this same session) is
    kept.

    Degrades to returning the input unchanged (best-effort, logged) when the
    claims ref cannot be fetched (no git remote, network down, no `git`
    binary): filtering out claimed issues is a convenience over the real
    enforcement, which is ``claim_issue``'s own CAS at `start` time -- an
    unfiltered list here is noisier, never unsafe.
    """
    if current_session_id is None:
        current_session_id = get_current_session_id()
    try:
        claims = fetch_all_claims(workspace_root)
    except Exception as exc:  # noqa: BLE001 - degrade to unfiltered, but log
        logger.warning(
            "could not fetch claims to filter the issue scan (%s); showing "
            "the unfiltered list.",
            exc,
        )
        return list(issue_numbers)

    # One board fetch shared across every liveness check in this scan; the
    # per-issue re-fetch was an N+1 on the session-start hot path.
    board_items: Optional[List[Dict[str, Any]]] = None
    board_fetched = False

    unclaimed: List[int] = []
    for number in issue_numbers:
        claim_data = claims.get(number)
        if claim_data is None:
            unclaimed.append(number)
            continue
        if not board_fetched:
            board_items = fetch_board_items(workspace_root)
            board_fetched = True
        has_pr = has_active_pr_or_review(workspace_root, number, board_items=board_items)
        if is_claim_active(claim_data, current_session_id, has_open_pr=has_pr):
            continue
        unclaimed.append(number)
    return unclaimed
