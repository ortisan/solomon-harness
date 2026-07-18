import os
import json
import sqlite3
import logging
import sys
import functools
import threading
import datetime
import glob
import hashlib
import re
import uuid
from contextlib import contextmanager
from typing import (
    Generator,
    Any,
    Dict,
    List,
    Optional,
    Protocol,
    Sequence,
    Union,
    runtime_checkable,
)


# Dimensionality of the default memory embedding. Must match the HNSW vector
# index DEFINEd on the ``memory`` table (DIMENSION 256) and the HashingEmbedder.
EMBEDDING_DIM = 256


@runtime_checkable
class Embedder(Protocol):
    """A text-to-vector embedder: anything with ``embed(text) -> list[float]``.

    The contract is intentionally narrow so a real semantic model (sentence
    transformers, an API embedder, etc.) can be dropped in to replace the default
    lexical embedder without touching the database client.
    """

    def embed(self, text: str) -> List[float]:
        ...


class HashingEmbedder:
    """A dependency-free LEXICAL embedder using the feature-hashing trick.

    Each token of the text is hashed into one of ``dim`` buckets with a signed
    contribution, and the accumulated vector is L2-normalized. Two texts land near
    each other in cosine space when they SHARE TOKENS, not when they are
    semantically related: this is lexical overlap, not meaning. It is the safe
    default because it needs no model download and no third-party dependency. For
    true semantic similarity, pass a model-backed object exposing the same
    ``embed(text) -> list[float]`` method to :class:`DatabaseClient`.
    """

    _TOKEN = re.compile(r"[a-z0-9]+")

    def __init__(self, dim: int = EMBEDDING_DIM) -> None:
        self.dim = dim

    def embed(self, text: str) -> List[float]:
        """Return the L2-normalized feature-hash vector for ``text``.

        An empty or token-less text yields the all-zero vector; cosine distance to
        a zero vector is undefined, so callers should treat an empty query as a
        no-op rather than a search.
        """
        vec = [0.0] * self.dim
        for token in self._TOKEN.findall((text or "").lower()):
            digest = hashlib.blake2b(token.encode("utf-8"), digest_size=8).digest()
            h = int.from_bytes(digest, "big")
            bucket = h % self.dim
            # A second, independent bit of the hash sets the sign so that frequent
            # collisions cancel on average instead of always reinforcing.
            sign = 1.0 if (h // self.dim) % 2 == 0 else -1.0
            vec[bucket] += sign
        norm = sum(v * v for v in vec) ** 0.5
        if norm > 0.0:
            vec = [v / norm for v in vec]
        return vec


# ---------------------------------------------------------------------------
# Canonical issue-status vocabulary (ADR-0006).
#
# One source of truth for the status token stored on an issue, so the
# normalize-on-write rule, the open/terminal predicate, and the cockpit's
# column mapping cannot drift apart. Board display names and casing aliases
# collapse to one canonical token per logical status; reads stay tolerant of
# legacy values (expand/contract, no destructive rewrite).
# ---------------------------------------------------------------------------

# Lowercased board display name / alias -> canonical token. A status not listed
# here passes through unchanged. The display columns and the legacy literal
# open carry casing aliases (ADR-0016) so the store never holds two rows
# differing only by case for the same logical status.
_STATUS_ALIASES = {
    "ideas": "Ideas",
    "backlog": "Backlog",
    "ready": "Ready",
    "open": "open",
    "in progress": "in_progress",
    "in_progress": "in_progress",
    "code review": "code_review",
    "code_review": "code_review",
    # "review" is a legacy word written by an early stage before the vocabulary
    # existed; it maps to code_review so the one-shot normalization pass can
    # actually retire it (#173).
    "review": "code_review",
    "qa": "qa",
    "done": "closed",
    "closed": "closed",
}

# Stored literals treated as terminal (delivered). New writes normalize to
# "closed"; "done" and "Done" remain so legacy rows written before normalization
# are still excluded by the open predicate. Bound as query parameters, never
# string-formatted, so the predicate carries no injection surface (STRIDE).
TERMINAL_STATUSES = ("closed", "done", "Done")

# Canonical token -> delivery-board display column, for the cockpit read side.
STATUS_DISPLAY_COLUMNS = {
    "Ideas": "Ideas",
    "Backlog": "Backlog",
    "Ready": "Ready",
    "in_progress": "In Progress",
    "code_review": "Code Review",
    "qa": "QA",
    "closed": "Done",
}

# The delivery-board display columns in fixed left-to-right order. This is the one
# canonical definition of the column names: it is derived from STATUS_DISPLAY_COLUMNS
# (insertion order Ideas -> Backlog -> Ready -> In Progress -> Code Review -> QA ->
# Done) so the column list can never drift from the status vocabulary. github.py and
# cockpit_read.py import this constant rather than re-declaring it (ADR-0006).
BOARD_COLUMNS: List[str] = list(STATUS_DISPLAY_COLUMNS.values())


def normalize_status(status: Optional[str]) -> Optional[str]:
    """Map a board display name or casing alias to its canonical memory token.

    The canonical tokens are in_progress, code_review, qa and the terminal
    closed; Ideas, Backlog, Ready and the legacy literal open pass through
    unchanged. None passes through so an unset status is never invented.
    """
    if status is None:
        return None
    return _STATUS_ALIASES.get(str(status).strip().lower(), status)


def is_terminal(status: Optional[str]) -> bool:
    """True when a status is terminal (delivered) under the canonical vocabulary.

    Normalizes first, then tests membership in the terminal-literal set, so every
    spelling of a delivered status (closed, done, Done, the board's Done) is
    classified terminal while open work is not.
    """
    return normalize_status(status) in TERMINAL_STATUSES


def is_github_issue(github_id: Optional[str]) -> bool:
    """True when ``github_id`` is a real GitHub issue id (a non-empty, ASCII,
    all-digits string), False for a composite RAID/follow-up slug (``116-R-01``),
    an empty or null id, a unicode-digit string, or any other tracking item.

    This is the single source of truth for the digits-only rule that segregates
    real GitHub work from internal tracking rows (#116). It is total: it never
    raises, defaulting any unknown shape to the tracking bucket (False).
    """
    s = str(github_id)
    return s.isdigit() and s.isascii()


def recover_parent(github_id: Optional[str], title: Optional[str]) -> Optional[str]:
    """Recover a tracking row's parent GitHub number from its slug id, else title.

    Tracking rows carry a composite slug id (``68-R-01``, ``45-M2``) and a human
    title (``RAID R-01 (#68)``). The parent number is read id-first -- the run of
    digits before the slug's first hyphen -- because the id is the structural key;
    failing that, the first ``#<digits>`` reference in the title is used, which
    subsumes the ``PR #45`` spelling. Returns the number as a string, or None when
    neither yields one. Pure and total (#127): it never raises and never invents a
    number, so a row with no recoverable parent is left open rather than guessed.
    """
    id_match = re.match(r"(\d+)-", str(github_id))
    if id_match:
        return id_match.group(1)
    title_match = re.search(r"#(\d+)", str(title))
    if title_match:
        return title_match.group(1)
    return None


# ---------------------------------------------------------------------------
# Canonical status vocabularies for the other stateful kinds (ADR-0016).
#
# The same normalize-on-write rule ADR-0006 established for issues, applied to
# loop runs (and, with ADR-0016, to handoffs, sessions and milestones): one
# canonical token per logical state, normalized here below every consumer, so
# a writer and an aggregator can never drift apart on spelling again (#165:
# the writer stored "failed" while the failure rate counted "failure", so
# every failed run was invisible). Reads stay tolerant of legacy tokens;
# unknown tokens pass through lowercased so normalization never invents a
# state -- the store-side ASSERT is what rejects genuine garbage.
# ---------------------------------------------------------------------------

# The canonical loop-run outcomes. workflows.py writes exactly these.
# "skipped": a zero-exit start that changed nothing (ADR-0039 amending
# ADR-0016); excluded from loop_run_failure_rate by construction.
LOOP_RUN_STATUSES = ("ok", "failed", "skipped")

# Lowercased legacy/alias token -> canonical loop-run token.
_LOOP_RUN_ALIASES = {
    "success": "ok",
    "passed": "ok",
    "failure": "failed",
    "error": "failed",
}


def _normalize_token(value: Optional[str], aliases: Dict[str, str]) -> Optional[str]:
    """Trim, lowercase, and alias-map one status token; None passes through."""
    if value is None:
        return None
    token = str(value).strip().lower()
    return aliases.get(token, token)


def normalize_loop_run_status(status: Optional[str]) -> Optional[str]:
    """Map a loop-run status to its canonical token (ok or failed).

    Legacy spellings collapse (success/passed -> ok, failure/error -> failed);
    an unknown token passes through lowercased; None passes through so an
    unset status is never invented.
    """
    return _normalize_token(status, _LOOP_RUN_ALIASES)


# The canonical handoff lifecycle: logged open, accepted by the recipient,
# done when the receiving stage completes.
HANDOFF_STATUSES = ("open", "accepted", "done")

_HANDOFF_ALIASES = {
    "ready": "open",
    "pending": "open",
    "approved": "accepted",
    "completed": "done",
    "closed": "done",
}

# The canonical session lifecycle: active while in flight, done when wrapped up.
SESSION_STATUSES = ("active", "done")

_SESSION_ALIASES = {
    "completed": "done",
    "closed": "done",
    "finished": "done",
}

# The canonical milestone lifecycle, matching GitHub's own open/closed states.
MILESTONE_STATES = ("open", "closed")

_MILESTONE_ALIASES = {
    "active": "open",
    "pending": "open",
    "complete": "closed",
    "completed": "closed",
    "done": "closed",
}


def normalize_handoff_status(status: Optional[str]) -> Optional[str]:
    """Map a handoff status to its canonical token (open, accepted, or done)."""
    return _normalize_token(status, _HANDOFF_ALIASES)


def normalize_session_status(status: Optional[str]) -> Optional[str]:
    """Map a session status to its canonical token (active or done)."""
    return _normalize_token(status, _SESSION_ALIASES)


def normalize_milestone_state(state: Optional[str]) -> Optional[str]:
    """Map a milestone state to its canonical token (open or closed)."""
    return _normalize_token(state, _MILESTONE_ALIASES)


# The memory categories that are operational blobs, not semantic notes: the
# code index (bootstrap writes categories codebase_index and index) and the
# per-card board history. Embedding them pollutes the HNSW vector index, so
# semantic_search returns file contents instead of meaning (ADR-0016, F6).
# A DENYLIST, deliberately: an unknown category keeps its embedding and stays
# searchable without a code change, whereas an allowlist would silently drop
# new categories from the index -- the failure mode being fixed, inverted.
NON_SEMANTIC_MEMORY_CATEGORIES = ("codebase_index", "index", "board_history", "claim")


def is_semantic_category(category: Optional[str]) -> bool:
    """Whether a memory category belongs in the semantic vector index.

    Total: None or empty (no category) counts as semantic, preserving the
    pre-gate behavior for every category not on the denylist.
    """
    return str(category or "").strip().lower() not in NON_SEMANTIC_MEMORY_CATEGORIES


# The status literals a harness write can legitimately store on an issue row:
# the canonical display/board tokens (ADR-0006) plus the legacy literals that
# replays and reads stay tolerant of. This is the SurrealDB ASSERT set for
# issues.status; the other kinds assert their canonical vocabulary directly.
ISSUE_STATUS_LITERALS = tuple(STATUS_DISPLAY_COLUMNS) + ("open",) + TERMINAL_STATUSES


def _surreal_literal_array(values: Sequence[str]) -> str:
    """Render internal status constants as a SurrealQL string array literal.

    Only ever fed the module's own vocabulary tuples (never caller input), and
    deduplicated preserving order so overlapping legacy sets stay tidy.
    """
    seen = dict.fromkeys(values)
    return "[" + ", ".join("'" + v + "'" for v in seen) + "]"


# ---------------------------------------------------------------------------
# Canonical person key (ADR-0012).
#
# The cross-tenant subject of an issue. Like normalize_status, it is normalized
# on write and lives here, below every consumer, so the key cannot drift across
# the cockpit, digest, and evals. An email is preferred because it is stable
# across projects and tools; a handle is namespaced gh:<login> so it can never
# collide with an email; a null/empty assignee reads back as "unassigned".
# ---------------------------------------------------------------------------

# Reserved query token for an issue with no person key. Never a valid concrete
# key: every real key is an email or a gh: handle, so no assignee normalizes to it.
UNASSIGNED_PERSON_KEY = "unassigned"


def normalize_person_key(email: Optional[str], login: Optional[str]) -> Optional[str]:
    """Map an email and a login to the canonical, cross-tenant person key.

    Implements the ADR-0012 identity contract at its normative scalar seam: the
    caller (the github.py capture site) extracts the email and login from the
    GitHub assignee JSON, so this function stays free of any source shape. Total
    and deterministic: it never raises and has no side effects. A non-empty,
    ``@``-bearing email wins, lowercased and trimmed, because an email is the same
    string across projects and tools. Otherwise a non-empty login yields
    ``gh:<lowercased-login>``; the ``gh:`` namespace has no ``@``, so a handle key
    can never collide with an email key. When neither yields a usable value the
    result is None, which reads back under the reserved ``unassigned`` pseudo-key
    via :func:`person_key_or_unassigned`.
    """
    normalized_email = str(email or "").strip().lower()
    if normalized_email and "@" in normalized_email:
        return normalized_email
    normalized_login = str(login or "").strip().lower()
    if normalized_login:
        return f"gh:{normalized_login}"
    return None


def person_key_or_unassigned(key: Optional[str]) -> str:
    """Map a stored person key (or None) to a queryable subject token.

    A null key reads back as the reserved ``unassigned`` pseudo-key, so the
    "unassigned" subject lives in one named, tested place rather than being
    re-derived by every read consumer.
    """
    return key if key is not None else UNASSIGNED_PERSON_KEY


class SpectronFallbackClient:
    """Fallback client for Spectron REST API when the python package doesn't export it."""

    def __init__(self, context: str, endpoint: str, api_key: str, timeout: float = 30.0, max_retries: int = 3):
        self.context = context
        self.endpoint = endpoint.rstrip('/')
        self.api_key = api_key
        self.timeout = timeout
        self.max_retries = max_retries
        import requests
        self.session = requests.Session()
        self.session.headers.update({
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        })

    def remember(self, fact: str, scope: Optional[List[str]] = None) -> Any:
        url = f"{self.endpoint}/api/v1/{self.context}/facts"
        payload: Dict[str, Any] = {"fact": fact}
        if scope:
            payload["scope"] = scope
        resp = self.session.post(url, json=payload, timeout=self.timeout)
        resp.raise_for_status()
        return resp.json()

    def recall(self, query: str, scope: Optional[List[str]] = None) -> Any:
        url = f"{self.endpoint}/api/v1/{self.context}/query"
        payload: Dict[str, Any] = {"query": query}
        if scope:
            payload["scope"] = scope
        resp = self.session.post(url, json=payload, timeout=self.timeout)
        resp.raise_for_status()
        
        data = resp.json()
        class MockHit:
            def __init__(self, text):
                self.text = text
        class MockResponse:
            def __init__(self, hits):
                self.hits = hits
        hits = [MockHit(h.get("text", "")) for h in data.get("hits", [])]
        return MockResponse(hits)


def _resolve_database(configured: Optional[str], project_root: str) -> str:
    """Resolve the SurrealDB database name for a project.

    The shared SurrealDB holds every project, so the database name must be unique
    per project, not the generic "harness". When the config carries that sentinel
    (or nothing), derive an ``<owner>-<repo>`` tenant from the git remote so two
    projects never collide in the shared instance. An explicit name is kept as-is.
    """
    database = configured or "harness"
    if database in ("", "harness"):
        try:
            from solomon_harness.home import derive_tenant

            return derive_tenant(project_root)
        except Exception:
            return "harness"
    return database


def _resolve_mirror_root_path(
    project_root: str,
    db_path: Optional[str] = None,
    override: Optional[str] = None,
) -> str:
    """Resolve the write-through mirror root from a single precedence rule.

    Shared by :class:`DatabaseClient` and the healthcheck so a pending-reconcile
    count is never read from a different directory than the one writes land in
    (issue #35). Precedence: an explicit ``override``, then ``HARNESS_MIRROR_ROOT``,
    then a ``memory-mirror`` sibling of an explicit ``db_path`` or ``HARNESS_DB_PATH``
    (the test/sandbox isolation convention), then
    ``<project_root>/.solomon/memory-mirror``.
    """
    if override:
        return override
    env = os.environ.get("HARNESS_MIRROR_ROOT")
    if env:
        return env
    if db_path:
        base = os.path.dirname(os.path.abspath(db_path))
        return os.path.join(base, "memory-mirror")
    env_db = os.environ.get("HARNESS_DB_PATH")
    if env_db:
        base = os.path.dirname(os.path.abspath(env_db))
        return os.path.join(base, "memory-mirror")
    return os.path.join(project_root, ".solomon", "memory-mirror")


def _surreal_connection_exception_types() -> tuple:
    """Connection/websocket exception classes that mark a transport fault by type.

    The surrealdb SDK (``ConnectionUnavailableError``) and its websocket transport
    raise dedicated exception types when the connection drops; matching on the type
    is far more precise than scanning a message for substrings. Each candidate is
    imported defensively because the exact set varies by SDK/websockets version, so
    any class that is absent is simply skipped (issue #37).
    """
    types: List[type] = []
    candidates = [
        ("surrealdb.errors", "ConnectionUnavailableError"),
        ("websockets.exceptions", "ConnectionClosed"),
        ("websockets.exceptions", "ConnectionClosedError"),
        ("websockets.exceptions", "ConnectionClosedOK"),
        ("websockets.exceptions", "WebSocketException"),
    ]
    for module_name, attr in candidates:
        try:
            module = __import__(module_name, fromlist=[attr])
        except Exception:
            continue
        exc_type = getattr(module, attr, None)
        if isinstance(exc_type, type) and issubclass(exc_type, BaseException):
            types.append(exc_type)
    return tuple(types)


_SURREAL_CONNECTION_EXCEPTIONS = _surreal_connection_exception_types()


class _ConnectionLost(Exception):
    """Raised when a SurrealDB call fails because the transport/connection dropped.

    This is deliberately distinct from a query or data error: only a connection
    loss may trigger a reconnect or a fallback to SQLite (issue #37). A malformed
    query or a data error must surface unchanged.
    """


def _resilient(method):
    """Make a public DatabaseClient method survive a mid-session connection drop.

    On ``_ConnectionLost`` the wrapper attempts exactly one bounded reconnect. If
    that succeeds it re-runs the method once and returns its result. If the
    reconnect fails (or the single retry still loses the connection) it activates
    the SQLite fallback and re-runs the method, which then takes its own SQLite
    branch -- so a transient drop never propagates as a raised error.

    A method that is already on the SQLite backend never raises ``_ConnectionLost``,
    so the wrapper is a transparent pass-through for SQLite-only clients.
    """

    @functools.wraps(method)
    def wrapper(self, *args, **kwargs):
        try:
            return method(self, *args, **kwargs)
        except _ConnectionLost:
            if self._connect_surreal():
                try:
                    return method(self, *args, **kwargs)
                except _ConnectionLost:
                    pass
            self._activate_sqlite_fallback()
            return method(self, *args, **kwargs)

    return wrapper


class DatabaseClient:
    """A client to manage SQLite or SurrealDB database operations for the agent harness."""

    backend: str
    db: Any
    db_path: Optional[str]
    busy_timeout_seconds: float
    harness_dir: str

    # SurrealDB is used as a true multi-model store: relational tables with
    # indexes, graph RELATION edges, a timeseries metrics table, and an HNSW
    # vector index for semantic memory. Every DEFINE is IF NOT EXISTS
    # (idempotent) and SCHEMALESS, so it never rejects the existing
    # string-typed writes. Kept as ONE STATEMENT PER LIST ENTRY (not one
    # concatenated multi-statement string): the surrealdb SDK's ``.query()``
    # only surfaces the FIRST statement's result of whatever string it is
    # given, so a single call with everything concatenated would silently
    # accept a failure in any later DEFINE (an index, a RELATION table, the
    # HNSW vector index). Executing one statement per call makes every
    # statement the "first" (and only) result of its own call, so a failing
    # statement is never swallowed.
    _SURREAL_SCHEMA_STATEMENTS: List[str] = [
        "DEFINE TABLE IF NOT EXISTS decisions SCHEMALESS;",
        "DEFINE TABLE IF NOT EXISTS memory SCHEMALESS;",
        "DEFINE TABLE IF NOT EXISTS milestones SCHEMALESS;",
        "DEFINE TABLE IF NOT EXISTS issues SCHEMALESS;",
        "DEFINE TABLE IF NOT EXISTS backtest_runs SCHEMALESS;",
        "DEFINE TABLE IF NOT EXISTS sessions SCHEMALESS;",
        "DEFINE TABLE IF NOT EXISTS handoffs SCHEMALESS;",
        "DEFINE TABLE IF NOT EXISTS releases SCHEMALESS;",
        "DEFINE TABLE IF NOT EXISTS loop_runs SCHEMALESS;",
        "DEFINE TABLE IF NOT EXISTS metrics SCHEMALESS;",
        # Graph: typed RELATION edge tables.
        "DEFINE TABLE IF NOT EXISTS blocks TYPE RELATION;",
        "DEFINE TABLE IF NOT EXISTS supersedes TYPE RELATION;",
        "DEFINE TABLE IF NOT EXISTS contains TYPE RELATION;",
        "DEFINE TABLE IF NOT EXISTS produced TYPE RELATION;",
        "DEFINE TABLE IF NOT EXISTS addresses TYPE RELATION;",
        # Episodic work graph (ADR-0018): sessions and loop_runs link to the
        # issues they advance, so resume is a graph query, not a prose regex.
        "DEFINE TABLE IF NOT EXISTS worked_on TYPE RELATION;",
        # Relational: indexes for the hot lookups. github_id is the record
        # key, so it is unique by construction.
        "DEFINE INDEX IF NOT EXISTS issues_github_id "
        "ON issues FIELDS github_id UNIQUE;",
        "DEFINE INDEX IF NOT EXISTS issues_status ON issues FIELDS status;",
        "DEFINE INDEX IF NOT EXISTS decisions_created_at "
        "ON decisions FIELDS created_at;",
        # Time-ordered hot paths. get_latest_activity reads the newest sessions
        # and handoffs row (ORDER BY timestamp DESC LIMIT 1) on every session
        # start; without these the planner does a TableScan plus sort that grows
        # with the ledger. Indexing the ordered field turns each into an
        # IndexScan, the plan decisions_created_at already gets. A new index name
        # applies to existing tenants on the next connect, so no backfill.
        "DEFINE INDEX IF NOT EXISTS sessions_timestamp "
        "ON sessions FIELDS timestamp;",
        "DEFINE INDEX IF NOT EXISTS handoffs_timestamp "
        "ON handoffs FIELDS timestamp;",
        # loop_run_throughput / loop_run_failure_rate filter and group loop_runs
        # by created_at.
        "DEFINE INDEX IF NOT EXISTS loop_runs_created_at "
        "ON loop_runs FIELDS created_at;",
        # Timeseries: composite index on (name, time) for metrics.
        "DEFINE INDEX IF NOT EXISTS metrics_name_time "
        "ON metrics FIELDS name, time;",
        # Vector: HNSW index over the 256-dim memory embedding.
        "DEFINE INDEX IF NOT EXISTS memory_embedding ON memory "
        f"FIELDS embedding HNSW DIMENSION {EMBEDDING_DIM} "
        "DIST COSINE TYPE F32;",
        # Typed states (ADR-0016): one targeted ASSERT per stateful field. The
        # tables stay SCHEMALESS elsewhere. Harness code normalizes on write
        # (normalize_status and friends, below every consumer), so these can
        # never fire for harness writes; they exist to reject garbage from
        # foreign writers. NONE stays allowed so a row that never carried the
        # field remains writable. Each is its own list entry -- one statement
        # per query() call -- so a failing DEFINE is never swallowed.
        #
        # OVERWRITE, not IF NOT EXISTS: a closed vocabulary can grow (ADR-0039
        # added "skipped"), and IF NOT EXISTS is a no-op on a pre-existing
        # field, so a database created before the growth would keep the old
        # ASSERT and reject the new token forever. OVERWRITE re-applies the
        # current vocabulary on every connect, so these fields self-heal.
        "DEFINE FIELD OVERWRITE status ON issues "
        f"ASSERT $value = NONE OR $value IN {_surreal_literal_array(ISSUE_STATUS_LITERALS)};",
        "DEFINE FIELD OVERWRITE status ON handoffs "
        f"ASSERT $value = NONE OR $value IN {_surreal_literal_array(HANDOFF_STATUSES)};",
        "DEFINE FIELD OVERWRITE status ON sessions "
        f"ASSERT $value = NONE OR $value IN {_surreal_literal_array(SESSION_STATUSES)};",
        "DEFINE FIELD OVERWRITE status ON loop_runs "
        f"ASSERT $value = NONE OR $value IN {_surreal_literal_array(LOOP_RUN_STATUSES)};",
        "DEFINE FIELD OVERWRITE state ON milestones "
        f"ASSERT $value = NONE OR $value IN {_surreal_literal_array(MILESTONE_STATES)};",
        # First-class issue status transitions (ADR-0016, F4): one row per board
        # move, typed where it matters (the issue link and the timestamp) while
        # the table stays SCHEMALESS elsewhere. The composite index makes the
        # per-issue timeline (and cycle time) one indexed query instead of a
        # JSON parse per issue.
        "DEFINE TABLE IF NOT EXISTS transitions SCHEMALESS;",
        "DEFINE FIELD IF NOT EXISTS issue ON transitions TYPE record<issues>;",
        "DEFINE FIELD IF NOT EXISTS entered_at ON transitions TYPE datetime;",
        "DEFINE INDEX IF NOT EXISTS transitions_issue_entered "
        "ON transitions FIELDS issue, entered_at;",
    ]

    def __init__(
        self,
        db_path: Optional[str] = None,
        harness_dir: Optional[str] = None,
        mirror_root: Optional[str] = None,
        embedder: Optional[Embedder] = None,
    ) -> None:
        """Initializes the database client and selects the appropriate backend.

        Args:
            db_path: Optional custom path to the SQLite database file (if using SQLite).
            harness_dir: The agent (or template) directory that owns .agent/config.json
                and the memory store. Passed explicitly by the thin agent entrypoint;
                when omitted it falls back to this file's package location.
            mirror_root: Optional override for the write-through Markdown mirror root
                (issue #35). Defaults to ``<repo>/.solomon/memory-mirror``; tests point
                it at a temp directory so they never touch the real project's state.
            embedder: Optional text embedder used to vectorize memory entries for
                semantic search. Defaults to :class:`HashingEmbedder`, a dependency-free
                lexical embedder; pass a model-backed embedder for true semantic search.
        """
        self._init_embedder(embedder)
        self._init_connection_state(db_path)
        self._resolve_roots(harness_dir)

        # Root for the write-through Markdown mirror (issue #35). Resolved once, up
        # front, so every write funnels to the same gitignored local store.
        self._mirror_root = self._resolve_mirror_root(mirror_root)

        db_config = self._load_config()
        self._init_backend(db_config)

    def _init_embedder(self, embedder: Optional[Embedder]) -> None:
        """Choose the embedder that vectorizes memory for the vector index."""
        # The embedder that vectorizes memory for the HNSW vector index. The default
        # is lexical (token overlap), swappable for a real semantic model.
        self._embedder: Embedder = embedder or HashingEmbedder()

    def _init_connection_state(self, db_path: Optional[str]) -> None:
        """Set the backend defaults and the rebuildable SurrealDB params."""
        self.backend = "sqlite"
        self.db = None
        # Typed Any: assigned a Spectron or SpectronFallbackClient by
        # _init_spectron when configured, else stays None.
        self.spectron: Any = None
        self.db_path = db_path
        # The explicit db_path argument (kept distinct from the resolved store path)
        # marks a test/sandbox-isolated client, used to keep the mirror beside it.
        self._db_path_param = db_path

        # HARNESS_DB_PATH must force SQLite isolation exactly like an explicit
        # db_path argument: it has to set self.db_path BEFORE _init_backend runs,
        # because _init_backend only enters the SurrealDB branch when
        # ``self.db_path is None``. Reading it later (inside _resolve_sqlite_path)
        # is too late -- with the shared SurrealDB reachable the backend is already
        # chosen, and writes land in the real multi-tenant store, so the env var
        # silently fails to isolate (issue #40). Resolve to an absolute path and
        # create its parent up front so the SQLite connect never races a missing
        # directory. An empty value is ignored (treated as unset).
        if self.db_path is None:
            env_db = os.environ.get("HARNESS_DB_PATH")
            if env_db:
                abs_db = os.path.abspath(env_db)
                os.makedirs(os.path.dirname(abs_db), exist_ok=True)
                self.db_path = abs_db

        # SurrealDB connection params captured so the connection can be rebuilt
        # mid-session after a drop, not only at construction (issue #37).
        self._surreal_class: Any = None
        self._surreal_url: Optional[str] = None
        self._surreal_username: Optional[str] = None
        self._surreal_password: Optional[str] = None
        self._surreal_namespace: Optional[str] = None
        self._surreal_database: Optional[str] = None
        self._connect_deadline: float = 5.0

        # Why the client is on SQLite although a SurrealDB primary was intended.
        # None while SurrealDB serves, and None when SQLite is a deliberate
        # choice (explicit db_path, or no surrealdb provider configured). Every
        # fallback path records its reason here so backend_status() can report
        # the degradation honestly instead of looking like a clean SQLite setup.
        self._fallback_reason: Optional[str] = None

    def _resolve_roots(self, harness_dir: Optional[str]) -> None:
        """Resolve the owning harness directory and the repository root."""
        # The shared client no longer lives inside the agent directory, so the caller
        # passes the owning harness directory explicitly; fall back to this file's
        # package location for standalone or test use.
        if harness_dir is None:
            harness_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        self.harness_dir = harness_dir

        # Locate the repository root by walking up from the harness directory.
        project_root: str = harness_dir
        found_root: bool = False
        while project_root and project_root != os.path.dirname(project_root):
            if os.path.exists(os.path.join(project_root, ".git")):
                found_root = True
                break
            if (
                os.path.exists(os.path.join(project_root, "agents"))
                and os.path.exists(os.path.join(project_root, "memory"))
                and os.path.exists(os.path.join(project_root, "solomon_harness"))
            ):
                found_root = True
                break
            project_root = os.path.dirname(project_root)

        if not found_root:
            project_root = harness_dir

        # Retained so the mid-session SQLite fallback can resolve the same store
        # path the constructor would have used (issue #37), and for read-only
        # tenant discovery (list_databases).
        self._project_root = project_root

    def _load_config(self) -> Dict[str, Any]:
        """Read .agent/config.json and capture the database block's fields."""
        # Load configuration. Prefer the harness-local .agent/config.json, which carries
        # the per-agent `database` block, and fall back to the project-root config.
        config: Dict[str, Any] = {}
        candidate_config_paths = [
            os.path.join(self.harness_dir, ".agent", "config.json"),
            os.path.join(self._project_root, ".agent", "config.json"),
        ]
        for candidate in candidate_config_paths:
            if os.path.isfile(candidate):
                try:
                    with open(candidate, "r", encoding="utf-8") as f:
                        config = json.load(f)
                    break
                except (OSError, json.JSONDecodeError) as exc:
                    logging.error(f"Failed to read configuration at {candidate}: {exc}")

        db_config = config.get("database", {})
        self.busy_timeout_seconds = float(db_config.get("busy_timeout_seconds", 5.0))

        # Retained for read-only tenant discovery (list_databases). On the SQLite
        # fallback the resolvable tenant is derived from these, not from the store.
        self._configured_database = db_config.get("database")
        # The SurrealDB namespace that holds every tenant database. Stored so the
        # read-only use_tenant() accessor can rebind the connection scope to the
        # selected tenant with the same parameterized SDK bind the constructor uses.
        self._namespace = db_config.get("namespace", "solomon")
        return db_config

    def _init_backend(self, db_config: Dict[str, Any]) -> None:
        """Bring up SurrealDB when configured and reachable, else SQLite."""
        provider = db_config.get("provider")
        # An explicit db_path forces the SQLite backend (used for test isolation and
        # eval sandboxes), regardless of the configured provider.
        if provider == "surrealdb" and self.db_path is None:
            # Dynamically import surrealdb to support dynamic backend loading
            try:
                import surrealdb  # type: ignore[import-not-found]

                Surreal = surrealdb.Surreal
                has_surrealdb = True
            except (ImportError, AttributeError):
                has_surrealdb = False
                Surreal = None

            url = os.environ.get(
                "SURREAL_URL", db_config.get("url", "ws://localhost:8000/rpc")
            )
            # Credentials come from the environment first, then config. There is no
            # committed default credential: for a non-local server with no credentials
            # we fail closed and fall back to SQLite rather than guessing root/root.
            username = os.environ.get("SURREAL_USER", db_config.get("username"))
            password = os.environ.get("SURREAL_PASS", db_config.get("password"))
            is_local = any(h in url for h in ("localhost", "127.0.0.1", "0.0.0.0"))
            if is_local:
                username = username or "root"
                if not password:
                    try:
                        from solomon_harness.home import generated_memory_password

                        password = generated_memory_password()
                    except Exception:
                        password = None
                password = password or "root"
            creds_ok = bool(username and password)

            if has_surrealdb and Surreal is not None and creds_ok:
                namespace = self._namespace
                database = _resolve_database(
                    db_config.get("database"), self._project_root
                )

                # Capture the params so _connect_surreal can rebuild the handle
                # after a mid-session drop, not only here at construction (#37).
                self._surreal_class = Surreal
                self._surreal_url = url
                self._surreal_username = username
                self._surreal_password = password
                self._surreal_namespace = namespace
                self._surreal_database = database
                self._connect_deadline = float(
                    db_config.get("connect_timeout_seconds", 5.0)
                )

                if self._connect_surreal():
                    try:
                        # Initialize SurrealDB tables. IF NOT EXISTS makes this
                        # idempotent: SurrealDB v2+ errors on re-DEFINE otherwise.
                        # Executed statement-by-statement (not as one concatenated
                        # multi-statement string): see _SURREAL_SCHEMA_STATEMENTS for
                        # why, and _bootstrap_surreal_schema for the raise-on-any-
                        # failure contract. The backend is marked ready only after
                        # every statement has actually succeeded.
                        self._bootstrap_surreal_schema()
                        self.backend = "surrealdb"
                        self._init_spectron(db_config)
                    except Exception as e:
                        sys.stderr.write(f"Warning: SurrealDB initialization failed: {e}\n")
                        sys.stderr.write(
                            "SurrealDB library or server unavailable. Falling back to SQLite backend.\n"
                        )
                        if self.db:
                            try:
                                self.db.close()
                            except Exception:
                                pass
                            self.db = None
                        self.backend = "sqlite"
                        self._fallback_reason = f"SurrealDB initialization failed: {e}"
                else:
                    sys.stderr.write("Warning: Connection to SurrealDB failed.\n")
                    sys.stderr.write(
                        "SurrealDB library or server unavailable. Falling back to SQLite backend.\n"
                    )
                    self.backend = "sqlite"
                    self._fallback_reason = "connection to SurrealDB failed"
            else:
                if not creds_ok:
                    sys.stderr.write(
                        "SurrealDB credentials are not set for a non-local URL; set "
                        "SURREAL_USER/SURREAL_PASS. Falling back to SQLite backend.\n"
                    )
                    self._fallback_reason = (
                        "SurrealDB credentials are not set for a non-local URL"
                    )
                else:
                    sys.stderr.write(
                        "SurrealDB library or server unavailable. Falling back to SQLite backend.\n"
                    )
                    self._fallback_reason = "surrealdb library unavailable"
                self.backend = "sqlite"

        # Initialize SQLite if backend is sqlite
        if self.backend == "sqlite":
            if self.db_path is None:
                self.db_path = self._resolve_sqlite_path()
            self._init_sqlite_db()

    def _init_spectron(self, db_config: Dict[str, Any]) -> None:
        """Connect the optional Spectron client when URL and API key are set."""
        # Initialize Spectron if URL and API Key are configured
        spectron_url = os.environ.get(
            "SPECTRON_URL", db_config.get("spectron_url")
        )
        spectron_api_key = os.environ.get(
            "SPECTRON_API_KEY", db_config.get("spectron_api_key")
        )
        spectron_context = os.environ.get(
            "SPECTRON_CONTEXT", db_config.get("spectron_context", "dev")
        )
        if spectron_url and spectron_api_key:
            try:
                try:
                    # Spectron ships only in newer surrealdb builds;
                    # the except below handles its absence at runtime.
                    from surrealdb import Spectron  # type: ignore[attr-defined]
                    self.spectron = Spectron(
                        context=spectron_context,
                        endpoint=spectron_url,
                        api_key=spectron_api_key
                    )
                except (ImportError, AttributeError):
                    self.spectron = SpectronFallbackClient(
                        context=spectron_context,
                        endpoint=spectron_url,
                        api_key=spectron_api_key
                    )
            except Exception as e:
                sys.stderr.write(f"Warning: Connection to Spectron failed: {e}\n")
                self.spectron = None

    def backend_status(self) -> Dict[str, Any]:
        """Report which backend serves this client, publicly (issue #163).

        Returns ``{"backend", "degraded", "fallback_reason"}``. ``degraded`` is
        True only when a SurrealDB primary was intended but the SQLite fallback
        is serving; a deliberate SQLite client (explicit ``db_path``, or no
        surrealdb provider configured) is not degraded and carries no reason.
        The session-start digest already renders this state; this accessor
        gives sessions and workflows the same answer without reaching into
        private attributes.
        """
        degraded = self.backend != "surrealdb" and self._fallback_reason is not None
        return {
            "backend": self.backend,
            "degraded": degraded,
            "fallback_reason": self._fallback_reason if degraded else None,
        }

    @contextmanager
    def _sqlite_conn(self) -> Generator[sqlite3.Connection, None, None]:
        """Establishes and returns a SQLite connection context and ensures it is closed on exit."""
        if self.db_path is None:
            raise ValueError("Database path must be set for SQLite backend")
        conn = sqlite3.connect(self.db_path, timeout=self.busy_timeout_seconds)
        conn.row_factory = sqlite3.Row
        # WAL plus a busy timeout keeps the shared store safe when several agents write
        # concurrently instead of failing with "database is locked".
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute(f"PRAGMA busy_timeout={int(self.busy_timeout_seconds * 1000)}")
        # SQLite does not enforce a declared FOREIGN KEY unless this pragma is set
        # on the connection (it defaults OFF). The harness schema no longer
        # declares one (ADR-0016 dropped issues.milestone_id -> milestones.id,
        # which rejected the minted milestone record ids), but the pragma stays
        # ON so any store that still carries the legacy constraint keeps its
        # original enforcement until its rebuild migration runs. Must be set
        # before any transaction begins, so it runs here, before ``with conn:``.
        conn.execute("PRAGMA foreign_keys = ON")
        try:
            with conn:
                yield conn
        finally:
            conn.close()

    def _init_sqlite_db(self) -> None:
        """Creates the required SQLite tables if they do not already exist."""
        queries = [
            """
            CREATE TABLE IF NOT EXISTS decisions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                record_id TEXT,
                title TEXT NOT NULL,
                rationale TEXT,
                outcome TEXT,
                author TEXT,
                branch TEXT,
                commit_sha TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            """,
            """
            CREATE TABLE IF NOT EXISTS memory (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL,
                category TEXT,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            """,
            """
            CREATE TABLE IF NOT EXISTS milestones (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                record_id TEXT,
                title TEXT NOT NULL,
                description TEXT,
                due_date TEXT,
                state TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            """,
            # No FOREIGN KEY on milestone_id (ADR-0016): the reference now
            # carries the minted milestone record id, which the old FK
            # (targeting the integer rowid) rejected; the SurrealDB primary
            # never enforced one, and the linkage is soft by design.
            """
            CREATE TABLE IF NOT EXISTS issues (
                github_id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                type_ TEXT,
                status TEXT,
                milestone_id TEXT,
                assignee TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            """,
            """
            CREATE TABLE IF NOT EXISTS backtest_runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                record_id TEXT,
                strategy_name TEXT NOT NULL,
                sharpe_ratio REAL,
                max_drawdown REAL,
                profit_factor REAL,
                parameters TEXT,
                dataset TEXT,
                commit_sha TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            """,
            """
            CREATE TABLE IF NOT EXISTS sessions (
                session_id TEXT PRIMARY KEY,
                agent_name TEXT,
                task TEXT,
                messages TEXT,
                status TEXT,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            """,
            """
            CREATE TABLE IF NOT EXISTS handoffs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                record_id TEXT,
                sender TEXT,
                recipient TEXT,
                contract_type TEXT,
                contract_path TEXT,
                status TEXT,
                summary TEXT,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            """,
            """
            CREATE TABLE IF NOT EXISTS releases (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                record_id TEXT,
                version TEXT NOT NULL,
                tag TEXT,
                notes TEXT,
                issue_github_id TEXT,
                milestone_id TEXT,
                commit_sha TEXT,
                released_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            """,
            """
            CREATE TABLE IF NOT EXISTS loop_runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                record_id TEXT,
                stage TEXT,
                target TEXT,
                decision TEXT,
                status TEXT,
                session_id TEXT,
                target_issue INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            """,
            # Timeseries metrics, mirrored on the SQLite fallback so recorded
            # statistics survive a backend outage. ``tags`` holds JSON, ``time`` an
            # ISO-8601 string; the composite index matches the SurrealDB layout.
            """
            CREATE TABLE IF NOT EXISTS metrics (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                record_id TEXT,
                name TEXT NOT NULL,
                value REAL,
                tags TEXT,
                time TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            """,
            "CREATE INDEX IF NOT EXISTS metrics_name_time ON metrics (name, time);",
            # Issue status transitions, mirrored on the SQLite fallback so board
            # moves are recorded even degraded (ADR-0016). ``github_id`` stands in
            # for the SurrealDB record link; ``entered_at`` is a UTC ISO string;
            # ``record_id`` is the client-minted id (backend-invariant, F7).
            """
            CREATE TABLE IF NOT EXISTS transitions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                record_id TEXT,
                github_id TEXT NOT NULL,
                from_status TEXT,
                to_status TEXT,
                entered_at TIMESTAMP,
                actor TEXT
            );
            """,
            "CREATE UNIQUE INDEX IF NOT EXISTS transitions_record_id "
            "ON transitions (record_id);",
            "CREATE INDEX IF NOT EXISTS transitions_issue_entered "
            "ON transitions (github_id, entered_at);",
            # worked_on parity link table (ADR-0018). On SurrealDB the edge is
            # a RELATE through the mirrored funnel; whenever a link write does
            # not land on the primary (pure-SQLite or degraded fallback) this
            # table keeps graph-based resume working. ``source_table`` is
            # 'sessions' or 'loop_runs'; ``source_id`` the session_id or the
            # minted loop_run record id. The unique index makes a re-save of
            # the same session idempotent (INSERT OR IGNORE).
            """
            CREATE TABLE IF NOT EXISTS worked_on (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                record_id TEXT,
                source_table TEXT NOT NULL,
                source_id TEXT NOT NULL,
                github_id TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            """,
            "CREATE UNIQUE INDEX IF NOT EXISTS worked_on_link "
            "ON worked_on (source_table, source_id, github_id);",
            "CREATE INDEX IF NOT EXISTS worked_on_issue ON worked_on (github_id);",
        ]

        try:
            with self._sqlite_conn() as conn:
                cursor = conn.cursor()
                for query in queries:
                    cursor.execute(query)
                self._ensure_issue_assignee_column(conn)
                self._ensure_issue_milestone_id_is_text(conn)
                self._ensure_issue_milestone_fk_dropped(conn)
                self._ensure_column(conn, "sessions", "status", "TEXT")
                self._ensure_column(conn, "handoffs", "summary", "TEXT")
                self._ensure_column(conn, "loop_runs", "target_issue", "INTEGER")
                self._ensure_record_id_columns(conn)
                conn.commit()
        except sqlite3.Error as e:
            logging.error(f"SQLite database initialization failed: {e}")
            raise RuntimeError(f"SQLite database initialization failed: {e}")

    @staticmethod
    def _ensure_issue_milestone_id_is_text(conn: sqlite3.Connection) -> None:
        """Migrate a pre-migration issues.milestone_id from INTEGER to TEXT.

        releases.milestone_id has always been TEXT (save_release str()-casts it),
        while issues.milestone_id was declared INTEGER, forcing a string-cast at
        every relational read that compares the two. A fresh store's CREATE TABLE
        already declares TEXT, so this is a no-op there; a pre-migration store is
        migrated in place.

        SQLite has no ALTER COLUMN to change a declared type, so the migration
        rebuilds the table: rename the old one aside, recreate ``issues`` with the
        current column set (assignee only if the #118 migration already ran) and
        milestone_id TEXT, copy every row across with milestone_id cast to TEXT
        (a value is never otherwise changed), then drop the renamed original.

        Concurrency-safe like :meth:`_ensure_issue_assignee_column`: two
        simultaneous first-opens can both pass the PRAGMA guard before either
        renames, so the losing RENAME raises ``OperationalError: table ... already
        exists``, which means a concurrent open already started the same rebuild;
        that is treated as already-migrated. Any other OperationalError is a real
        failure and propagates.
        """
        columns = {row["name"]: row["type"] for row in conn.execute("PRAGMA table_info(issues)")}
        milestone_type = columns.get("milestone_id")
        if milestone_type is None or milestone_type.upper() == "TEXT":
            return  # already TEXT, or the table does not exist yet
        has_assignee = "assignee" in columns
        try:
            conn.execute("ALTER TABLE issues RENAME TO issues_pre_text_milestone")
        except sqlite3.OperationalError as exc:
            if "already exists" not in str(exc).lower():
                raise
            return
        assignee_column = ", assignee TEXT" if has_assignee else ""
        assignee_select = ", assignee" if has_assignee else ""
        # The rebuilt table carries no FOREIGN KEY (ADR-0016; see
        # _ensure_issue_milestone_fk_dropped for the rationale).
        conn.execute(
            "CREATE TABLE issues ("
            "github_id TEXT PRIMARY KEY, "
            "title TEXT NOT NULL, "
            "type_ TEXT, "
            "status TEXT, "
            "milestone_id TEXT" + assignee_column + ", "
            "created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP"
            ")"
        )
        conn.execute(
            "INSERT INTO issues "
            "(github_id, title, type_, status, milestone_id" + assignee_select + ", created_at) "
            "SELECT github_id, title, type_, status, CAST(milestone_id AS TEXT)"
            + assignee_select
            + ", created_at FROM issues_pre_text_milestone"
        )
        conn.execute("DROP TABLE issues_pre_text_milestone")

    @staticmethod
    def _ensure_issue_milestone_fk_dropped(conn: sqlite3.Connection) -> None:
        """Rebuild a pre-ADR-0016 issues table to drop the milestone FOREIGN KEY.

        The FK targeted ``milestones (id)``, the integer rowid, but with
        backend-invariant record ids (F7) an issue's milestone_id carries the
        minted milestone record id, which that FK rejects on every write. The
        SurrealDB primary never enforced the constraint, so parity and the F7
        contract both call for dropping it; the milestone linkage is soft by
        design (the graph ``contains`` edge is the authoritative link).

        SQLite cannot drop a constraint in place, so the migration rebuilds the
        table exactly like :meth:`_ensure_issue_milestone_id_is_text`: rename
        aside, recreate without the FK (preserving the current column set),
        copy every row unchanged, drop the renamed original. A fresh store's
        CREATE TABLE already omits the FK, so this is a no-op there.
        Concurrency-safe via the same losing-RENAME guard.
        """
        row = conn.execute(
            "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = 'issues'"
        ).fetchone()
        if row is None or "FOREIGN KEY" not in str(row["sql"]).upper():
            return  # no table yet, or the FK is already gone
        columns = {r["name"] for r in conn.execute("PRAGMA table_info(issues)")}
        has_assignee = "assignee" in columns
        try:
            conn.execute("ALTER TABLE issues RENAME TO issues_pre_fk_drop")
        except sqlite3.OperationalError as exc:
            if "already exists" not in str(exc).lower():
                raise
            return
        assignee_column = ", assignee TEXT" if has_assignee else ""
        assignee_select = ", assignee" if has_assignee else ""
        conn.execute(
            "CREATE TABLE issues ("
            "github_id TEXT PRIMARY KEY, "
            "title TEXT NOT NULL, "
            "type_ TEXT, "
            "status TEXT, "
            "milestone_id TEXT" + assignee_column + ", "
            "created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP"
            ")"
        )
        conn.execute(
            "INSERT INTO issues "
            "(github_id, title, type_, status, milestone_id" + assignee_select + ", created_at) "
            "SELECT github_id, title, type_, status, milestone_id"
            + assignee_select
            + ", created_at FROM issues_pre_fk_drop"
        )
        conn.execute("DROP TABLE issues_pre_fk_drop")

    # The minted-id tables on the SQLite fallback: each stores the client-minted
    # id in record_id, so an id means the same thing on both backends (F7).
    # memory, issues, and sessions are natural-keyed and need no minted column.
    _RECORD_ID_TABLES = (
        "decisions",
        "milestones",
        "backtest_runs",
        "handoffs",
        "releases",
        "loop_runs",
        "metrics",
        "transitions",
    )

    @classmethod
    def _ensure_record_id_columns(cls, conn: sqlite3.Connection) -> None:
        """Add record_id + its unique index to pre-migration tables (ADR-0016).

        Expand/contract like :meth:`_ensure_issue_assignee_column`: legacy rows
        keep a NULL record_id (the unique index tolerates NULLs), new writes
        stamp the minted id. SQLite's ALTER cannot add a UNIQUE column, so the
        column is plain and the uniqueness lives in a separate index. Table
        names come from the class constant, never caller input.
        """
        for table in cls._RECORD_ID_TABLES:
            cls._ensure_column(conn, table, "record_id", "TEXT")
            conn.execute(
                f"CREATE UNIQUE INDEX IF NOT EXISTS {table}_record_id "
                f"ON {table} (record_id)"
            )

    @staticmethod
    def _ensure_column(
        conn: sqlite3.Connection, table: str, column: str, decl: str
    ) -> None:
        """Add a nullable column to a pre-migration table (expand/contract).

        The generic form of :meth:`_ensure_issue_assignee_column` (#118), used
        by the ADR-0016 additive columns (sessions.status, handoffs.summary,
        record_id). Idempotent via the PRAGMA guard, and concurrency-safe on
        the shared store: the losing ALTER of two simultaneous first-opens
        raises ``duplicate column name``, which means a concurrent open already
        migrated, so it is swallowed; any other OperationalError propagates.
        ``table``, ``column`` and ``decl`` are internal constants, never caller
        input.
        """
        existing = {row["name"] for row in conn.execute(f"PRAGMA table_info({table})")}
        if not existing or column in existing:
            return
        try:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {decl}")
        except sqlite3.OperationalError as exc:
            if "duplicate column" not in str(exc).lower():
                raise

    @staticmethod
    def _ensure_issue_assignee_column(conn: sqlite3.Connection) -> None:
        """Add the nullable assignee column to a pre-migration issues table (#118).

        Expand/contract and idempotent: guarded by a PRAGMA table_info check, so a
        store created before the column gains it additively (no destructive rewrite
        of existing rows, which keep assignee NULL), while a fresh store whose
        CREATE TABLE already declared the column skips the ALTER.

        Concurrency-safe on the shared multi-agent store: two simultaneous
        first-opens can both pass the PRAGMA guard before either ALTERs, so the
        losing ALTER raises ``OperationalError: duplicate column name``. That means
        a concurrent open already added the column, so it is treated as
        already-migrated; any other OperationalError is a real failure and
        propagates.
        """
        existing = {row["name"] for row in conn.execute("PRAGMA table_info(issues)")}
        if "assignee" in existing:
            return
        try:
            conn.execute("ALTER TABLE issues ADD COLUMN assignee TEXT")
        except sqlite3.OperationalError as exc:
            if "duplicate column" not in str(exc).lower():
                raise

    def _resolve_sqlite_path(self) -> str:
        """Resolve the SQLite store path.

        HARNESS_DB_PATH redirects the store to a temp file for tests and ad-hoc
        runs so the real project memory is never touched (issue #24); otherwise it
        lands in the per-project memory dir. Shared by the constructor and the
        mid-session SQLite fallback so both resolve to the same file (issue #37).
        """
        env_db = os.environ.get("HARNESS_DB_PATH")
        if env_db:
            os.makedirs(os.path.dirname(os.path.abspath(env_db)), exist_ok=True)
            return env_db
        db_dir = os.path.join(self._project_root, "memory", "long_term")
        os.makedirs(db_dir, exist_ok=True)
        return os.path.join(db_dir, "harness.db")

    def _connect_surreal(self) -> bool:
        """(Re)build ``self.db`` and sign in, returning True on success.

        Used both at construction and to recover from a mid-session drop (#37).
        The attempt runs in a worker thread joined with ``self._connect_deadline``
        so a half-open socket can never block past the deadline -- the exact
        indefinite hang ("no close frame") that motivated this fix. A late-
        completing attempt only mutates a local dict, never ``self.db``.
        """
        Surreal = self._surreal_class
        if Surreal is None or not self._surreal_url:
            return False

        outcome: Dict[str, Any] = {}

        def _attempt() -> None:
            try:
                db = Surreal(self._surreal_url)
                if hasattr(db, "connect"):
                    db.connect()
                # SDK 2.x uses username/password keys (1.x used user/pass).
                db.signin(
                    {
                        "username": self._surreal_username,
                        "password": self._surreal_password,
                    }
                )
                db.use(self._surreal_namespace, self._surreal_database)
                outcome["db"] = db
            except Exception as exc:  # noqa: BLE001 - report, never raise from the worker
                outcome["error"] = exc

        worker = threading.Thread(target=_attempt, name="surreal-connect", daemon=True)
        worker.start()
        worker.join(self._connect_deadline)
        if worker.is_alive():
            sys.stderr.write(
                f"SurrealDB reconnect exceeded {self._connect_deadline}s deadline; "
                "abandoning the attempt.\n"
            )
            return False
        db = outcome.get("db")
        if db is None:
            return False
        self.db = db
        return True

    def _bootstrap_surreal_schema(self) -> None:
        """Execute every schema DDL statement, raising if any one fails.

        The surrealdb SDK's ``.query()`` only surfaces the FIRST statement's
        result of whatever string it is given (it checks ``response["result"][0]``
        only), so a single call with every DEFINE concatenated would silently
        accept a failure in a later statement (an index, a RELATION table, the
        HNSW vector index). Calling ``.query()`` once per statement makes each
        statement the first (and only) result of its own call, so a failing
        statement raises here and the constructor's caller can abort the
        SurrealDB bootstrap and fall back to SQLite instead of marking a
        partially-applied schema "ready".
        """
        for statement in self._SURREAL_SCHEMA_STATEMENTS:
            self.db.query(statement)

    @staticmethod
    def _is_connection_error(exc: Exception) -> bool:
        """True only for a transport/connection fault, never a query or data error.

        Classification is by exception TYPE first -- Python's own
        ``ConnectionError``/``OSError`` and the surrealdb SDK's
        websocket/connection exception classes -- because the type is the precise
        signal. The message fallback is deliberately narrow: it matches only
        anchored, multi-word transport phrases (the "no close frame" incident
        symptom, "connection reset", and the like), so a genuine query/data error
        that merely contains the word "connection" or "closed" in passing is NOT
        misread as a drop. Scoping the reconnect trigger this narrowly is the
        contract: a malformed query or a data error must surface unchanged and
        must not reconnect or fall back (issue #37).
        """
        if isinstance(exc, (ConnectionError, OSError)):
            return True
        if _SURREAL_CONNECTION_EXCEPTIONS and isinstance(
            exc, _SURREAL_CONNECTION_EXCEPTIONS
        ):
            return True
        message = str(exc).lower()
        # Anchored phrases only: each is a transport symptom that does not occur in
        # an ordinary query/data error message.
        markers = (
            "no close frame",
            "connection closed",
            "connection reset",
            "connection refused",
            "connection aborted",
            "connection lost",
            "websocket connection is closed",
            "websocket is closed",
            "transport closed",
            "transport is closed",
            "broken pipe",
            "not connected",
        )
        return any(marker in message for marker in markers)

    def _run_surreal(self, query: str, params: Optional[Dict[str, Any]] = None) -> Any:
        """Run a SurrealDB query, raising ``_ConnectionLost`` only on a transport
        fault so the resilient decorator can reconnect or fall back. A query or
        data error is re-raised unchanged for the caller's own handling (#37)."""
        if self.db is None:
            raise _ConnectionLost("no active SurrealDB connection")
        try:
            if params is None:
                return self.db.query(query)
            return self.db.query(query, params)
        except Exception as exc:  # noqa: BLE001 - classified, then re-raised
            if self._is_connection_error(exc):
                raise _ConnectionLost(str(exc)) from exc
            raise

    def _activate_sqlite_fallback(self) -> None:
        """Switch to the SQLite backend after a reconnect could not be made.

        This is the last resort so a mid-session drop never loses a write: the
        client keeps serving from the local SQLite store. The switch is announced
        loudly on stderr because it creates a SurrealDB/SQLite divergence that
        must be reconciled on recovery (the durable cure is issue #35). Idempotent:
        re-initializing SQLite uses CREATE TABLE IF NOT EXISTS.
        """
        sys.stderr.write(
            "WARNING: SurrealDB connection lost and the single reconnect failed; "
            "falling back to the local SQLite store. Memory written from now on will "
            "diverge from SurrealDB until reconcile runs.\n"
        )
        if self.db is not None:
            try:
                self.db.close()
            except Exception:
                pass
            self.db = None
        self.backend = "sqlite"
        self._fallback_reason = (
            "SurrealDB connection lost mid-session; reconnect failed"
        )
        if self.db_path is None:
            self.db_path = self._resolve_sqlite_path()
        self._init_sqlite_db()

    @staticmethod
    def _normalize(record: Dict[str, Any]) -> Dict[str, Any]:
        """Make a SurrealDB record JSON-serializable.

        SurrealDB returns RecordID objects for ids and datetime objects for
        time::now() fields; both must become strings so callers (and the MCP
        server) can json.dumps the result.
        """
        out = {}
        for k, v in record.items():
            if type(v).__name__ == "RecordID":
                out[k] = str(v)
            elif hasattr(v, "isoformat"):  # datetime / date
                out[k] = v.isoformat()
            else:
                out[k] = v
        return out

    def _extract_list(self, res: Any) -> List[Dict[str, Any]]:
        """Return the record dicts from a SurrealDB query result.

        SDK 2.x returns ``query()`` results as a flat ``list[dict]``; this also
        tolerates the legacy ``[{"result": [...]}]`` and ``[[...]]`` shapes.
        """
        if not res:
            return []
        rows = res
        if isinstance(rows, list) and rows:
            head = rows[0]
            if isinstance(head, dict) and isinstance(head.get("result"), list):
                rows = head["result"]
            elif isinstance(head, list):
                rows = head
        return [self._normalize(r) for r in rows if isinstance(r, dict)]

    def _extract_record(self, res: Any) -> Optional[Dict[str, Any]]:
        """Extract the first record dictionary from a SurrealDB query result."""
        rows = self._extract_list(res)
        return rows[0] if rows else None

    def _extract_field(self, res: Any, field_name: str) -> Any:
        """Extract a single field from the first record of a query result."""
        rec = self._extract_record(res)
        return rec.get(field_name) if rec else None

    def _extract_id(self, res: Any) -> Optional[str]:
        """Extract the (stringified) record id from a query result."""
        rec = self._extract_record(res)
        if rec and rec.get("id") is not None:
            return str(rec["id"])
        return None

    @staticmethod
    def _rid(table: str, key: Union[str, int]) -> Any:
        """Build a SurrealDB RecordID for ``table:key`` (deterministic upsert id)."""
        from surrealdb import RecordID

        return RecordID(table, str(key))

    @staticmethod
    def _parse_rid(id_value: Union[str, int, None]) -> Any:
        """Turn a 'table:id' string (or RecordID) into a RecordID for querying.

        SurrealDB v3.x renders a complex record key wrapped in display delimiters
        (angle brackets ``decisions:⟨abc-123⟩`` or backticks); these are not part
        of the binary key, so they are stripped before the RecordID is rebuilt.
        Without this, a get-by-id of a minted complex key never matches the stored
        record and silently returns None.
        """
        if id_value is None:
            return None
        if type(id_value).__name__ == "RecordID":
            return id_value
        s = str(id_value)
        if ":" in s:
            from surrealdb import RecordID

            table, _, rid = s.partition(":")
            rid = rid.strip()
            if len(rid) >= 2 and rid[0] == "⟨" and rid[-1] == "⟩":
                rid = rid[1:-1]
            elif len(rid) >= 2 and rid[0] == "`" and rid[-1] == "`":
                rid = rid[1:-1]
            return RecordID(table, rid)
        return s

    # ----------------------------------------------------------------------
    # Write-through Markdown mirror + reconcile-on-recovery (issue #35).
    #
    # Every write also lands in a human-readable Markdown file under
    # ``.solomon/memory-mirror/<kind>/<id>.md`` so a mid-session backend outage
    # never silently drops an audit-trail record: a write that only reaches the
    # SQLite fallback is stamped ``synced: false`` and replayed to the SurrealDB
    # primary on recovery via :meth:`reconcile`. The id is client-minted and used
    # as both the mirror filename and the SurrealDB RecordID, so a replay is a
    # deterministic UPSERT that never duplicates an already-present record.
    # ----------------------------------------------------------------------

    _KIND_TABLE = {
        "decision": "decisions",
        "memory": "memory",
        "issue": "issues",
        "milestone": "milestones",
        "release": "releases",
        "backtest": "backtest_runs",
        "session": "sessions",
        "handoff": "handoffs",
        "loop_run": "loop_runs",
    }
    _KIND_TIMEFIELD = {
        "decision": "created_at",
        "memory": "updated_at",
        "issue": "created_at",
        "milestone": "created_at",
        "release": "released_at",
        "backtest": "created_at",
        "session": "timestamp",
        "handoff": "timestamp",
        "loop_run": "created_at",
    }
    # Per-kind (field, normalizer) applied when a mirror record is replayed, so
    # a legacy pending mirror carrying a pre-vocabulary token (pending, failure,
    # active) is normalized like any other write and can never trip the typed-
    # state ASSERTs (ADR-0016). Functions held inside a dict are plain values,
    # not descriptors, so they never bind as methods.
    _KIND_STATUS_NORMALIZER: Dict[str, tuple] = {
        "issue": ("status", normalize_status),
        "handoff": ("status", normalize_handoff_status),
        "session": ("status", normalize_session_status),
        "loop_run": ("status", normalize_loop_run_status),
        "milestone": ("state", normalize_milestone_state),
    }

    def _resolve_mirror_root(self, override: Optional[str]) -> str:
        """Resolve the write-through mirror root.

        An explicit ``mirror_root`` (or ``HARNESS_MIRROR_ROOT``) wins. When the
        SQLite store is redirected to a temp file for a test or sandbox (an
        explicit ``db_path`` or ``HARNESS_DB_PATH``), the mirror lives beside it so
        a test never touches the real project's ``.solomon/`` -- the same isolation
        convention :meth:`_resolve_sqlite_path` uses for the DB. Otherwise it is the
        gitignored ``.solomon/memory-mirror`` at the repository root.

        Delegates to the module-level :func:`_resolve_mirror_root_path` so the
        healthcheck resolves the very same root and can never count pending records
        in a different directory than the one writes land in.
        """
        return _resolve_mirror_root_path(
            self._project_root, db_path=self._db_path_param, override=override
        )

    @staticmethod
    def _utc_iso() -> str:
        """Current UTC time as an ISO-8601 string (the mirror ``created_at``)."""
        return datetime.datetime.now(datetime.timezone.utc).isoformat()

    def _mint_id(self, kind: str) -> str:
        """A client-minted stable id ``<kind>-<utc>-<short-uuid>``.

        Used as the mirror filename and the SurrealDB RecordID so a replay is a
        deterministic UPSERT. Minted once per logical write, never inside the
        resilient DB retry, so a reconnect/fallback re-run never re-mints it.
        """
        stamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        return f"{kind}-{stamp}-{uuid.uuid4().hex[:8]}"

    @staticmethod
    def _safe_name(record_id: str) -> str:
        """A filesystem-safe mirror filename for an id.

        Minted ids are already safe and pass through unchanged. A natural-key id
        (memory key, github_id, session_id) may carry path-unsafe characters, so it
        is slugified and disambiguated with a short content hash to avoid two
        distinct keys colliding onto one file. The authoritative id stays in the
        frontmatter regardless of the filename.
        """
        rid = str(record_id)
        safe = re.sub(r"[^A-Za-z0-9._-]", "_", rid)
        if safe == rid:
            return safe
        digest = hashlib.sha1(rid.encode("utf-8")).hexdigest()[:8]
        return f"{safe}-{digest}"

    @staticmethod
    def _render_mirror(
        record_id: str, kind: str, created_at: str, synced: bool, fields: Dict[str, Any]
    ) -> str:
        """Render a mirror file: YAML-ish frontmatter plus a readable JSON body."""
        payload = json.dumps(fields, indent=2, sort_keys=True, default=str)
        # JSON-encode the id so a natural-key id carrying a newline or control
        # character cannot break out of its single frontmatter line and inject
        # extra keys (which would corrupt the parsed id on replay). The quoted form
        # round-trips losslessly through _parse_mirror (issue #35).
        lines = [
            "---",
            f"id: {json.dumps(str(record_id))}",
            f"kind: {kind}",
            f"created_at: {created_at}",
            f"synced: {'true' if synced else 'false'}",
            "---",
            "",
            f"# {kind} record",
            "",
            "```json",
            payload,
            "```",
            "",
        ]
        return "\n".join(lines)

    @staticmethod
    def _parse_mirror(text: str) -> tuple:
        """Parse a mirror file into ``(meta, payload)``.

        ``meta`` carries ``id``, ``kind``, ``created_at`` and a coerced boolean
        ``synced``; ``payload`` is the JSON body (the original write fields).
        """
        parts = text.split("---", 2)
        if len(parts) < 3:
            raise ValueError("mirror file has no frontmatter")
        meta: Dict[str, Any] = {}
        for line in parts[1].strip().splitlines():
            if ":" in line:
                key, _, value = line.partition(":")
                value = value.strip()
                # A JSON-quoted value (e.g. an encoded id) is decoded back to its
                # exact original; plain values pass through unchanged so older
                # mirror files stay readable.
                if value.startswith('"'):
                    try:
                        value = json.loads(value)
                    except (json.JSONDecodeError, ValueError):
                        pass
                meta[key.strip()] = value
        meta["synced"] = str(meta.get("synced", "true")).lower() == "true"
        body = parts[2]
        payload: Dict[str, Any] = {}
        start = body.find("```json")
        if start != -1:
            end = body.find("```", start + len("```json"))
            if end != -1:
                payload = json.loads(body[start + len("```json") : end])
        return meta, payload

    def _mirror_write(
        self,
        kind: str,
        record_id: str,
        fields: Dict[str, Any],
        synced: bool,
        created_at: Optional[str] = None,
    ) -> str:
        """Write (or re-stamp) the Markdown mirror for one record.

        A mirror-write failure is the durability guarantee failing, so it is loud:
        it raises rather than being swallowed by the DB-down success path (#35).
        """
        if created_at is None:
            created_at = self._utc_iso()
        directory = os.path.join(self._mirror_root, kind)
        path = os.path.join(directory, self._safe_name(record_id) + ".md")
        content = self._render_mirror(record_id, kind, created_at, synced, fields)
        try:
            os.makedirs(directory, exist_ok=True)
            with open(path, "w", encoding="utf-8") as handle:
                handle.write(content)
        except OSError as exc:
            raise RuntimeError(f"memory mirror write failed at {path}: {exc}") from exc
        return path

    def _is_synced(self) -> bool:
        """Whether the just-attempted write reached the SurrealDB primary.

        With no SurrealDB primary configured the local SQLite store is the only
        source of truth, so the record is synced by definition and nothing needs
        reconciling. Otherwise a write is synced only while the client is still on
        SurrealDB; if a drop forced ``_activate_sqlite_fallback`` (or the primary
        was already unavailable) the client is on SQLite and the record is pending.
        """
        if self._surreal_class is None:
            return True
        return self.backend == "surrealdb"

    def _write_through(self, kind, record_id, fields, db_op):
        """Durability funnel shared by every write method (issue #35).

        Mints the mirror once, OUTSIDE the resilient DB attempt, so a
        reconnect/fallback re-run never double-writes it. The mirror is stamped
        ``synced: false`` first; after the DB attempt it is re-stamped via
        :meth:`_is_synced`. ``db_op`` is the per-kind ``@_resilient`` DB writer; it
        never raises solely because the backend is down (it falls back to SQLite),
        so the write is durable even during an outage.
        """
        # Skip mirroring for internal database index and project structure files
        # to prevent repository bloat.
        if kind == "memory" and fields.get("category") in ("codebase_index", "index", "project_model", "project_evolution"):
            return db_op(record_id, fields)

        created_at = self._utc_iso()
        self._mirror_write(kind, record_id, fields, synced=False, created_at=created_at)
        result = db_op(record_id, fields)
        self._mirror_write(
            kind, record_id, fields, synced=self._is_synced(), created_at=created_at
        )
        return result

    def _pending_mirror_files(self) -> List[tuple]:
        """All mirror files still marked ``synced: false``, as ``(path, meta, payload)``."""
        out: List[tuple] = []
        if not os.path.isdir(self._mirror_root):
            return out
        for path in sorted(glob.glob(os.path.join(self._mirror_root, "*", "*.md"))):
            try:
                with open(path, "r", encoding="utf-8") as handle:
                    meta, payload = self._parse_mirror(handle.read())
            except (OSError, ValueError, json.JSONDecodeError):
                continue
            if not meta.get("synced", True):
                out.append((path, meta, payload))
        return out

    def _replay(self, meta: Dict[str, Any], payload: Dict[str, Any]) -> None:
        """Idempotently replay a mirrored record into the SurrealDB primary.

        A regular record is UPSERTed; a deletion tombstone (payload marked
        ``deleted``) is replayed as a DELETE so a removed record never comes back.
        The UPSERT is keyed by the record's stored id, so replaying a record that
        is already present updates it in place rather than duplicating it. The
        original mirror ``created_at`` is preserved as the record's time field so a
        replayed row sorts where it belongs. Raises ``_ConnectionLost`` on a
        transport fault so :meth:`reconcile` can stop and leave the rest pending.
        """
        kind = meta["kind"]
        if kind == "edge":
            # An edge replays as an idempotent RELATE: the minted id is stamped
            # on the edge as record_id, so the check-before-create can tell an
            # already-replayed edge from a missing one (RELATE itself has no
            # client-keyed UPSERT form) (ADR-0016, F5).
            edge = self._safe_ident(payload["edge"], "edge name")
            rid = payload.get("record_id") or meta["id"]
            existing = self._run_surreal(
                f"SELECT record_id FROM {edge} WHERE record_id = $record_id LIMIT 1;",
                {"record_id": rid},
            )
            if self._extract_record(existing) is None:
                query, params = self._relate_statement(payload, rid)
                self._run_surreal(query, params)
            return
        if kind == "metric":
            # A metric replays keyed by its minted id, carrying its ORIGINAL
            # time coerced to a native datetime -- the metrics time field is
            # what time::group buckets on, so it must never become a string.
            content = dict(payload)
            content["time"] = self._coerce_dt(payload.get("time") or meta.get("created_at"))
            self._run_surreal(
                "UPSERT $id CONTENT $content;",
                {"id": self._rid("metrics", meta["id"]), "content": content},
            )
            return
        table = self._KIND_TABLE[kind]
        if payload.get("deleted"):
            # A deletion tombstone (a mutation like delete_memory that ran while
            # the primary was down) replays as a DELETE keyed by the stored id --
            # never an UPSERT, which would resurrect the deleted record. Deleting
            # an absent record is a no-op, so the replay stays idempotent.
            self._run_surreal("DELETE $id;", {"id": self._rid(table, meta["id"])})
            return
        content = dict(payload)
        content[self._KIND_TIMEFIELD.get(kind, "created_at")] = meta.get("created_at")
        # Replay is a write seam like any other: normalize the kind's status
        # field so a legacy pending mirror cannot trip the typed-state ASSERTs
        # (ADR-0016).
        normalizer_entry = self._KIND_STATUS_NORMALIZER.get(kind)
        if normalizer_entry is not None:
            field, normalizer = normalizer_entry
            if field in content:
                content[field] = normalizer(content[field])
        self._run_surreal(
            "UPSERT $id CONTENT $content;",
            {"id": self._rid(table, meta["id"]), "content": content},
        )

    def reconcile(self) -> Dict[str, int]:
        """Replay pending mirror records to the SurrealDB primary (issue #35).

        Recovers a primary connection via :meth:`_connect_surreal` when the client
        is not currently on SurrealDB. Each ``synced: false`` record is replayed as
        a deterministic UPSERT by its stored id (idempotent: a second run is a
        no-op and never duplicates), then its mirror is flipped to ``synced: true``.
        A mid-run connection drop is tolerated: replay stops and every remaining
        record stays pending for a later run. Never raises.

        Returns a ``{"synced", "remaining"}`` count.
        """
        pending = self._pending_mirror_files()
        if not pending:
            return {"synced": 0, "remaining": 0}
        # A SurrealDB primary is required to reconcile against. With none configured
        # the local SQLite store is already authoritative, so there is nothing to
        # push and the records are reported as remaining (not an error).
        if self._surreal_class is None:
            return {"synced": 0, "remaining": len(pending)}
        if self.backend != "surrealdb" or self.db is None:
            if self._connect_surreal():
                self.backend = "surrealdb"
                self._fallback_reason = None
            else:
                return {"synced": 0, "remaining": len(pending)}

        synced = 0
        remaining = 0
        dropped = False
        for path, meta, payload in pending:
            if dropped:
                remaining += 1
                continue
            try:
                self._replay(meta, payload)
            except _ConnectionLost:
                # A mid-run drop leaves this and every later record pending.
                dropped = True
                remaining += 1
                continue
            except Exception as exc:  # noqa: BLE001 - one bad record must not block the rest
                logging.error(f"Failed to reconcile {path}: {exc}")
                remaining += 1
                continue
            self._mirror_write(
                meta["kind"], meta["id"], payload, synced=True, created_at=meta.get("created_at")
            )
            synced += 1
        return {"synced": synced, "remaining": remaining}

    def log_decision(
        self,
        title: str,
        rationale: str,
        outcome: str,
        author: str,
        branch: str,
        commit_sha: str,
    ) -> Union[str, int, None]:
        """Logs an architectural or design decision to the database.

        Args:
            title: The title of the decision.
            rationale: Explanation and options considered.
            outcome: Chosen course of action.
            author: Person or role logging the decision.
            branch: Current Git branch name.
            commit_sha: Commit SHA representing the change.

        Returns:
            The primary key ID or record ID of the inserted record.
        """
        fields = {
            "title": title,
            "rationale": rationale,
            "outcome": outcome,
            "author": author,
            "branch": branch,
            "commit_sha": commit_sha,
        }
        return self._write_through(
            "decision", self._mint_id("decision"), fields, self._db_log_decision
        )

    @_resilient
    def _db_log_decision(
        self, record_id: str, fields: Dict[str, Any]
    ) -> Union[str, int, None]:
        """Persist a decision: client-minted id, idempotent UPSERT on SurrealDB."""
        if self.backend == "surrealdb":
            query = """
            UPSERT $id CONTENT {
                title: $title,
                rationale: $rationale,
                outcome: $outcome,
                author: $author,
                branch: $branch,
                commit_sha: $commit_sha,
                created_at: time::now()
            };
            """
            params = {"id": self._rid("decisions", record_id), **fields}
            try:
                res = self._run_surreal(query, params)
                return self._extract_id(res)
            except _ConnectionLost:
                raise
            except Exception as e:
                logging.error(f"Failed to log decision in SurrealDB: {e}")
                raise RuntimeError(f"Failed to log decision in SurrealDB: {e}")
        else:
            query = """
            INSERT INTO decisions
                (record_id, title, rationale, outcome, author, branch, commit_sha)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """
            try:
                with self._sqlite_conn() as conn:
                    conn.execute(
                        query,
                        (
                            record_id,
                            fields["title"],
                            fields["rationale"],
                            fields["outcome"],
                            fields["author"],
                            fields["branch"],
                            fields["commit_sha"],
                        ),
                    )
                    conn.commit()
                    # The minted id, never lastrowid: backend-invariant (F7).
                    return record_id
            except sqlite3.Error as e:
                logging.error(f"Failed to log decision: {e}")
                raise RuntimeError(f"Failed to log decision: {e}")

    def save_memory(self, key: str, value: str, category: str) -> None:
        """Upserts a key-value memory entry.

        Args:
            key: Unique key identifying the memory.
            value: Value of the memory entry.
            category: Categorical bucket for the memory.
        """
        fields = {"key": key, "value": value, "category": category}
        # The natural key is already a stable id, so it is reused for the RecordID
        # and the mirror filename (re-saving the same key updates in place).
        self._write_through("memory", key, fields, self._db_save_memory)

    @_resilient
    def _db_save_memory(self, record_id: str, fields: Dict[str, Any]) -> None:
        """Persist a memory entry: idempotent UPSERT keyed by the memory key."""
        key = fields["key"]
        value = fields["value"]
        category = fields["category"]
        if self.backend == "surrealdb":
            if self.spectron is not None:
                try:
                    self.spectron.remember(fact=value, scope=[category, key])
                except Exception as e:
                    logging.warning(f"Failed to save memory in Spectron: {e}")

            # Upsert by a deterministic record id derived from the key, so
            # re-saving the same key updates in place. The embedding is computed
            # here (not stored in the durability mirror) so the vector index stays
            # additive: existing get_memory reads and the mirror format are
            # unchanged, and a record without an embedding is simply not indexed.
            # Non-semantic categories (the code index, the board history) skip
            # the embedding entirely -- the field is omitted, so the HNSW index
            # never sees the row (ADR-0016, F6). A re-save that changes category
            # replaces the whole CONTENT, so a stale embedding falls out then.
            params = {
                "id": self._rid("memory", record_id),
                "key": key,
                "value": value,
                "category": category,
            }
            if is_semantic_category(category):
                embedding_field = "embedding: $embedding,\n                "
                params["embedding"] = self._embedder.embed(f"{key} {value}")
            else:
                embedding_field = ""
            query = f"""
            UPSERT $id CONTENT {{
                key: $key,
                value: $value,
                category: $category,
                {embedding_field}updated_at: time::now()
            }};
            """
            try:
                self._run_surreal(query, params)
            except _ConnectionLost:
                raise
            except Exception as e:
                logging.error(f"Failed to save memory in SurrealDB: {e}")
                raise RuntimeError(f"Failed to save memory in SurrealDB: {e}")
        else:
            query = """
            INSERT INTO memory (key, value, category, updated_at)
            VALUES (?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(key) DO UPDATE SET
                value=excluded.value,
                category=excluded.category,
                updated_at=CURRENT_TIMESTAMP
            """
            try:
                with self._sqlite_conn() as conn:
                    conn.execute(query, (key, value, category))
                    conn.commit()
            except sqlite3.Error as e:
                logging.error(f"Failed to save memory: {e}")
                raise RuntimeError(f"Failed to save memory: {e}")

    def delete_memory(self, key: str) -> None:
        """Deletes a memory entry by key (no-op if it does not exist).

        The deletion goes through the same write-through funnel as every other
        mutation: the key's mirror file is overwritten with a deletion tombstone
        (same key-derived filename, so it replaces any pending save for the key)
        before the DB delete runs. A reconcile after an outage therefore replays
        the DELETE instead of resurrecting the row from a stale pending save.
        """
        self._write_through(
            "memory", key, {"key": key, "deleted": True}, self._db_delete_memory
        )

    @_resilient
    def _db_delete_memory(self, record_id: str, fields: Dict[str, Any]) -> None:
        """Delete a memory entry; a connection loss falls back like every write."""
        key = fields["key"]
        if self.backend == "surrealdb":
            try:
                self._run_surreal("DELETE memory WHERE key = $key;", {"key": key})
            except _ConnectionLost:
                raise
            except Exception as e:
                logging.error(f"Failed to delete memory in SurrealDB: {e}")
        else:
            try:
                with self._sqlite_conn() as conn:
                    conn.execute("DELETE FROM memory WHERE key = ?", (key,))
                    conn.commit()
            except sqlite3.Error as e:
                logging.error(f"Failed to delete memory: {e}")

    @_resilient
    def get_memory(self, key: str) -> Optional[str]:
        """Retrieves a memory value by its key.

        Args:
            key: The unique memory key.

        Returns:
            The memory value string or None if not found.
        """
        if self.backend == "surrealdb":
            if self.spectron is not None:
                try:
                    res = self.spectron.recall(key)
                    if res and hasattr(res, "hits") and res.hits:
                        return res.hits[0].text
                except Exception as e:
                    logging.warning(f"Failed to recall memory from Spectron: {e}")

            query = "SELECT `value` FROM memory WHERE key = $key"
            try:
                res = self._run_surreal(query, {"key": key})
                return self._extract_field(res, "value")
            except _ConnectionLost:
                raise
            except Exception as e:
                logging.error(f"Failed to retrieve memory from SurrealDB: {e}")
                raise RuntimeError(f"Failed to retrieve memory from SurrealDB: {e}")
        else:
            query = "SELECT value FROM memory WHERE key = ?"
            try:
                with self._sqlite_conn() as conn:
                    cursor = conn.cursor()
                    cursor.execute(query, (key,))
                    row = cursor.fetchone()
                    return row["value"] if row else None
            except sqlite3.Error as e:
                logging.error(f"Failed to retrieve memory: {e}")
                raise RuntimeError(f"Failed to retrieve memory: {e}")

    @_resilient
    def get_memory_bulk(self, keys: Sequence[str]) -> Dict[str, str]:
        """Retrieves several memory values in one round trip, keyed by key.

        Exists so a caller that needs N memory entries (e.g. one board_history
        per issue) issues exactly one query instead of N (the N+1 pattern).
        Returns a dict containing only the keys that resolved to a value; a key
        with no stored entry is simply absent, the same "miss" a single
        ``get_memory`` call reports as None. An empty ``keys`` sequence is a
        no-op that skips the query entirely.
        """
        keys = list(keys)
        if not keys:
            return {}
        if self.backend == "surrealdb":
            query = "SELECT key, `value` FROM memory WHERE key IN $keys"
            try:
                res = self._run_surreal(query, {"keys": keys})
                return {
                    row["key"]: row["value"]
                    for row in self._extract_list(res)
                    if "key" in row
                }
            except _ConnectionLost:
                raise
            except Exception as e:
                logging.error(f"Failed to bulk retrieve memory from SurrealDB: {e}")
                raise RuntimeError(f"Failed to bulk retrieve memory from SurrealDB: {e}")
        else:
            placeholders = ",".join("?" for _ in keys)
            query = f"SELECT key, value FROM memory WHERE key IN ({placeholders})"
            try:
                with self._sqlite_conn() as conn:
                    cursor = conn.cursor()
                    cursor.execute(query, keys)
                    return {row["key"]: row["value"] for row in cursor.fetchall()}
            except sqlite3.Error as e:
                logging.error(f"Failed to bulk retrieve memory: {e}")
                raise RuntimeError(f"Failed to bulk retrieve memory: {e}")

    def create_milestone(
        self, title: str, description: str, due_date: str, state: str
    ) -> Union[str, int, None]:
        """Creates a project milestone record.

        Args:
            title: Milestone title.
            description: Detailed objective list.
            due_date: Target completion date.
            state: Lifecycle state, normalized to the canonical vocabulary
                (open or closed) at this write seam (ADR-0016); legacy
                spellings (active, complete, pending) collapse to it.

        Returns:
            The primary key ID or record ID of the created milestone.
        """
        fields = {
            "title": title,
            "description": description,
            "due_date": due_date,
            "state": normalize_milestone_state(state),
        }
        return self._write_through(
            "milestone", self._mint_id("milestone"), fields, self._db_create_milestone
        )

    @_resilient
    def _db_create_milestone(
        self, record_id: str, fields: Dict[str, Any]
    ) -> Union[str, int, None]:
        """Persist a milestone: client-minted id, idempotent UPSERT on SurrealDB."""
        if self.backend == "surrealdb":
            query = """
            UPSERT $id CONTENT {
                title: $title,
                description: $description,
                due_date: $due_date,
                state: $state,
                created_at: time::now()
            };
            """
            params = {"id": self._rid("milestones", record_id), **fields}
            try:
                res = self._run_surreal(query, params)
                return self._extract_id(res)
            except _ConnectionLost:
                raise
            except Exception as e:
                logging.error(f"Failed to create milestone in SurrealDB: {e}")
                raise RuntimeError(f"Failed to create milestone in SurrealDB: {e}")
        else:
            query = """
            INSERT INTO milestones (record_id, title, description, due_date, state)
            VALUES (?, ?, ?, ?, ?)
            """
            try:
                with self._sqlite_conn() as conn:
                    conn.execute(
                        query,
                        (
                            record_id,
                            fields["title"],
                            fields["description"],
                            fields["due_date"],
                            fields["state"],
                        ),
                    )
                    conn.commit()
                    return record_id
            except sqlite3.Error as e:
                logging.error(f"Failed to create milestone: {e}")
                raise RuntimeError(f"Failed to create milestone: {e}")

    @_resilient
    def list_milestones(self) -> List[Dict[str, Any]]:
        """List milestones, most recent first."""
        if self.backend == "surrealdb":
            try:
                res = self._run_surreal("SELECT * FROM milestones ORDER BY created_at DESC")
                return self._extract_list(res)
            except _ConnectionLost:
                raise
            except Exception as e:
                logging.error(f"Failed to list milestones from SurrealDB: {e}")
                raise RuntimeError(f"Failed to list milestones from SurrealDB: {e}")
        else:
            try:
                with self._sqlite_conn() as conn:
                    cursor = conn.cursor()
                    cursor.execute(
                        "SELECT * FROM milestones ORDER BY created_at DESC, id DESC"
                    )
                    return [dict(row) for row in cursor.fetchall()]
            except sqlite3.Error as e:
                logging.error(f"Failed to list milestones: {e}")
                raise RuntimeError(f"Failed to list milestones: {e}")

    @_resilient
    def get_milestone_by_title(self, title: str) -> Optional[Dict[str, Any]]:
        """Return the most recent milestone row with this exact title, or None."""
        if self.backend == "surrealdb":
            try:
                res = self._run_surreal(
                    "SELECT * FROM milestones WHERE title = $t ORDER BY created_at DESC LIMIT 1",
                    {"t": title},
                )
                rows = self._extract_list(res)
                return rows[0] if rows else None
            except _ConnectionLost:
                raise
            except Exception as e:
                logging.error(f"Failed to look up milestone by title in SurrealDB: {e}")
                raise RuntimeError(f"Failed to look up milestone by title in SurrealDB: {e}")
        else:
            try:
                with self._sqlite_conn() as conn:
                    cursor = conn.cursor()
                    cursor.execute(
                        "SELECT * FROM milestones WHERE title = ? "
                        "ORDER BY created_at DESC, id DESC LIMIT 1",
                        (title,),
                    )
                    row = cursor.fetchone()
                    return dict(row) if row else None
            except sqlite3.Error as e:
                logging.error(f"Failed to look up milestone by title: {e}")
                raise RuntimeError(f"Failed to look up milestone by title: {e}")

    def ensure_milestone(
        self, title: str, description: str = "", due_date: str = ""
    ) -> Union[str, int, None]:
        """Return the id of the milestone with this title, creating it (open) if new.

        Idempotent by title: a second refine of an issue under the same epic does
        not create a duplicate memory milestone row (issue #176, AC1).
        """
        existing = self.get_milestone_by_title(title)
        if existing:
            return existing.get("record_id") or existing.get("id")
        return self.create_milestone(title, description, due_date, "open")

    def close_milestone(self, title: str) -> Union[str, int, None]:
        """Write the milestone's state through to closed (terminal), idempotent.

        Finds the existing row by title and re-writes it closed; if none exists
        yet, records it closed. Re-running never creates a duplicate (#176, AC2).
        """
        existing = self.get_milestone_by_title(title)
        if not existing:
            return self.create_milestone(title, "", "", "closed")
        record_id = existing.get("record_id") or self._record_key(
            existing.get("id"), existing.get("id")
        )
        fields = {
            "title": existing.get("title") or title,
            "description": existing.get("description") or "",
            "due_date": existing.get("due_date") or "",
            "state": "closed",
        }
        return self._write_through(
            "milestone", str(record_id), fields, self._db_set_milestone_state
        )

    @_resilient
    def delete_milestone_by_title(self, title: str) -> int:
        """Delete every milestone row with this title. Returns the number removed.

        Used by the one-shot milestone reconcile to prune junk rows ("Sprint 1",
        "M1", "m") that never corresponded to a real GitHub milestone (#176).
        """
        if self.backend == "surrealdb":
            try:
                self._run_surreal("DELETE milestones WHERE title = $t", {"t": title})
                return 1
            except _ConnectionLost:
                raise
            except Exception as e:
                logging.error(f"Failed to delete milestone in SurrealDB: {e}")
                raise RuntimeError(f"Failed to delete milestone in SurrealDB: {e}")
        else:
            try:
                with self._sqlite_conn() as conn:
                    cursor = conn.execute("DELETE FROM milestones WHERE title = ?", (title,))
                    conn.commit()
                    return cursor.rowcount
            except sqlite3.Error as e:
                logging.error(f"Failed to delete milestone: {e}")
                raise RuntimeError(f"Failed to delete milestone: {e}")

    @_resilient
    def _db_set_milestone_state(
        self, record_id: str, fields: Dict[str, Any]
    ) -> Union[str, int, None]:
        """Rewrite an existing milestone with a new state; UPSERT (Surreal), UPDATE (SQLite)."""
        if self.backend == "surrealdb":
            query = """
            UPSERT $id CONTENT {
                title: $title,
                description: $description,
                due_date: $due_date,
                state: $state,
                created_at: time::now()
            };
            """
            params = {"id": self._rid("milestones", record_id), **fields}
            try:
                res = self._run_surreal(query, params)
                return self._extract_id(res)
            except _ConnectionLost:
                raise
            except Exception as e:
                logging.error(f"Failed to update milestone state in SurrealDB: {e}")
                raise RuntimeError(f"Failed to update milestone state in SurrealDB: {e}")
        else:
            try:
                with self._sqlite_conn() as conn:
                    conn.execute(
                        "UPDATE milestones SET state = ? WHERE record_id = ? OR id = ?",
                        (fields["state"], record_id, record_id),
                    )
                    conn.commit()
                    return record_id
            except sqlite3.Error as e:
                logging.error(f"Failed to update milestone state: {e}")
                raise RuntimeError(f"Failed to update milestone state: {e}")

    def save_release(
        self,
        version: str,
        tag: Optional[str] = None,
        notes: Optional[str] = None,
        issue_github_id: Optional[str] = None,
        milestone_id: Optional[Union[str, int]] = None,
        commit_sha: Optional[str] = None,
    ) -> Union[str, int, None]:
        """Record a delivered release in the project memory.

        Args:
            version: Semantic version of the release (e.g. v1.2.0).
            tag: Git tag for the release.
            notes: Changelog or release notes.
            issue_github_id: The delivered issue this release closes, if any.
            milestone_id: Associated milestone id, if any.
            commit_sha: The merge/release commit SHA.

        Returns:
            The id of the created release record.
        """
        mid = str(milestone_id) if milestone_id is not None else None
        fields = {
            "version": version,
            "tag": tag,
            "notes": notes,
            "issue_github_id": issue_github_id,
            "milestone_id": mid,
            "commit_sha": commit_sha,
        }
        release_id = self._write_through(
            "release", self._mint_id("release"), fields, self._db_save_release
        )
        try:
            import json as _json
            import datetime
            from solomon_harness.bootstrap import scan_project_structure

            # Fetch issue details if issue_github_id is provided
            issue_title = ""
            if issue_github_id:
                issue_row = self.get_issue(issue_github_id)
                if issue_row:
                    issue_title = issue_row.get("title", "")

            # Format the evolution entry
            evolution_entry = {
                "issue_number": issue_github_id or "",
                "issue_title": issue_title,
                "version": version,
                "date": datetime.date.today().isoformat()
            }

            # Retrieve existing evolution log
            existing_evo_raw = self.get_memory("__project_evolution__")
            evolution_list = []
            if existing_evo_raw:
                try:
                    evolution_list = _json.loads(existing_evo_raw)
                except Exception:
                    evolution_list = []

            # Append and save
            evolution_list.append(evolution_entry)
            self.save_memory(key="__project_evolution__", value=_json.dumps(evolution_list), category="project_evolution")

            # Refresh structure
            scan_project_structure(self._project_root, self)

        except Exception as exc:
            import logging
            logging.warning(f"Failed to record project evolution or refresh structure: {type(exc).__name__}")

        return release_id

    @_resilient
    def _db_save_release(
        self, record_id: str, fields: Dict[str, Any]
    ) -> Union[str, int, None]:
        """Persist a release: client-minted id, idempotent UPSERT on SurrealDB."""
        if self.backend == "surrealdb":
            query = """
            UPSERT $id CONTENT {
                version: $version,
                tag: $tag,
                notes: $notes,
                issue_github_id: $issue_github_id,
                milestone_id: $milestone_id,
                commit_sha: $commit_sha,
                released_at: time::now()
            };
            """
            params = {"id": self._rid("releases", record_id), **fields}
            try:
                res = self._run_surreal(query, params)
                return self._extract_id(res)
            except _ConnectionLost:
                raise
            except Exception as e:
                logging.error(f"Failed to save release in SurrealDB: {e}")
                raise RuntimeError(f"Failed to save release in SurrealDB: {e}")
        else:
            query = """
            INSERT INTO releases
                (record_id, version, tag, notes, issue_github_id, milestone_id, commit_sha)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """
            try:
                with self._sqlite_conn() as conn:
                    conn.execute(
                        query,
                        (
                            record_id,
                            fields["version"],
                            fields["tag"],
                            fields["notes"],
                            fields["issue_github_id"],
                            fields["milestone_id"],
                            fields["commit_sha"],
                        ),
                    )
                    conn.commit()
                    return record_id
            except sqlite3.Error as e:
                logging.error(f"Failed to save release: {e}")
                raise RuntimeError(f"Failed to save release: {e}")

    @_resilient
    def get_release(self, release_id: Union[str, int]) -> Optional[Dict[str, Any]]:
        """Retrieve a release by id."""
        if self.backend == "surrealdb":
            try:
                res = self._run_surreal(
                    "SELECT * FROM $id", {"id": self._parse_rid(release_id)}
                )
                return self._extract_record(res)
            except _ConnectionLost:
                raise
            except Exception as e:
                logging.error(f"Failed to retrieve release from SurrealDB: {e}")
                raise RuntimeError(f"Failed to retrieve release from SurrealDB: {e}")
        else:
            try:
                with self._sqlite_conn() as conn:
                    cursor = conn.cursor()
                    cursor.execute(
                        "SELECT * FROM releases WHERE id = ? OR record_id = ?",
                        self._sqlite_id_lookup(release_id),
                    )
                    row = cursor.fetchone()
                    return dict(row) if row else None
            except sqlite3.Error as e:
                logging.error(f"Failed to retrieve release: {e}")
                raise RuntimeError(f"Failed to retrieve release: {e}")

    @_resilient
    def list_releases(self, limit: int = 20) -> List[Dict[str, Any]]:
        """List delivered releases, most recent first."""
        if self.backend == "surrealdb":
            try:
                res = self._run_surreal(
                    "SELECT * FROM releases ORDER BY released_at DESC LIMIT $limit",
                    {"limit": int(limit)},
                )
                return self._extract_list(res)
            except _ConnectionLost:
                raise
            except Exception as e:
                logging.error(f"Failed to list releases from SurrealDB: {e}")
                raise RuntimeError(f"Failed to list releases from SurrealDB: {e}")
        else:
            try:
                with self._sqlite_conn() as conn:
                    cursor = conn.cursor()
                    cursor.execute(
                        "SELECT * FROM releases ORDER BY released_at DESC, id DESC LIMIT ?",
                        (int(limit),),
                    )
                    return [dict(row) for row in cursor.fetchall()]
            except sqlite3.Error as e:
                logging.error(f"Failed to list releases: {e}")
                raise RuntimeError(f"Failed to list releases: {e}")

    def log_issue(
        self,
        github_id: str,
        title: str,
        type_: str,
        status: str,
        milestone_id: Optional[Union[str, int]],
        assignee: Optional[str] = None,
    ) -> None:
        """Logs a GitHub issue.

        Args:
            github_id: Numeric or string ID of the GitHub issue.
            title: Title of the issue.
            type_: Type of issue (e.g., bug, feature, refactor).
            status: Status (e.g., open, closed). Normalized to one canonical token
                per logical status on write (ADR-0006), so no two rows differ only
                by casing for the same status.
            milestone_id: Associated milestone ID in the database.
            assignee: Optional canonical person key (ADR-0012), already normalized
                by ``normalize_person_key`` at the capture seam. Additive sixth
                parameter defaulting to None, so every existing 5-arg caller is
                unchanged and stores ``assignee`` NULL, read back as ``unassigned``.
        """
        fields = {
            "github_id": github_id,
            "title": title,
            "type_": type_,
            "status": normalize_status(status),
            "milestone_id": milestone_id,
            "assignee": assignee,
        }
        # github_id is already a stable id, reused for the RecordID and filename.
        self._write_through("issue", github_id, fields, self._db_log_issue)

    @_resilient
    def _db_log_issue(self, record_id: str, fields: Dict[str, Any]) -> None:
        """Persist an issue: idempotent UPSERT keyed by the github_id."""
        if self.backend == "surrealdb":
            query = """
            UPSERT $id CONTENT {
                github_id: $github_id,
                title: $title,
                type_: $type_,
                status: $status,
                milestone_id: $milestone_id,
                assignee: $assignee,
                created_at: time::now()
            };
            """
            params = {"id": self._rid("issues", record_id), **fields}
            try:
                self._run_surreal(query, params)
            except _ConnectionLost:
                raise
            except Exception as e:
                # Log the exception type and record id, never str(e): the issue row
                # carries the person key (an email when public), so a backend error
                # string must not leak it into logs (STRIDE: information disclosure).
                logging.error(
                    "Failed to log issue %s in SurrealDB: %s", record_id, type(e).__name__
                )
                raise RuntimeError(f"Failed to log issue in SurrealDB: {e}")
        else:
            query = """
            INSERT INTO issues (github_id, title, type_, status, milestone_id, assignee)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(github_id) DO UPDATE SET
                title=excluded.title,
                type_=excluded.type_,
                status=excluded.status,
                milestone_id=excluded.milestone_id,
                assignee=excluded.assignee
            """
            try:
                with self._sqlite_conn() as conn:
                    conn.execute(
                        query,
                        (
                            fields["github_id"],
                            fields["title"],
                            fields["type_"],
                            fields["status"],
                            fields["milestone_id"],
                            fields["assignee"],
                        ),
                    )
                    conn.commit()
            except sqlite3.Error as e:
                # Type and record id only, never str(e): the row carries the person
                # key, so a backend error string must not leak it (STRIDE: info
                # disclosure).
                logging.error("Failed to log issue %s: %s", record_id, type(e).__name__)
                raise RuntimeError(f"Failed to log issue: {e}")

    def save_backtest(
        self,
        strategy_name: str,
        sharpe_ratio: float,
        max_drawdown: float,
        profit_factor: float,
        parameters: str,
        dataset: str,
        commit_sha: str,
    ) -> Union[str, int, None]:
        """Saves a backtest run log.

        Args:
            strategy_name: Name of the trading strategy.
            sharpe_ratio: Sharpe ratio outcome.
            max_drawdown: Maximum drawdown percentage.
            profit_factor: Profit factor metric.
            parameters: JSON string or text mapping parameters used.
            dataset: Name or path of the dataset.
            commit_sha: Git commit hash of the code executed.

        Returns:
            The primary key ID or record ID of the inserted record.
        """
        fields = {
            "strategy_name": strategy_name,
            "sharpe_ratio": sharpe_ratio,
            "max_drawdown": max_drawdown,
            "profit_factor": profit_factor,
            "parameters": parameters,
            "dataset": dataset,
            "commit_sha": commit_sha,
        }
        return self._write_through(
            "backtest", self._mint_id("backtest"), fields, self._db_save_backtest
        )

    @_resilient
    def _db_save_backtest(
        self, record_id: str, fields: Dict[str, Any]
    ) -> Union[str, int, None]:
        """Persist a backtest run: client-minted id, idempotent UPSERT on SurrealDB."""
        if self.backend == "surrealdb":
            query = """
            UPSERT $id CONTENT {
                strategy_name: $strategy_name,
                sharpe_ratio: $sharpe_ratio,
                max_drawdown: $max_drawdown,
                profit_factor: $profit_factor,
                parameters: $parameters,
                dataset: $dataset,
                commit_sha: $commit_sha,
                created_at: time::now()
            };
            """
            params = {"id": self._rid("backtest_runs", record_id), **fields}
            try:
                res = self._run_surreal(query, params)
                return self._extract_id(res)
            except _ConnectionLost:
                raise
            except Exception as e:
                logging.error(f"Failed to save backtest run in SurrealDB: {e}")
                raise RuntimeError(f"Failed to save backtest run in SurrealDB: {e}")
        else:
            query = """
            INSERT INTO backtest_runs
                (record_id, strategy_name, sharpe_ratio, max_drawdown,
                 profit_factor, parameters, dataset, commit_sha)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """
            try:
                with self._sqlite_conn() as conn:
                    conn.execute(
                        query,
                        (
                            record_id,
                            fields["strategy_name"],
                            fields["sharpe_ratio"],
                            fields["max_drawdown"],
                            fields["profit_factor"],
                            fields["parameters"],
                            fields["dataset"],
                            fields["commit_sha"],
                        ),
                    )
                    conn.commit()
                    return record_id
            except sqlite3.Error as e:
                logging.error(f"Failed to save backtest run: {e}")
                raise RuntimeError(f"Failed to save backtest run: {e}")

    def save_session(
        self,
        session_id: str,
        agent_name: str,
        task: str,
        messages: Union[List[Dict[str, Any]], str],
        status: str = "active",
        issues: Optional[Sequence[Union[int, str]]] = None,
    ) -> None:
        """Upserts a short-term session state.

        Args:
            session_id: Unique identifier for the session.
            agent_name: Name of the agent.
            task: Task description.
            messages: List of message dictionaries representing conversation history.
            status: Lifecycle status, normalized to the canonical vocabulary
                (active or done) at this write seam (ADR-0016). Additive
                parameter defaulting to active, so every existing caller is
                unchanged and get_latest_activity reads the stored value
                instead of hardcoding it.
            issues: Optional GitHub issue numbers this session worked on. Each
                becomes a ``worked_on`` edge (session -> issue, ADR-0018) after
                the session row lands, so resume is a graph query instead of a
                regex over the free-text task string. Validated numeric before
                any write; a missing issue row is created minimally via the
                log_issue path so an edge never dangles.
        """
        # Validate before the session write so a bad number fails the whole
        # call fast instead of leaving a session row with half its links.
        issue_numbers = [self._canonical_issue_number(n) for n in (issues or [])]
        fields = {
            "session_id": session_id,
            "agent_name": agent_name,
            "task": task,
            "messages": messages,
            "status": normalize_session_status(status),
        }
        # session_id is already a stable id, reused for the RecordID and filename.
        self._write_through("session", session_id, fields, self._db_save_session)
        for gid in issue_numbers:
            self._record_worked_on("sessions", session_id, gid)

    @_resilient
    def _db_save_session(self, record_id: str, fields: Dict[str, Any]) -> None:
        """Persist a session: idempotent UPSERT keyed by the session_id."""
        if self.backend == "surrealdb":
            query = """
            UPSERT $id CONTENT {
                session_id: $session_id,
                agent_name: $agent_name,
                task: $task,
                messages: $messages,
                status: $status,
                timestamp: time::now()
            };
            """
            params = {
                "id": self._rid("sessions", record_id),
                "session_id": fields["session_id"],
                "agent_name": fields["agent_name"],
                "task": fields["task"],
                "messages": fields["messages"],
                "status": fields.get("status") or "active",
            }
            try:
                self._run_surreal(query, params)
            except _ConnectionLost:
                raise
            except Exception as e:
                logging.error(f"Failed to save session in SurrealDB: {e}")
                raise RuntimeError(f"Failed to save session in SurrealDB: {e}")
        else:
            messages = fields["messages"]
            serialized_messages = (
                json.dumps(messages) if not isinstance(messages, str) else messages
            )
            query = """
            INSERT INTO sessions (session_id, agent_name, task, messages, status, timestamp)
            VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(session_id) DO UPDATE SET
                agent_name=excluded.agent_name,
                task=excluded.task,
                messages=excluded.messages,
                status=excluded.status,
                timestamp=CURRENT_TIMESTAMP
            """
            try:
                with self._sqlite_conn() as conn:
                    conn.execute(
                        query,
                        (
                            fields["session_id"],
                            fields["agent_name"],
                            fields["task"],
                            serialized_messages,
                            fields.get("status") or "active",
                        ),
                    )
                    conn.commit()
            except sqlite3.Error as e:
                logging.error(f"Failed to save session: {e}")
                raise RuntimeError(f"Failed to save session: {e}")

    @_resilient
    def get_session(self, session_id: str) -> Optional[Dict[str, Any]]:
        """Retrieves a session state by session_id.

        Args:
            session_id: Unique identifier for the session.

        Returns:
            A dictionary containing the session details or None.
        """
        if self.backend == "surrealdb":
            query = "SELECT * FROM sessions WHERE session_id = $session_id"
            try:
                res = self._run_surreal(query, {"session_id": session_id})
                return self._extract_record(res)
            except _ConnectionLost:
                raise
            except Exception as e:
                logging.error(f"Failed to retrieve session from SurrealDB: {e}")
                raise RuntimeError(f"Failed to retrieve session from SurrealDB: {e}")
        else:
            query = "SELECT * FROM sessions WHERE session_id = ?"
            try:
                with self._sqlite_conn() as conn:
                    cursor = conn.cursor()
                    cursor.execute(query, (session_id,))
                    row = cursor.fetchone()
                    return dict(row) if row else None
            except sqlite3.Error as e:
                logging.error(f"Failed to retrieve session: {e}")
                raise RuntimeError(f"Failed to retrieve session: {e}")

    def log_handoff(
        self,
        sender: str,
        recipient: str,
        contract_type: str,
        contract_path: str,
        status: str,
        summary: str = "",
    ) -> Union[str, int, None]:
        """Creates a handoff log entry.

        Args:
            sender: The sender agent name.
            recipient: The recipient agent name.
            contract_type: Type of contract (e.g. plan, code).
            contract_path: File path to contract documentation.
            status: Lifecycle status, normalized to the canonical vocabulary
                (open, accepted, done) at this write seam (ADR-0016).
            summary: Short "what this stage did" text persisted on the row, so a
                resume survives worktree teardown even when the contract file at
                ``contract_path`` is gone. Additive parameter defaulting to ""
                so every existing 5-arg caller is unchanged.

        Returns:
            The primary key ID or record ID of the created handoff.
        """
        fields = {
            "sender": sender,
            "recipient": recipient,
            "contract_type": contract_type,
            "contract_path": contract_path,
            "status": normalize_handoff_status(status),
            "summary": summary,
        }
        handoff_id = self._write_through(
            "handoff", self._mint_id("handoff"), fields, self._db_log_handoff
        )
        try:
            from solomon_harness.bootstrap import index_codebase, scan_project_structure
            index_codebase(self._project_root, self)
            scan_project_structure(self._project_root, self)
        except Exception as exc:
            import logging
            logging.warning(f"Project structure scan refresh failed on handoff: {type(exc).__name__}")
        return handoff_id

    @_resilient
    def _db_log_handoff(
        self, record_id: str, fields: Dict[str, Any]
    ) -> Union[str, int, None]:
        """Persist a handoff: client-minted id, idempotent UPSERT on SurrealDB."""
        if self.backend == "surrealdb":
            query = """
            UPSERT $id CONTENT {
                sender: $sender,
                recipient: $recipient,
                contract_type: $contract_type,
                contract_path: $contract_path,
                status: $status,
                summary: $summary,
                timestamp: time::now()
            };
            """
            params = {"id": self._rid("handoffs", record_id), **fields}
            try:
                res = self._run_surreal(query, params)
                return self._extract_id(res)
            except _ConnectionLost:
                raise
            except Exception as e:
                logging.error(f"Failed to log handoff in SurrealDB: {e}")
                raise RuntimeError(f"Failed to log handoff in SurrealDB: {e}")
        else:
            query = """
            INSERT INTO handoffs
                (record_id, sender, recipient, contract_type, contract_path, status, summary)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """
            try:
                with self._sqlite_conn() as conn:
                    conn.execute(
                        query,
                        (
                            record_id,
                            fields["sender"],
                            fields["recipient"],
                            fields["contract_type"],
                            fields["contract_path"],
                            fields["status"],
                            fields["summary"],
                        ),
                    )
                    conn.commit()
                    return record_id
            except sqlite3.Error as e:
                logging.error(f"Failed to log handoff: {e}")
                raise RuntimeError(f"Failed to log handoff: {e}")

    def update_handoff_status(
        self, handoff_id: Union[str, int], status: str
    ) -> Union[str, int, None]:
        """Move a handoff along its lifecycle (open -> accepted -> done).

        Read-modify-write through the durability funnel: the mirror is
        re-written with the full merged row (not a partial patch), so a replay
        after an outage reconstructs the record instead of clobbering it. The
        status is normalized to the canonical vocabulary at this seam
        (ADR-0016). Returns the record id, or None when the handoff does not
        exist (never invents a row).
        """
        row = self.get_handoff(handoff_id)
        if row is None:
            return None
        fields = {
            "sender": row.get("sender"),
            "recipient": row.get("recipient"),
            "contract_type": row.get("contract_type"),
            "contract_path": row.get("contract_path"),
            "summary": row.get("summary") or "",
            "status": normalize_handoff_status(status),
        }
        record_key = self._record_key(row.get("id"), handoff_id)
        return self._write_through("handoff", record_key, fields, self._db_update_handoff)

    @staticmethod
    def _record_key(row_id: Any, fallback: Any) -> str:
        """The bare record key of a fetched row, for re-keying a funnel write.

        Strips the SurrealDB ``table:`` prefix and the v3.x display delimiters
        (angle brackets or backticks) from a stringified record id, so the
        funnel's mirror filename and UPSERT RecordID match the stored record.
        A SQLite integer id stringifies as-is; a missing id falls back to the
        id the caller passed.
        """
        value = row_id if row_id is not None else fallback
        s = str(value)
        if ":" in s:
            _, _, key = s.partition(":")
            key = key.strip()
            if len(key) >= 2 and key[0] == "⟨" and key[-1] == "⟩":
                key = key[1:-1]
            elif len(key) >= 2 and key[0] == "`" and key[-1] == "`":
                key = key[1:-1]
            return key
        return s

    def _sqlite_id_lookup(self, value: Any) -> tuple:
        """The parameter pair for a ``WHERE id = ? OR record_id = ?`` lookup.

        Accepts a legacy integer rowid, a minted record id, or the SurrealDB
        ``table:key`` spelling (stripped via :meth:`_record_key`), so a caller
        holding an id from either backend resolves the same row (F7).
        """
        return (value, self._record_key(value, value))

    @_resilient
    def _db_update_handoff(
        self, record_id: str, fields: Dict[str, Any]
    ) -> Union[str, int, None]:
        """Persist a handoff status change: targeted UPDATE, never a re-insert.

        SurrealDB gets ``UPDATE $id SET status = $status`` so the original
        timestamp and the rest of the row are preserved; SQLite updates by
        primary key. The full merged row lives in the mirror (written by the
        funnel), which is what a replay uses.
        """
        if self.backend == "surrealdb":
            query = "UPDATE $id SET status = $status;"
            params = {"id": self._rid("handoffs", record_id), "status": fields["status"]}
            try:
                res = self._run_surreal(query, params)
                return self._extract_id(res) or record_id
            except _ConnectionLost:
                raise
            except Exception as e:
                logging.error(f"Failed to update handoff in SurrealDB: {e}")
                raise RuntimeError(f"Failed to update handoff in SurrealDB: {e}")
        else:
            try:
                with self._sqlite_conn() as conn:
                    conn.execute(
                        "UPDATE handoffs SET status = ? WHERE id = ? OR record_id = ?",
                        (fields["status"], *self._sqlite_id_lookup(record_id)),
                    )
                    conn.commit()
                    return record_id
            except sqlite3.Error as e:
                logging.error(f"Failed to update handoff: {e}")
                raise RuntimeError(f"Failed to update handoff: {e}")

    def record_status_transition(
        self,
        github_id: Union[str, int],
        from_status: Optional[str],
        to_status: Optional[str],
        actor: Optional[str] = None,
    ) -> Union[str, int, None]:
        """Append one issue status transition to the first-class timeline.

        The row is ``{issue, github_id, from_status, to_status, entered_at,
        actor}`` (ADR-0016, F4): ``issue`` links the issues record on SurrealDB
        and ``entered_at`` is stamped server-side with ``time::now()``; on the
        SQLite fallback ``github_id`` stands in for the link and the stamp is
        UTC. Statuses are normalized through the canonical vocabulary
        (ADR-0006) at this write seam. Returns the client-minted record id on
        both backends. Not mirrored: durability is covered by the parallel
        legacy board_history write for this release (see the ADR).
        """
        fields = {
            "github_id": str(github_id),
            "from_status": normalize_status(from_status),
            "to_status": normalize_status(to_status),
            "actor": actor,
        }
        # Minted here, outside the resilient retry, so a reconnect/fallback
        # re-run never re-mints the id.
        return self._db_record_status_transition(self._mint_id("transition"), fields)

    @_resilient
    def _db_record_status_transition(
        self, record_id: str, fields: Dict[str, Any]
    ) -> Union[str, int, None]:
        """Persist a transition: minted id, idempotent UPSERT on SurrealDB."""
        if self.backend == "surrealdb":
            query = """
            UPSERT $id CONTENT {
                issue: $issue,
                github_id: $github_id,
                from_status: $from_status,
                to_status: $to_status,
                actor: $actor,
                entered_at: time::now()
            };
            """
            params = {
                "id": self._rid("transitions", record_id),
                "issue": self._rid("issues", fields["github_id"]),
                **fields,
            }
            try:
                res = self._run_surreal(query, params)
                return self._extract_id(res) or record_id
            except _ConnectionLost:
                raise
            except Exception as e:
                logging.error(f"Failed to record transition in SurrealDB: {e}")
                raise RuntimeError(f"Failed to record transition in SurrealDB: {e}")
        else:
            query = """
            INSERT INTO transitions
                (record_id, github_id, from_status, to_status, entered_at, actor)
            VALUES (?, ?, ?, ?, ?, ?)
            """
            try:
                with self._sqlite_conn() as conn:
                    conn.execute(
                        query,
                        (
                            record_id,
                            fields["github_id"],
                            fields["from_status"],
                            fields["to_status"],
                            self._utc_iso(),
                            fields["actor"],
                        ),
                    )
                    conn.commit()
                    return record_id
            except sqlite3.Error as e:
                logging.error(f"Failed to record transition: {e}")
                raise RuntimeError(f"Failed to record transition: {e}")

    @_resilient
    def get_status_transitions(
        self, github_ids: Sequence[Union[str, int]]
    ) -> Dict[str, List[Dict[str, Any]]]:
        """Bulk-read the recorded transitions for the given issues, one round trip.

        Returns a dict keyed by github_id; each value is the issue's transitions
        ascending by ``entered_at`` as ``{from_status, to_status, entered_at,
        actor}`` with ``entered_at`` coerced to an ISO-8601 string on both
        backends. An issue with no rows is absent, so a caller's ``.get(id, [])``
        degrades cleanly (the cockpit falls back to the legacy board_history).
        """
        ids = sorted({str(gid) for gid in github_ids if gid})
        if not ids:
            return {}
        if self.backend == "surrealdb":
            query = (
                "SELECT github_id, from_status, to_status, entered_at, actor "
                "FROM transitions WHERE github_id IN $ids ORDER BY entered_at;"
            )
            try:
                res = self._run_surreal(query, {"ids": ids})
                rows = self._extract_list(res)
            except _ConnectionLost:
                raise
            except Exception as e:
                logging.error(f"Failed to read transitions from SurrealDB: {e}")
                raise RuntimeError(f"Failed to read transitions from SurrealDB: {e}")
        else:
            placeholders = ", ".join("?" for _ in ids)
            query = (
                "SELECT github_id, from_status, to_status, entered_at, actor "
                f"FROM transitions WHERE github_id IN ({placeholders}) "
                "ORDER BY entered_at, id"
            )
            try:
                with self._sqlite_conn() as conn:
                    cursor = conn.cursor()
                    cursor.execute(query, ids)
                    rows = [dict(row) for row in cursor.fetchall()]
            except sqlite3.Error as e:
                logging.error(f"Failed to read transitions: {e}")
                raise RuntimeError(f"Failed to read transitions: {e}")
        grouped: Dict[str, List[Dict[str, Any]]] = {}
        for row in rows:
            entered_at = row.get("entered_at")
            if isinstance(entered_at, datetime.datetime):
                entered_at = entered_at.isoformat()
            grouped.setdefault(str(row.get("github_id")), []).append(
                {
                    "from_status": row.get("from_status"),
                    "to_status": row.get("to_status"),
                    "entered_at": entered_at,
                    "actor": row.get("actor"),
                }
            )
        return grouped

    @_resilient
    def get_handoff(self, handoff_id: Union[str, int]) -> Optional[Dict[str, Any]]:
        """Retrieves handoff log details by ID.

        Args:
            handoff_id: The primary key ID or record ID of the handoff.

        Returns:
            A dictionary containing the handoff details or None.
        """
        if self.backend == "surrealdb":
            query = "SELECT * FROM $id"
            try:
                res = self._run_surreal(
                    query, {"id": self._parse_rid(handoff_id)}
                )
                return self._extract_record(res)
            except _ConnectionLost:
                raise
            except Exception as e:
                logging.error(f"Failed to retrieve handoff from SurrealDB: {e}")
                raise RuntimeError(f"Failed to retrieve handoff from SurrealDB: {e}")
        else:
            query = "SELECT * FROM handoffs WHERE id = ? OR record_id = ?"
            try:
                with self._sqlite_conn() as conn:
                    cursor = conn.cursor()
                    cursor.execute(query, self._sqlite_id_lookup(handoff_id))
                    row = cursor.fetchone()
                    return dict(row) if row else None
            except sqlite3.Error as e:
                logging.error(f"Failed to retrieve handoff: {e}")
                raise RuntimeError(f"Failed to retrieve handoff: {e}")

    @_resilient
    def get_decision(self, decision_id: Union[str, int]) -> Optional[Dict[str, Any]]:
        """Retrieves a logged decision by ID.

        Args:
            decision_id: The primary key ID or record ID of the decision.

        Returns:
            A dictionary containing the record details or None.
        """
        if self.backend == "surrealdb":
            query = "SELECT * FROM $id"
            try:
                res = self._run_surreal(
                    query, {"id": self._parse_rid(decision_id)}
                )
                return self._extract_record(res)
            except _ConnectionLost:
                raise
            except Exception as e:
                logging.error(f"Failed to retrieve decision from SurrealDB: {e}")
                raise RuntimeError(f"Failed to retrieve decision from SurrealDB: {e}")
        else:
            query = "SELECT * FROM decisions WHERE id = ? OR record_id = ?"
            try:
                with self._sqlite_conn() as conn:
                    cursor = conn.cursor()
                    cursor.execute(query, self._sqlite_id_lookup(decision_id))
                    row = cursor.fetchone()
                    return dict(row) if row else None
            except sqlite3.Error as e:
                logging.error(f"Failed to retrieve decision: {e}")
                raise RuntimeError(f"Failed to retrieve decision: {e}")

    @_resilient
    def get_milestone(self, milestone_id: Union[str, int]) -> Optional[Dict[str, Any]]:
        """Retrieves a milestone by ID.

        Args:
            milestone_id: The primary key ID or record ID of the milestone.

        Returns:
            A dictionary containing the record details or None.
        """
        if self.backend == "surrealdb":
            query = "SELECT * FROM $id"
            try:
                res = self._run_surreal(
                    query, {"id": self._parse_rid(milestone_id)}
                )
                return self._extract_record(res)
            except _ConnectionLost:
                raise
            except Exception as e:
                logging.error(f"Failed to retrieve milestone from SurrealDB: {e}")
                raise RuntimeError(f"Failed to retrieve milestone from SurrealDB: {e}")
        else:
            query = "SELECT * FROM milestones WHERE id = ? OR record_id = ?"
            try:
                with self._sqlite_conn() as conn:
                    cursor = conn.cursor()
                    cursor.execute(query, self._sqlite_id_lookup(milestone_id))
                    row = cursor.fetchone()
                    return dict(row) if row else None
            except sqlite3.Error as e:
                logging.error(f"Failed to retrieve milestone: {e}")
                raise RuntimeError(f"Failed to retrieve milestone: {e}")

    @_resilient
    def get_issue(self, github_id: str) -> Optional[Dict[str, Any]]:
        """Retrieves an issue by its GitHub ID.

        Args:
            github_id: The primary key GitHub ID or record ID of the issue.

        Returns:
            A dictionary containing the record details or None.
        """
        if self.backend == "surrealdb":
            query = "SELECT * FROM issues WHERE github_id = $github_id"
            try:
                res = self._run_surreal(query, {"github_id": github_id})
                return self._extract_record(res)
            except _ConnectionLost:
                raise
            except Exception as e:
                logging.error(f"Failed to retrieve issue from SurrealDB: {e}")
                raise RuntimeError(f"Failed to retrieve issue from SurrealDB: {e}")
        else:
            query = "SELECT * FROM issues WHERE github_id = ?"
            try:
                with self._sqlite_conn() as conn:
                    cursor = conn.cursor()
                    cursor.execute(query, (github_id,))
                    row = cursor.fetchone()
                    return dict(row) if row else None
            except sqlite3.Error as e:
                logging.error(f"Failed to retrieve issue: {e}")
                raise RuntimeError(f"Failed to retrieve issue: {e}")

    @_resilient
    def get_backtest(self, backtest_id: Union[str, int]) -> Optional[Dict[str, Any]]:
        """Retrieves a backtest run by ID.

        Args:
            backtest_id: The primary key ID or record ID of the backtest run.

        Returns:
            A dictionary containing the record details or None.
        """
        if self.backend == "surrealdb":
            query = "SELECT * FROM $id"
            try:
                res = self._run_surreal(
                    query, {"id": self._parse_rid(backtest_id)}
                )
                return self._extract_record(res)
            except _ConnectionLost:
                raise
            except Exception as e:
                logging.error(f"Failed to retrieve backtest run from SurrealDB: {e}")
                raise RuntimeError(
                    f"Failed to retrieve backtest run from SurrealDB: {e}"
                )
        else:
            query = "SELECT * FROM backtest_runs WHERE id = ? OR record_id = ?"
            try:
                with self._sqlite_conn() as conn:
                    cursor = conn.cursor()
                    cursor.execute(query, self._sqlite_id_lookup(backtest_id))
                    row = cursor.fetchone()
                    return dict(row) if row else None
            except sqlite3.Error as e:
                logging.error(f"Failed to retrieve backtest run: {e}")
                raise RuntimeError(f"Failed to retrieve backtest run: {e}")

    @staticmethod
    def _annotate_issue_bucket(row: Dict[str, Any]) -> Dict[str, Any]:
        """Add the derived ``is_github_issue`` bucket flag to an issue row in place.

        Purely additive (#116): the row's stored fields are untouched and the set of
        rows returned is unchanged; callers gain a derived view field so they can
        segregate real GitHub issues from tracking items without re-parsing
        ``github_id``. No DB row is written, deleted, or mutated.
        """
        row["is_github_issue"] = is_github_issue(row.get("github_id"))
        return row

    @_resilient
    def get_open_issues(self) -> List[Dict[str, Any]]:
        """Retrieves the open issues, defined as every non-terminal row.

        "Open" is a non-terminal predicate (ADR-0006), not the literal
        status='open' filter no lifecycle step writes: a row is open when its
        status is not one of the terminal literals (closed/done/Done). A row with
        no status is non-terminal too (is_terminal(None) is False), so a NULL/NONE
        status is kept, matching digest.build_digest; a bare ``NOT IN`` would drop
        it. The terminal set is bound as a query parameter on both backends, never
        string-formatted, so the predicate carries no injection surface.

        Returns:
            A list of dictionaries, one per non-terminal issue, each carrying the
            stored fields plus a derived ``is_github_issue`` boolean (#116): True for
            a numeric GitHub id, False for a RAID/follow-up tracking row. The derived
            field is additive -- the stored row and the returned set are unchanged.
        """
        if self.backend == "surrealdb":
            query = (
                "SELECT * FROM issues "
                "WHERE status IS NONE OR status IS NULL OR status NOT IN $terminal"
            )
            try:
                res = self._run_surreal(query, {"terminal": list(TERMINAL_STATUSES)})
                return [self._annotate_issue_bucket(row) for row in self._extract_list(res)]
            except _ConnectionLost:
                raise
            except Exception as e:
                logging.error(f"Failed to retrieve open issues from SurrealDB: {e}")
                raise RuntimeError(
                    f"Failed to retrieve open issues from SurrealDB: {e}"
                )
        else:
            placeholders = ", ".join("?" for _ in TERMINAL_STATUSES)
            query = (
                f"SELECT * FROM issues WHERE status IS NULL OR status NOT IN ({placeholders})"
            )
            try:
                with self._sqlite_conn() as conn:
                    cursor = conn.cursor()
                    cursor.execute(query, tuple(TERMINAL_STATUSES))
                    rows = cursor.fetchall()
                    return [self._annotate_issue_bucket(dict(row)) for row in rows]
            except sqlite3.Error as e:
                logging.error(f"Failed to retrieve open issues: {e}")
                raise RuntimeError(f"Failed to retrieve open issues: {e}")

    def list_databases(self) -> List[str]:
        """List the harness-managed tenant database names (read-only).

        SurrealDB: discover tenants via ``INFO FOR NS``. SQLite fallback: return
        the single resolvable tenant for this workspace, derived from the config
        or the git remote. No row is created or mutated on either path.
        """
        if self.backend == "surrealdb":
            try:
                res = self.db.query("INFO FOR NS")
                info: Any = res
                if isinstance(info, list) and info:
                    head = info[0]
                    info = head.get("result", head) if isinstance(head, dict) else head
                databases = info.get("databases", {}) if isinstance(info, dict) else {}
                if isinstance(databases, dict):
                    return sorted(databases.keys())
                return sorted(str(d) for d in databases)
            except Exception as e:
                logging.error(f"Failed to list databases from SurrealDB: {e}")
                raise RuntimeError(f"Failed to list databases from SurrealDB: {e}")
        return [_resolve_database(self._configured_database, self._project_root)]

    def use_tenant(self, database: str) -> None:
        """Re-scope the open connection to a tenant database (read-only).

        SurrealDB: rebind the connection scope with the SDK's parameterized
        ``use(namespace, database)`` call, the same bind the constructor uses.
        It carries no SQL and performs no write, and binds exactly one database,
        so per-tenant isolation (ADR-0002) holds by construction. Callers must
        pass a name already validated against the discovered-tenant allowlist.
        SQLite fallback: a no-op, because a SQLite workspace resolves to a single
        tenant and the allowlist only ever yields that one name.
        """
        if self.backend == "surrealdb" and self.db is not None:
            self.db.use(self._namespace, database)

    def list_issues(self) -> List[Dict[str, Any]]:
        """Retrieves every issue for this tenant regardless of status.

        Read-only. Unlike get_open_issues (the non-terminal rows only), this returns
        all issues including the terminal/Done ones, so the cockpit board can render
        the full seven columns. No row is created or mutated.
        """
        if self.backend == "surrealdb":
            query = "SELECT * FROM issues"
            try:
                res = self.db.query(query)
                return self._extract_list(res)
            except Exception as e:
                logging.error(f"Failed to list issues from SurrealDB: {e}")
                raise RuntimeError(f"Failed to list issues from SurrealDB: {e}")
        else:
            query = "SELECT * FROM issues ORDER BY created_at"
            try:
                with self._sqlite_conn() as conn:
                    cursor = conn.cursor()
                    cursor.execute(query)
                    return [dict(row) for row in cursor.fetchall()]
            except sqlite3.Error as e:
                logging.error(f"Failed to list issues: {e}")
                raise RuntimeError(f"Failed to list issues: {e}")

    @_resilient
    def get_latest_activity(self) -> Optional[Dict[str, Any]]:
        """Retrieves the most recent entry from the handoffs or sessions table.

        A broken connection must never masquerade as "no activity": a connection
        loss propagates as ``_ConnectionLost`` so the resilient decorator reconnects
        or falls back, and a genuinely empty store still returns None (issue #37).

        The winning row (session or handoff, whichever has the later timestamp)
        shapes the 'type', 'agent', 'task', and 'status' fields. Every /solomon-*
        command logs a handoff immediately followed by a session save, so the
        session row routinely wins by timestamp; regardless of which row wins,
        'contract_path' is populated from the latest handoff if one exists, so
        the handoff contract (docs/solomon-workflow.md, "Handoff contracts") is
        never silently dropped.

        Returns:
            A dictionary with keys 'type', 'agent', 'task', 'status', 'timestamp'
            (and 'contract_path', pointing to the latest handoff contract
            artifact, plus 'summary', the latest handoff's persisted "what this
            stage did" text, both surfaced if any handoff has been logged), or
            None if no activity exists.
        """
        latest_session = None
        if self.backend == "surrealdb":
            query = "SELECT * FROM sessions ORDER BY timestamp DESC LIMIT 1"
            try:
                res = self._run_surreal(query)
                latest_session = self._extract_record(res)
            except _ConnectionLost:
                raise
            except Exception as e:
                logging.error(f"Failed to query latest session: {e}")
        else:
            query = "SELECT * FROM sessions ORDER BY timestamp DESC LIMIT 1"
            try:
                with self._sqlite_conn() as conn:
                    cursor = conn.cursor()
                    cursor.execute(query)
                    row = cursor.fetchone()
                    if row:
                        latest_session = dict(row)
            except sqlite3.Error as e:
                logging.error(f"Failed to query latest session: {e}")

        latest_handoff = None
        if self.backend == "surrealdb":
            query = "SELECT * FROM handoffs ORDER BY timestamp DESC LIMIT 1"
            try:
                res = self._run_surreal(query)
                latest_handoff = self._extract_record(res)
            except _ConnectionLost:
                raise
            except Exception as e:
                logging.error(f"Failed to query latest handoff: {e}")
        else:
            query = "SELECT * FROM handoffs ORDER BY timestamp DESC LIMIT 1"
            try:
                with self._sqlite_conn() as conn:
                    cursor = conn.cursor()
                    cursor.execute(query)
                    row = cursor.fetchone()
                    if row:
                        latest_handoff = dict(row)
            except sqlite3.Error as e:
                logging.error(f"Failed to query latest handoff: {e}")

        if not latest_session and not latest_handoff:
            return None

        def parse_time(ts: Any) -> float:
            if not ts:
                return 0.0
            ts_str = str(ts).replace(" ", "T")
            try:
                import datetime

                clean_ts = ts_str.rstrip("Z")
                if "+" in clean_ts:
                    clean_ts = clean_ts.split("+")[0]
                dt = datetime.datetime.fromisoformat(clean_ts)
                return dt.timestamp()
            except Exception:
                return 0.0

        t_session = (
            parse_time(latest_session.get("timestamp")) if latest_session else -1.0
        )
        t_handoff = (
            parse_time(latest_handoff.get("timestamp")) if latest_handoff else -1.0
        )

        if t_session >= t_handoff:
            assert latest_session is not None
            result: Dict[str, Any] = {
                "type": "session",
                "agent": latest_session.get("agent_name"),
                "task": latest_session.get("task"),
                # The stored lifecycle status (ADR-0016); legacy rows written
                # before the status column existed read back as active, which
                # was the previously hardcoded value.
                "status": latest_session.get("status") or "active",
                "timestamp": latest_session.get("timestamp"),
            }
            # Every /solomon-* command logs a handoff immediately followed by a
            # session save, so the session row routinely wins this comparison.
            # Surface the latest handoff's contract_path regardless, so the
            # bounded-context handoff mechanism (docs/solomon-workflow.md,
            # "Handoff contracts") is never silently dropped by that ordering.
            if latest_handoff is not None:
                result["contract_path"] = latest_handoff.get("contract_path")
                result["summary"] = latest_handoff.get("summary")
            # The linked issue numbers from the session's worked_on edges
            # (ADR-0018), added only when edges exist so consumers pinned on
            # the exact legacy shape are untouched by pre-edge rows.
            linked = self._session_issue_numbers(latest_session.get("session_id"))
            if linked:
                result["issues"] = linked
            return result
        else:
            assert latest_handoff is not None
            return {
                "type": "handoff",
                "agent": f"{latest_handoff.get('sender')} -> {latest_handoff.get('recipient')}",
                "task": latest_handoff.get("contract_type"),
                "status": latest_handoff.get("status"),
                "contract_path": latest_handoff.get("contract_path"),
                # The persisted "what this stage did" text (ADR-0016), so a
                # resume works even when the contract file is gone with its
                # worktree.
                "summary": latest_handoff.get("summary"),
                "timestamp": latest_handoff.get("timestamp"),
            }

    def _session_issue_numbers(self, session_id: Any) -> List[int]:
        """GitHub issue numbers linked from a session by worked_on edges.

        Best-effort by design (ADR-0018): a graph read failure reports no
        links, because the resume shape must never break when the graph is
        unreachable -- the session row itself was already fetched.
        """
        if not session_id:
            return []
        try:
            if self.backend == "surrealdb":
                res = self._run_surreal(
                    "SELECT array::distinct(->worked_on->issues.github_id) "
                    "AS gids FROM $node;",
                    {"node": self._rid("sessions", str(session_id))},
                )
                gids = self._extract_field(res, "gids") or []
            else:
                with self._sqlite_conn() as conn:
                    cursor = conn.cursor()
                    cursor.execute(
                        "SELECT DISTINCT github_id FROM worked_on "
                        "WHERE source_table = 'sessions' AND source_id = ?",
                        (str(session_id),),
                    )
                    gids = [row["github_id"] for row in cursor.fetchall()]
            return sorted(
                int(g) for g in gids if str(g).isdigit() and str(g).isascii()
            )
        except Exception:
            return []

    @staticmethod
    def _activity_epoch(ts: Any) -> float:
        """Best-effort epoch seconds for an activity timestamp (0.0 unknown).

        Accepts the native datetime SurrealDB returns and the ISO/space-
        separated strings SQLite stores, mirroring get_latest_activity's
        tolerant parsing so the two orderings can never disagree.
        """
        if isinstance(ts, datetime.datetime):
            return ts.timestamp()
        if not ts:
            return 0.0
        clean = str(ts).replace(" ", "T").rstrip("Z")
        if "+" in clean:
            clean = clean.split("+")[0]
        try:
            return datetime.datetime.fromisoformat(clean).timestamp()
        except ValueError:
            return 0.0

    @_resilient
    def latest_activity_per_issue(self, limit: int = 10) -> List[Dict[str, Any]]:
        """The most recent linked activity per non-terminal issue (ADR-0018).

        For each issue that has worked_on edges and is not terminal, returns
        the most recent linked session or loop run. One graph query on
        SurrealDB (issues projecting ``<-worked_on<-sessions`` and
        ``<-worked_on<-loop_runs``); a join over the parity link table on the
        SQLite fallback. The terminal filter runs in Python through the shared
        :func:`is_terminal` predicate, so the status vocabulary lives in one
        place.

        Returns rows shaped ``{github_id, title, issue_status, type, agent,
        task, status, timestamp}`` -- ``type`` is ``session`` or ``loop_run``;
        for a loop run ``agent`` is the stage and ``task`` the decision text.
        Most recent first, capped at ``limit``.
        """
        candidates: List[Dict[str, Any]] = []
        order = 0
        if self.backend == "surrealdb":
            query = (
                "SELECT github_id, title, status AS issue_status, "
                "<-worked_on<-sessions.* AS sessions, "
                "<-worked_on<-loop_runs.* AS loop_runs "
                "FROM issues WHERE count(<-worked_on) > 0;"
            )
            try:
                res = self._run_surreal(query)
                issues = self._extract_list(res)
            except _ConnectionLost:
                raise
            except Exception as e:
                logging.error(f"Failed to query per-issue activity: {e}")
                raise RuntimeError(f"Failed to query per-issue activity: {e}")
            for issue in issues:
                for s in issue.get("sessions") or []:
                    order += 1
                    candidates.append({
                        "github_id": issue.get("github_id"),
                        "title": issue.get("title"),
                        "issue_status": issue.get("issue_status"),
                        "type": "session",
                        "agent": s.get("agent_name"),
                        "task": s.get("task"),
                        "status": s.get("status"),
                        "timestamp": s.get("timestamp"),
                        "_order": order,
                    })
                for r in issue.get("loop_runs") or []:
                    order += 1
                    candidates.append({
                        "github_id": issue.get("github_id"),
                        "title": issue.get("title"),
                        "issue_status": issue.get("issue_status"),
                        "type": "loop_run",
                        "agent": r.get("stage"),
                        "task": r.get("decision"),
                        "status": r.get("status"),
                        "timestamp": r.get("created_at"),
                        "_order": order,
                    })
        else:
            session_query = """
            SELECT w.github_id AS github_id, i.title AS title,
                   i.status AS issue_status, s.agent_name AS agent,
                   s.task AS task, s.status AS status,
                   s.timestamp AS timestamp, w.id AS link_order
            FROM worked_on w
            JOIN sessions s
                ON w.source_table = 'sessions' AND w.source_id = s.session_id
            LEFT JOIN issues i ON i.github_id = w.github_id
            """
            loop_query = """
            SELECT w.github_id AS github_id, i.title AS title,
                   i.status AS issue_status, r.stage AS agent,
                   r.decision AS task, r.status AS status,
                   r.created_at AS timestamp, w.id AS link_order
            FROM worked_on w
            JOIN loop_runs r
                ON w.source_table = 'loop_runs' AND w.source_id = r.record_id
            LEFT JOIN issues i ON i.github_id = w.github_id
            """
            try:
                with self._sqlite_conn() as conn:
                    cursor = conn.cursor()
                    for kind, query in (
                        ("session", session_query),
                        ("loop_run", loop_query),
                    ):
                        cursor.execute(query)
                        for row in cursor.fetchall():
                            entry = dict(row)
                            entry["type"] = kind
                            # The link-row id is a global insertion sequence:
                            # it breaks CURRENT_TIMESTAMP's one-second ties
                            # deterministically.
                            entry["_order"] = entry.pop("link_order")
                            candidates.append(entry)
            except sqlite3.Error as e:
                logging.error(f"Failed to query per-issue activity: {e}")
                raise RuntimeError(f"Failed to query per-issue activity: {e}")

        best: Dict[str, Dict[str, Any]] = {}
        for entry in candidates:
            if is_terminal(entry.get("issue_status")):
                continue
            gid = str(entry.get("github_id"))
            key = (self._activity_epoch(entry.get("timestamp")), entry["_order"])
            current = best.get(gid)
            if current is None or key > (
                self._activity_epoch(current.get("timestamp")), current["_order"]
            ):
                best[gid] = entry
        rows = sorted(
            best.values(),
            key=lambda e: (self._activity_epoch(e.get("timestamp")), e["_order"]),
            reverse=True,
        )[: int(limit)]
        for entry in rows:
            entry.pop("_order", None)
        return rows

    def save_loop_run(
        self,
        stage: str,
        target: str,
        decision: str,
        status: str,
        session_id: str,
        target_issue: Optional[int] = None,
    ) -> Union[str, int, None]:
        """Append one loop-run entry to the auditable ledger.

        Each driven stage records what it advanced and the outcome, so the loop's
        own decisions become an auditable trail. The concurrent-driver guard is
        the lockfile, not this ledger, because under the SQLite fallback each
        worktree gets a separate database and a cross-worktree count would be
        invisible.

        ``status`` is normalized to the canonical loop-run vocabulary (ok or
        failed) at this write seam, so the aggregators can count one token
        (#165, ADR-0016).

        ``target_issue`` is the GitHub issue number this run advanced, when the
        stage carries one. It is stored on the row and also written as a
        ``worked_on`` edge (loop_run -> issue, ADR-0018), the same edge table
        sessions use, so per-issue resume sees loop runs too.
        """
        gid = (
            self._canonical_issue_number(target_issue)
            if target_issue is not None
            else None
        )
        fields = {
            "stage": stage,
            "target": target,
            "decision": decision,
            "status": normalize_loop_run_status(status),
            "session_id": session_id,
            "target_issue": int(gid) if gid is not None else None,
        }
        record_id = self._mint_id("loop_run")
        result = self._write_through(
            "loop_run", record_id, fields, self._db_save_loop_run
        )
        if gid is not None:
            self._record_worked_on("loop_runs", record_id, gid)
        return result

    @_resilient
    def _db_save_loop_run(
        self, record_id: str, fields: Dict[str, Any]
    ) -> Union[str, int, None]:
        """Persist a loop-run entry: client-minted id, idempotent UPSERT on SurrealDB."""
        if self.backend == "surrealdb":
            query = """
            UPSERT $id CONTENT {
                stage: $stage,
                target: $target,
                decision: $decision,
                status: $status,
                session_id: $session_id,
                target_issue: $target_issue,
                created_at: time::now()
            };
            """
            params = {"id": self._rid("loop_runs", record_id), **fields}
            params.setdefault("target_issue", None)
            try:
                res = self._run_surreal(query, params)
                return self._extract_id(res)
            except _ConnectionLost:
                raise
            except Exception as e:
                logging.error(f"Failed to save loop run in SurrealDB: {e}")
                raise RuntimeError(f"Failed to save loop run in SurrealDB: {e}")
        else:
            query = """
            INSERT INTO loop_runs
                (record_id, stage, target, decision, status, session_id, target_issue)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """
            try:
                with self._sqlite_conn() as conn:
                    conn.execute(
                        query,
                        (
                            record_id,
                            fields["stage"],
                            fields["target"],
                            fields["decision"],
                            fields["status"],
                            fields["session_id"],
                            fields.get("target_issue"),
                        ),
                    )
                    conn.commit()
                    return record_id
            except sqlite3.Error as e:
                logging.error(f"Failed to save loop run: {e}")
                raise RuntimeError(f"Failed to save loop run: {e}")

    def list_loop_runs(self, limit: int = 20) -> List[Dict[str, Any]]:
        """List loop runs, most recent first."""
        if self.backend == "surrealdb":
            try:
                res = self.db.query(
                    "SELECT * FROM loop_runs ORDER BY created_at DESC LIMIT $limit",
                    {"limit": int(limit)},
                )
                return self._extract_list(res)
            except Exception as e:
                logging.error(f"Failed to list loop runs from SurrealDB: {e}")
                raise RuntimeError(f"Failed to list loop runs from SurrealDB: {e}")
        else:
            try:
                with self._sqlite_conn() as conn:
                    cursor = conn.cursor()
                    cursor.execute(
                        "SELECT * FROM loop_runs ORDER BY id DESC LIMIT ?", (int(limit),)
                    )
                    return [dict(row) for row in cursor.fetchall()]
            except sqlite3.Error as e:
                logging.error(f"Failed to list loop runs: {e}")
                raise RuntimeError(f"Failed to list loop runs: {e}")

    def list_decisions(self, limit: int = 20) -> List[Dict[str, Any]]:
        """List logged decisions, most recent first."""
        if self.backend == "surrealdb":
            try:
                res = self.db.query(
                    "SELECT * FROM decisions ORDER BY created_at DESC LIMIT $limit",
                    {"limit": int(limit)},
                )
                return self._extract_list(res)
            except Exception as e:
                logging.error(f"Failed to list decisions from SurrealDB: {e}")
                raise RuntimeError(f"Failed to list decisions from SurrealDB: {e}")
        else:
            try:
                with self._sqlite_conn() as conn:
                    cursor = conn.cursor()
                    cursor.execute(
                        "SELECT * FROM decisions ORDER BY id DESC LIMIT ?", (int(limit),)
                    )
                    return [dict(row) for row in cursor.fetchall()]
            except sqlite3.Error as e:
                logging.error(f"Failed to list decisions: {e}")
                raise RuntimeError(f"Failed to list decisions: {e}")

    def list_handoffs(self, limit: int = 20) -> List[Dict[str, Any]]:
        """List handoff log entries, most recent first."""
        if self.backend == "surrealdb":
            try:
                res = self.db.query(
                    "SELECT * FROM handoffs ORDER BY timestamp DESC LIMIT $limit",
                    {"limit": int(limit)},
                )
                return self._extract_list(res)
            except Exception as e:
                logging.error(f"Failed to list handoffs from SurrealDB: {e}")
                raise RuntimeError(f"Failed to list handoffs from SurrealDB: {e}")
        else:
            try:
                with self._sqlite_conn() as conn:
                    cursor = conn.cursor()
                    cursor.execute(
                        "SELECT * FROM handoffs ORDER BY id DESC LIMIT ?", (int(limit),)
                    )
                    return [dict(row) for row in cursor.fetchall()]
            except sqlite3.Error as e:
                logging.error(f"Failed to list handoffs: {e}")
                raise RuntimeError(f"Failed to list handoffs: {e}")

    # ----------------------------------------------------------------------
    # Multi-model SurrealDB: graph, timeseries, and vector.
    #
    # SurrealDB is used as a true multi-model store. The relational tables and
    # their indexes live in the init block; the methods below add the graph
    # (RELATE edges + traversals), timeseries (the metrics table and bucketed
    # aggregation), and vector (HNSW KNN over memory embeddings) models. The graph
    # and vector models have no SQLite equivalent and raise on the fallback
    # backend; record_metric/query_metric also work on SQLite so statistics
    # survive an outage.
    # ----------------------------------------------------------------------

    # The graph RELATION edge tables DEFINEd in the init block. The generic
    # ``relate`` accepts any safe identifier, but only these are pre-defined.
    _RELATION_EDGES = (
        "blocks", "supersedes", "contains", "produced", "addresses", "worked_on",
    )
    _IDENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
    # Time buckets accepted by SurrealDB's ``time::group`` that floor cleanly.
    # ``week`` is excluded: it returns a null bucket on v3.x.
    _TS_BUCKETS = ("minute", "hour", "day", "month", "year")
    _METRIC_AGGS = {
        "count": "count()",
        "mean": "math::mean(value)",
        "sum": "math::sum(value)",
        "min": "math::min(value)",
        "max": "math::max(value)",
    }

    def _require_surreal(self, feature: str) -> None:
        """Guard a SurrealDB-only model, raising a clear error on the fallback."""
        if self.backend != "surrealdb":
            raise RuntimeError(f"{feature} requires the SurrealDB backend")

    @classmethod
    def _safe_ident(cls, name: str, what: str = "identifier") -> str:
        """Validate an interpolated identifier (edge or field name) against injection."""
        if not cls._IDENT.match(str(name)):
            raise ValueError(f"unsafe {what}: {name!r}")
        return str(name)

    @classmethod
    def _as_rid(cls, table: str, value: Any) -> Any:
        """Coerce ``value`` into a RecordID in ``table``.

        Accepts a RecordID, a full ``table:key`` string (as the public save methods
        return), or a bare natural key (a github_id, session_id, or minted id).

        SurrealDB wraps a complex record id in angle-bracket delimiters (U+27E8 and
        U+27E9), or backticks, when it stringifies it (e.g. a minted decision id);
        those delimiters are stripped so the rebuilt RecordID matches the stored
        record instead of a literally-bracketed key. The actual binary key is never
        bracketed. :meth:`_parse_rid` applies the same stripping for ``table:key``
        inputs; this method additionally accepts a bare natural key with no table
        prefix, which the graph helpers pass.
        """
        if type(value).__name__ == "RecordID":
            return value
        s = str(value)
        if ":" in s:
            tbl, _, key = s.partition(":")
            key = key.strip()
            if len(key) >= 2 and key[0] == "⟨" and key[-1] == "⟩":
                key = key[1:-1]
            elif len(key) >= 2 and key[0] == "`" and key[-1] == "`":
                key = key[1:-1]
            return cls._rid(tbl, key)
        return cls._rid(table, value)

    @staticmethod
    def _coerce_dt(at: Any) -> Optional[datetime.datetime]:
        """Coerce a datetime or ISO-8601 string into a timezone-aware datetime."""
        if at is None:
            return None
        if isinstance(at, datetime.datetime):
            return at
        return datetime.datetime.fromisoformat(str(at).replace("Z", "+00:00"))

    @classmethod
    def _coerce_dt_iso(cls, at: Any) -> Optional[str]:
        """Coerce a datetime or ISO string into an ISO-8601 string (SQLite storage)."""
        dt = cls._coerce_dt(at)
        return dt.isoformat() if dt else None

    # --- Graph ---------------------------------------------------------------

    # Parameter names the RELATE statement itself owns; an edge field with one
    # of these names would silently overwrite the endpoint or identity binding.
    _RESERVED_EDGE_PARAMS = frozenset({"rel_from", "rel_to", "record_id", "id"})

    def relate(self, edge: str, from_id: Any, to_id: Any, **fields: Any) -> Optional[str]:
        """Create a graph edge ``from_id -[edge]-> to_id`` and return its record id.

        ``from_id``/``to_id`` are RecordIDs or ``table:key`` strings (the typed
        helpers below build them from natural keys). Extra keyword fields are
        stored on the edge record.

        Routed through the durability funnel (kind ``edge``, ADR-0016 F5): the
        minted edge id is stamped on the edge as ``record_id``, and during an
        outage of the configured primary the pending mirror carries the edge to
        :meth:`reconcile`, which replays it as an idempotent RELATE
        (check-before-create on that stamp). The graph model has no SQLite
        representation, so with no SurrealDB primary configured at all this
        still raises the graph guard -- there would be nothing to replay into.
        """
        if self.backend != "surrealdb" and self._surreal_class is None:
            self._require_surreal("graph relations")
        edge = self._safe_ident(edge, "edge name")
        for key in fields:
            self._safe_ident(key, "edge field")
            if key in self._RESERVED_EDGE_PARAMS:
                raise ValueError(f"reserved edge field name: {key!r}")
        record_id = self._mint_id("edge")
        payload = {
            "edge": edge,
            "from_id": str(from_id),
            "to_id": str(to_id),
            "fields": dict(fields),
            "record_id": record_id,
        }
        result = self._write_through("edge", record_id, payload, self._db_relate)
        return result if result is not None else record_id

    @_resilient
    def _db_relate(self, record_id: str, payload: Dict[str, Any]) -> Optional[str]:
        """Persist an edge: RELATE with the minted id stamped as record_id.

        On the degraded fallback (the configured primary is down and the
        resilient wrapper switched to SQLite) this is a no-op: the pending
        mirror is the durable copy and reconcile replays it.
        """
        if self.backend != "surrealdb":
            return None
        query, params = self._relate_statement(payload, record_id)
        try:
            res = self._run_surreal(query, params)
            return self._extract_id(res)
        except _ConnectionLost:
            raise
        except Exception as e:
            logging.error(f"Failed to relate in SurrealDB: {e}")
            raise RuntimeError(f"Failed to relate in SurrealDB: {e}")

    def _relate_statement(self, payload: Dict[str, Any], record_id: str) -> tuple:
        """Build the RELATE query and params for a live write or a replay."""
        edge = self._safe_ident(payload["edge"], "edge name")
        params: Dict[str, Any] = {
            "rel_from": self._parse_rid(payload["from_id"]),
            "rel_to": self._parse_rid(payload["to_id"]),
            "record_id": record_id,
        }
        assignments = ["record_id = $record_id"]
        for key, val in (payload.get("fields") or {}).items():
            self._safe_ident(key, "edge field")
            assignments.append(f"{key} = ${key}")
            params[key] = val
        query = f"RELATE $rel_from->{edge}->$rel_to SET {', '.join(assignments)};"
        return query, params

    def _traverse(self, rid: Any, path: str) -> List[Dict[str, Any]]:
        """Return the distinct target records of a one-hop traversal from ``rid``.

        ``path`` is a fixed internal traversal idiom (e.g. ``->blocks->issues``),
        never caller input. Records are deduplicated and normalized.
        """
        self._require_surreal("graph traversal")
        query = f"SELECT array::distinct({path}.*) AS items FROM $node;"
        res = self._run_surreal(query, {"node": rid})
        items = self._extract_field(res, "items") or []
        return [self._normalize(r) for r in items if isinstance(r, dict)]

    def block_issue(self, blocker_github_id: Any, blocked_github_id: Any, reason: Optional[str] = None) -> Optional[str]:
        """Record that one issue blocks another (issue -[blocks]-> issue)."""
        fields = {"reason": reason} if reason else {}
        return self.relate(
            "blocks", self._rid("issues", blocker_github_id), self._rid("issues", blocked_github_id), **fields
        )

    def supersede_decision(self, new_decision_id: Any, old_decision_id: Any, reason: Optional[str] = None) -> Optional[str]:
        """Record that a newer decision supersedes an older one (decision -[supersedes]-> decision)."""
        fields = {"reason": reason} if reason else {}
        return self.relate(
            "supersedes", self._as_rid("decisions", new_decision_id), self._as_rid("decisions", old_decision_id), **fields
        )

    def assign_issue_to_milestone(self, milestone_id: Any, github_id: Any) -> Optional[str]:
        """Place an issue under a milestone (milestone -[contains]-> issue)."""
        return self.relate("contains", self._as_rid("milestones", milestone_id), self._rid("issues", github_id))

    def link_session_handoff(self, session_id: Any, handoff_id: Any) -> Optional[str]:
        """Record that a session produced a handoff (session -[produced]-> handoff)."""
        return self.relate("produced", self._as_rid("sessions", session_id), self._as_rid("handoffs", handoff_id))

    @staticmethod
    def _canonical_issue_number(value: Any) -> str:
        """Validate and canonicalize a GitHub issue number to its digit string.

        Same digits-only, ASCII-only rule as :func:`is_github_issue`; leading
        zeros are dropped. Raises ``ValueError`` on anything else, so a bad
        number can never reach a query or the graph.
        """
        s = str(value)
        if not (s.isdigit() and s.isascii()):
            raise ValueError(f"invalid GitHub issue number: {value!r}")
        return str(int(s))

    def _record_worked_on(self, source_table: str, source_key: str, gid: str) -> None:
        """Link one episodic row (session or loop run) to the issue it advanced.

        The worked_on edge (ADR-0018): ``<source_table>:<source_key> ->
        worked_on -> issues:<gid>``. A missing issue row is first created
        minimally through the log_issue path so the edge never dangles. On
        SurrealDB the edge rides the wave-1 mirrored relate funnel (ADR-0016
        F5), with a check-before-relate so re-saving a session does not
        duplicate the edge. Whenever the write cannot land on the primary
        (pure-SQLite, or the degraded fallback -- where relate still mirrors
        the edge as pending for replay) a parity row in the SQLite worked_on
        link table keeps graph-based resume working.
        """
        if self.get_issue(gid) is None:
            self.log_issue(gid, f"GitHub issue #{gid}", "issue", "open", None)
        if self.backend == "surrealdb" or self._surreal_class is not None:
            if not (
                self.backend == "surrealdb"
                and gid in self._worked_on_targets(source_table, source_key)
            ):
                self.relate(
                    "worked_on",
                    self._rid(source_table, source_key),
                    self._rid("issues", gid),
                )
        if self.backend != "surrealdb":
            self._sqlite_link_worked_on(source_table, source_key, gid)

    def _worked_on_targets(self, source_table: str, source_key: str) -> List[str]:
        """github_ids already linked from a source row (live-SurrealDB only).

        Best-effort: any read failure reports no targets, so the caller
        proceeds to relate (the resilient write path handles the fault).
        """
        try:
            res = self._run_surreal(
                "SELECT array::distinct(->worked_on->issues.github_id) AS gids "
                "FROM $node;",
                {"node": self._rid(source_table, source_key)},
            )
            return [str(g) for g in (self._extract_field(res, "gids") or [])]
        except Exception:
            return []

    def _sqlite_link_worked_on(
        self, source_table: str, source_id: str, github_id: str
    ) -> None:
        """Write one worked_on parity row; idempotent via the unique link index."""
        query = (
            "INSERT OR IGNORE INTO worked_on "
            "(record_id, source_table, source_id, github_id) VALUES (?, ?, ?, ?)"
        )
        try:
            with self._sqlite_conn() as conn:
                conn.execute(
                    query, (self._mint_id("edge"), source_table, source_id, github_id)
                )
                conn.commit()
        except sqlite3.Error as e:
            logging.error(f"Failed to link worked_on: {e}")
            raise RuntimeError(f"Failed to link worked_on: {e}")

    def decision_addresses_issue(self, decision_id: Any, github_id: Any) -> Optional[str]:
        """Record that a decision addresses an issue (decision -[addresses]-> issue)."""
        return self.relate("addresses", self._as_rid("decisions", decision_id), self._rid("issues", github_id))

    @_resilient
    def issues_blocking(self, github_id: Any) -> List[Dict[str, Any]]:
        """Issues that THIS issue blocks (outgoing ``->blocks->``)."""
        return self._traverse(self._rid("issues", github_id), "->blocks->issues")

    @_resilient
    def issues_blocked_by(self, github_id: Any) -> List[Dict[str, Any]]:
        """Issues that block THIS issue (incoming ``<-blocks<-``)."""
        return self._traverse(self._rid("issues", github_id), "<-blocks<-issues")

    @_resilient
    def milestone_issues(self, milestone_id: Any) -> List[Dict[str, Any]]:
        """Issues contained by a milestone (``->contains->``)."""
        return self._traverse(self._as_rid("milestones", milestone_id), "->contains->issues")

    @_resilient
    def supersedes_chain(self, decision_id: Any) -> List[Dict[str, Any]]:
        """The transitive chain of decisions a decision supersedes, nearest first.

        Walks ``->supersedes->decisions`` breadth-first with a visited guard, so a
        cyclic graph terminates instead of looping forever.
        """
        self._require_surreal("graph traversal")
        chain: List[Dict[str, Any]] = []
        seen = set()
        frontier = [self._as_rid("decisions", decision_id)]
        while frontier:
            current = frontier.pop(0)
            for rec in self._traverse(current, "->supersedes->decisions"):
                rid = str(rec.get("id"))
                if rid in seen:
                    continue
                seen.add(rid)
                chain.append(rec)
                frontier.append(self._as_rid("decisions", rid))
        return chain

    # --- Timeseries ----------------------------------------------------------

    def record_metric(self, name: str, value: float, tags: Optional[Dict[str, Any]] = None, at: Any = None) -> Union[str, int, None]:
        """Append one timeseries metric point (name, value, tags, time).

        Works on BOTH backends so statistics survive a SQLite fallback, and is
        routed through the durability funnel (kind ``metric``, ADR-0016 F5):
        during an outage the point lands in the fallback metrics table AND a
        pending mirror, which reconcile replays to the primary with its
        ORIGINAL time. ``at`` is an optional datetime or ISO-8601 string; it
        defaults to the write time, stamped client-side in UTC so the mirror,
        the fallback row, and the replay all carry the same instant. Returns
        the client-minted record id on both backends (F7).
        """
        fields = {
            "name": name,
            "value": float(value),
            "tags": tags or {},
            "time": self._coerce_dt_iso(at) or self._utc_iso(),
        }
        return self._write_through(
            "metric", self._mint_id("metric"), fields, self._db_record_metric
        )

    @_resilient
    def _db_record_metric(
        self, record_id: str, fields: Dict[str, Any]
    ) -> Union[str, int, None]:
        """Persist a metric point: minted id, idempotent UPSERT on SurrealDB."""
        if self.backend == "surrealdb":
            query = (
                "UPSERT $id CONTENT "
                "{name: $name, value: $value, tags: $tags, time: $time};"
            )
            params = {
                "id": self._rid("metrics", record_id),
                "name": fields["name"],
                "value": fields["value"],
                "tags": fields["tags"],
                "time": self._coerce_dt(fields["time"]),
            }
            try:
                res = self._run_surreal(query, params)
                return self._extract_id(res) or record_id
            except _ConnectionLost:
                raise
            except Exception as e:
                logging.error(f"Failed to record metric in SurrealDB: {e}")
                raise RuntimeError(f"Failed to record metric in SurrealDB: {e}")
        else:
            query = (
                "INSERT INTO metrics (record_id, name, value, tags, time) "
                "VALUES (?, ?, ?, ?, ?)"
            )
            try:
                with self._sqlite_conn() as conn:
                    conn.execute(
                        query,
                        (
                            record_id,
                            fields["name"],
                            fields["value"],
                            json.dumps(fields["tags"]),
                            fields["time"],
                        ),
                    )
                    conn.commit()
                    return record_id
            except sqlite3.Error as e:
                logging.error(f"Failed to record metric: {e}")
                raise RuntimeError(f"Failed to record metric: {e}")

    @_resilient
    def query_metric(self, name: str, since: Any = None, until: Any = None, limit: int = 100) -> List[Dict[str, Any]]:
        """Return metric points for ``name``, most recent first.

        Works on both backends. ``since``/``until`` bound the sample time
        (inclusive); each is a datetime or ISO-8601 string.
        """
        if self.backend == "surrealdb":
            clauses = ["name = $name"]
            params: Dict[str, Any] = {"name": name}
            if since is not None:
                clauses.append("time >= $since")
                params["since"] = self._coerce_dt(since)
            if until is not None:
                clauses.append("time <= $until")
                params["until"] = self._coerce_dt(until)
            where = " AND ".join(clauses)
            params["limit"] = int(limit)
            query = f"SELECT * FROM metrics WHERE {where} ORDER BY time DESC LIMIT $limit;"
            try:
                res = self._run_surreal(query, params)
                return self._extract_list(res)
            except _ConnectionLost:
                raise
            except Exception as e:
                logging.error(f"Failed to query metric in SurrealDB: {e}")
                raise RuntimeError(f"Failed to query metric in SurrealDB: {e}")
        else:
            clauses = ["name = ?"]
            args: List[Any] = [name]
            if since is not None:
                clauses.append("time >= ?")
                args.append(self._coerce_dt_iso(since))
            if until is not None:
                clauses.append("time <= ?")
                args.append(self._coerce_dt_iso(until))
            where = " AND ".join(clauses)
            query = f"SELECT name, value, tags, time FROM metrics WHERE {where} ORDER BY time DESC LIMIT ?"
            args.append(int(limit))
            try:
                with self._sqlite_conn() as conn:
                    cursor = conn.cursor()
                    cursor.execute(query, args)
                    rows = [dict(row) for row in cursor.fetchall()]
            except sqlite3.Error as e:
                logging.error(f"Failed to query metric: {e}")
                raise RuntimeError(f"Failed to query metric: {e}")
            for row in rows:
                if row.get("tags"):
                    try:
                        row["tags"] = json.loads(row["tags"])
                    except (json.JSONDecodeError, TypeError):
                        pass
            return rows

    @_resilient
    def aggregate_metric(self, name: str, bucket: str = "day", agg: str = "count", since: Any = None) -> List[Dict[str, Any]]:
        """Aggregate a metric into time buckets (SurrealDB-only).

        ``bucket`` is one of ``minute|hour|day|month|year``; ``agg`` is one of
        ``count|mean|sum|min|max``. Returns ``[{"bucket", "value"}, ...]`` sorted by
        bucket. Uses SurrealDB ``time::group`` bucketing.
        """
        self._require_surreal("metric aggregation")
        if bucket not in self._TS_BUCKETS:
            raise ValueError(f"unsupported bucket: {bucket!r}")
        if agg not in self._METRIC_AGGS:
            raise ValueError(f"unsupported aggregation: {agg!r}")
        agg_expr = self._METRIC_AGGS[agg]
        params: Dict[str, Any] = {"name": name, "bucket": bucket}
        since_clause = ""
        if since is not None:
            since_clause = "AND time >= $since "
            params["since"] = self._coerce_dt(since)
        query = (
            f"SELECT time::group(time, $bucket) AS bucket, {agg_expr} AS value "
            f"FROM metrics WHERE name = $name {since_clause}GROUP BY bucket;"
        )
        res = self._run_surreal(query, params)
        rows = self._extract_list(res)
        rows.sort(key=lambda r: str(r.get("bucket")))
        return rows

    @_resilient
    def loop_run_throughput(self, bucket: str = "day", since: Any = None) -> List[Dict[str, Any]]:
        """Loop-run counts per time bucket over the loop_runs ledger (SurrealDB-only)."""
        self._require_surreal("loop-run aggregation")
        if bucket not in self._TS_BUCKETS:
            raise ValueError(f"unsupported bucket: {bucket!r}")
        params: Dict[str, Any] = {"bucket": bucket}
        where = ""
        if since is not None:
            where = "WHERE created_at >= $since "
            params["since"] = self._coerce_dt(since)
        query = (
            f"SELECT time::group(created_at, $bucket) AS bucket, count() AS count "
            f"FROM loop_runs {where}GROUP BY bucket;"
        )
        res = self._run_surreal(query, params)
        rows = self._extract_list(res)
        rows.sort(key=lambda r: str(r.get("bucket")))
        return rows

    @_resilient
    def loop_run_failure_rate(self, since: Any = None) -> Dict[str, Any]:
        """Failure rate of loop runs (SurrealDB-only).

        Returns ``{"total", "failures", "failure_rate"}`` where ``failure_rate`` is
        ``failures / total`` (0.0 when there are no runs). A run counts as a failure
        when its ``status`` is the canonical ``failed`` OR the legacy ``failure``
        token: rows recorded before the vocabulary fix must not vanish from the
        metric (#165, ADR-0016).
        """
        self._require_surreal("loop-run aggregation")
        params: Dict[str, Any] = {}
        where = ""
        if since is not None:
            where = "WHERE created_at >= $since "
            params["since"] = self._coerce_dt(since)
        query = (
            f"SELECT count() AS total, count(status IN ['failed', 'failure']) AS failures "
            f"FROM loop_runs {where}GROUP ALL;"
        )
        res = self._run_surreal(query, params)
        rec = self._extract_record(res) or {}
        total = rec.get("total", 0) or 0
        failures = rec.get("failures", 0) or 0
        rate = (failures / total) if total else 0.0
        return {"total": total, "failures": failures, "failure_rate": rate}

    # --- Vector --------------------------------------------------------------

    @_resilient
    def semantic_search(self, query: str, k: int = 5, category: Optional[str] = None, ef: int = 64) -> List[Dict[str, Any]]:
        """Return the ``k`` memory entries nearest to ``query`` (SurrealDB-only).

        Nearness is cosine distance over the stored embedding via the HNSW index
        and SurrealDB's ``<|k, EF|>`` KNN operator (``ef`` is the search breadth).
        With the default :class:`HashingEmbedder` this is LEXICAL nearness (shared
        tokens), not semantic; swap in a model-backed embedder for true meaning.
        By default the non-semantic categories (the code index, the board
        history) are excluded so results carry meaning, not file blobs; an
        explicit ``category`` argument is honored verbatim, including one of the
        excluded categories (ADR-0016, F6). Results are
        ``[{"key", "value", "category", "distance"}, ...]`` nearest first.
        """
        self._require_surreal("semantic search")
        q_vec = self._embedder.embed(query)
        params: Dict[str, Any] = {"q": q_vec}
        if category is not None:
            cat_clause = "category = $category AND "
            params["category"] = category
        else:
            cat_clause = "category NOT IN $excluded AND "
            params["excluded"] = list(NON_SEMANTIC_MEMORY_CATEGORIES)
        knn = f"<|{int(k)},{int(ef)}|>"
        sql = (
            f"SELECT key, value, category, vector::distance::knn() AS distance "
            f"FROM memory WHERE {cat_clause}embedding {knn} $q ORDER BY distance;"
        )
        res = self._run_surreal(sql, params)
        return self._extract_list(res)

    def close(self) -> None:
        """Closes the database client and any open connections."""
        if self.backend == "surrealdb" and self.db:
            try:
                self.db.close()
            except Exception:
                pass
            self.db = None

    def __enter__(self) -> "DatabaseClient":
        return self

    def __exit__(
        self,
        exc_type: Optional[Any],
        exc_val: Optional[BaseException],
        exc_tb: Optional[Any],
    ) -> None:
        self.close()
