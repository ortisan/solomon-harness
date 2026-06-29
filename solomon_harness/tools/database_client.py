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
# here (Ideas, Backlog, Ready, the legacy literal open) passes through unchanged.
_STATUS_ALIASES = {
    "in progress": "in_progress",
    "in_progress": "in_progress",
    "code review": "code_review",
    "code_review": "code_review",
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
        # The embedder that vectorizes memory for the HNSW vector index. The default
        # is lexical (token overlap), swappable for a real semantic model.
        self._embedder: Embedder = embedder or HashingEmbedder()

        self.backend = "sqlite"
        self.db = None
        self.spectron = None
        self.db_path = db_path
        # The explicit db_path argument (kept distinct from the resolved store path)
        # marks a test/sandbox-isolated client, used to keep the mirror beside it.
        self._db_path_param = db_path

        # SurrealDB connection params captured so the connection can be rebuilt
        # mid-session after a drop, not only at construction (issue #37).
        self._surreal_class: Any = None
        self._surreal_url: Optional[str] = None
        self._surreal_username: Optional[str] = None
        self._surreal_password: Optional[str] = None
        self._surreal_namespace: Optional[str] = None
        self._surreal_database: Optional[str] = None
        self._connect_deadline: float = 5.0

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
        # path the constructor would have used (issue #37).
        self._project_root = project_root

        # Root for the write-through Markdown mirror (issue #35). Resolved once, up
        # front, so every write funnels to the same gitignored local store.
        self._mirror_root = self._resolve_mirror_root(mirror_root)

        # Load configuration. Prefer the harness-local .agent/config.json, which carries
        # the per-agent `database` block, and fall back to the project-root config.
        config: Dict[str, Any] = {}
        candidate_config_paths = [
            os.path.join(harness_dir, ".agent", "config.json"),
            os.path.join(project_root, ".agent", "config.json"),
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
        provider = db_config.get("provider")
        self.busy_timeout_seconds = float(db_config.get("busy_timeout_seconds", 5.0))

        # Retained for read-only tenant discovery (list_databases). On the SQLite
        # fallback the resolvable tenant is derived from these, not from the store.
        self._project_root = project_root
        self._configured_database = db_config.get("database")
        # The SurrealDB namespace that holds every tenant database. Stored so the
        # read-only use_tenant() accessor can rebind the connection scope to the
        # selected tenant with the same parameterized SDK bind the constructor uses.
        self._namespace = db_config.get("namespace", "solomon")

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
                password = password or "root"
            creds_ok = bool(username and password)

            if has_surrealdb and Surreal is not None and creds_ok:
                namespace = self._namespace
                database = _resolve_database(db_config.get("database"), project_root)

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
                        # SurrealDB is used as a true multi-model store: relational
                        # tables with indexes, graph RELATION edges, a timeseries
                        # metrics table, and an HNSW vector index for semantic memory.
                        # Every DEFINE is IF NOT EXISTS (idempotent) and SCHEMALESS, so
                        # it never rejects the existing string-typed writes.
                        init_query = (
                            "DEFINE TABLE IF NOT EXISTS decisions SCHEMALESS; "
                            "DEFINE TABLE IF NOT EXISTS memory SCHEMALESS; "
                            "DEFINE TABLE IF NOT EXISTS milestones SCHEMALESS; "
                            "DEFINE TABLE IF NOT EXISTS issues SCHEMALESS; "
                            "DEFINE TABLE IF NOT EXISTS backtest_runs SCHEMALESS; "
                            "DEFINE TABLE IF NOT EXISTS sessions SCHEMALESS; "
                            "DEFINE TABLE IF NOT EXISTS handoffs SCHEMALESS; "
                            "DEFINE TABLE IF NOT EXISTS releases SCHEMALESS; "
                            "DEFINE TABLE IF NOT EXISTS loop_runs SCHEMALESS; "
                            "DEFINE TABLE IF NOT EXISTS metrics SCHEMALESS; "
                            # Graph: typed RELATION edge tables.
                            "DEFINE TABLE IF NOT EXISTS blocks TYPE RELATION; "
                            "DEFINE TABLE IF NOT EXISTS supersedes TYPE RELATION; "
                            "DEFINE TABLE IF NOT EXISTS contains TYPE RELATION; "
                            "DEFINE TABLE IF NOT EXISTS produced TYPE RELATION; "
                            "DEFINE TABLE IF NOT EXISTS addresses TYPE RELATION; "
                            # Relational: indexes for the hot lookups. github_id is the
                            # record key, so it is unique by construction.
                            "DEFINE INDEX IF NOT EXISTS issues_github_id "
                            "ON issues FIELDS github_id UNIQUE; "
                            "DEFINE INDEX IF NOT EXISTS issues_status "
                            "ON issues FIELDS status; "
                            "DEFINE INDEX IF NOT EXISTS decisions_created_at "
                            "ON decisions FIELDS created_at; "
                            # Timeseries: composite index on (name, time) for metrics.
                            "DEFINE INDEX IF NOT EXISTS metrics_name_time "
                            "ON metrics FIELDS name, time; "
                            # Vector: HNSW index over the 256-dim memory embedding.
                            "DEFINE INDEX IF NOT EXISTS memory_embedding ON memory "
                            f"FIELDS embedding HNSW DIMENSION {EMBEDDING_DIM} "
                            "DIST COSINE TYPE F32;"
                        )
                        self.db.query(init_query)
                        self.backend = "surrealdb"

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
                else:
                    sys.stderr.write("Warning: Connection to SurrealDB failed.\n")
                    sys.stderr.write(
                        "SurrealDB library or server unavailable. Falling back to SQLite backend.\n"
                    )
                    self.backend = "sqlite"
            else:
                if not creds_ok:
                    sys.stderr.write(
                        "SurrealDB credentials are not set for a non-local URL; set "
                        "SURREAL_USER/SURREAL_PASS. Falling back to SQLite backend.\n"
                    )
                else:
                    sys.stderr.write(
                        "SurrealDB library or server unavailable. Falling back to SQLite backend.\n"
                    )
                self.backend = "sqlite"

        # Initialize SQLite if backend is sqlite
        if self.backend == "sqlite":
            if self.db_path is None:
                self.db_path = self._resolve_sqlite_path()
            self._init_sqlite_db()

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
                title TEXT NOT NULL,
                description TEXT,
                due_date TEXT,
                state TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            """,
            """
            CREATE TABLE IF NOT EXISTS issues (
                github_id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                type_ TEXT,
                status TEXT,
                milestone_id INTEGER,
                assignee TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (milestone_id) REFERENCES milestones (id)
            );
            """,
            """
            CREATE TABLE IF NOT EXISTS backtest_runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
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
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            """,
            """
            CREATE TABLE IF NOT EXISTS handoffs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                sender TEXT,
                recipient TEXT,
                contract_type TEXT,
                contract_path TEXT,
                status TEXT,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            """,
            """
            CREATE TABLE IF NOT EXISTS releases (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
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
                stage TEXT,
                target TEXT,
                decision TEXT,
                status TEXT,
                session_id TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            """,
            # Timeseries metrics, mirrored on the SQLite fallback so recorded
            # statistics survive a backend outage. ``tags`` holds JSON, ``time`` an
            # ISO-8601 string; the composite index matches the SurrealDB layout.
            """
            CREATE TABLE IF NOT EXISTS metrics (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                value REAL,
                tags TEXT,
                time TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            """,
            "CREATE INDEX IF NOT EXISTS metrics_name_time ON metrics (name, time);",
        ]

        try:
            with self._sqlite_conn() as conn:
                cursor = conn.cursor()
                for query in queries:
                    cursor.execute(query)
                self._ensure_issue_assignee_column(conn)
                conn.commit()
        except sqlite3.Error as e:
            logging.error(f"SQLite database initialization failed: {e}")
            raise RuntimeError(f"SQLite database initialization failed: {e}")

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
        """Idempotently UPSERT a mirrored record into the SurrealDB primary.

        The UPSERT is keyed by the record's stored id, so replaying a record that
        is already present updates it in place rather than duplicating it. The
        original mirror ``created_at`` is preserved as the record's time field so a
        replayed row sorts where it belongs. Raises ``_ConnectionLost`` on a
        transport fault so :meth:`reconcile` can stop and leave the rest pending.
        """
        kind = meta["kind"]
        table = self._KIND_TABLE[kind]
        content = dict(payload)
        content[self._KIND_TIMEFIELD.get(kind, "created_at")] = meta.get("created_at")
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
            INSERT INTO decisions (title, rationale, outcome, author, branch, commit_sha)
            VALUES (?, ?, ?, ?, ?, ?)
            """
            try:
                with self._sqlite_conn() as conn:
                    cursor = conn.cursor()
                    cursor.execute(
                        query,
                        (
                            fields["title"],
                            fields["rationale"],
                            fields["outcome"],
                            fields["author"],
                            fields["branch"],
                            fields["commit_sha"],
                        ),
                    )
                    conn.commit()
                    return cursor.lastrowid
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
            embedding = self._embedder.embed(f"{key} {value}")
            query = """
            UPSERT $id CONTENT {
                key: $key,
                value: $value,
                category: $category,
                embedding: $embedding,
                updated_at: time::now()
            };
            """
            params = {
                "id": self._rid("memory", record_id),
                "key": key,
                "value": value,
                "category": category,
                "embedding": embedding,
            }
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

    @_resilient
    def delete_memory(self, key: str) -> None:
        """Deletes a memory entry by key (no-op if it does not exist)."""
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

    def create_milestone(
        self, title: str, description: str, due_date: str, state: str
    ) -> Union[str, int, None]:
        """Creates a project milestone record.

        Args:
            title: Milestone title.
            description: Detailed objective list.
            due_date: Target completion date.
            state: Active state (e.g., active, complete, pending).

        Returns:
            The primary key ID or record ID of the created milestone.
        """
        fields = {
            "title": title,
            "description": description,
            "due_date": due_date,
            "state": state,
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
            INSERT INTO milestones (title, description, due_date, state)
            VALUES (?, ?, ?, ?)
            """
            try:
                with self._sqlite_conn() as conn:
                    cursor = conn.cursor()
                    cursor.execute(
                        query,
                        (
                            fields["title"],
                            fields["description"],
                            fields["due_date"],
                            fields["state"],
                        ),
                    )
                    conn.commit()
                    return cursor.lastrowid
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
        return self._write_through(
            "release", self._mint_id("release"), fields, self._db_save_release
        )

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
                (version, tag, notes, issue_github_id, milestone_id, commit_sha)
            VALUES (?, ?, ?, ?, ?, ?)
            """
            try:
                with self._sqlite_conn() as conn:
                    cursor = conn.cursor()
                    cursor.execute(
                        query,
                        (
                            fields["version"],
                            fields["tag"],
                            fields["notes"],
                            fields["issue_github_id"],
                            fields["milestone_id"],
                            fields["commit_sha"],
                        ),
                    )
                    conn.commit()
                    return cursor.lastrowid
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
                    cursor.execute("SELECT * FROM releases WHERE id = ?", (release_id,))
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
                    f"SELECT * FROM releases ORDER BY released_at DESC LIMIT {int(limit)}"
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
            INSERT INTO backtest_runs (strategy_name, sharpe_ratio, max_drawdown, profit_factor, parameters, dataset, commit_sha)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """
            try:
                with self._sqlite_conn() as conn:
                    cursor = conn.cursor()
                    cursor.execute(
                        query,
                        (
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
                    return cursor.lastrowid
            except sqlite3.Error as e:
                logging.error(f"Failed to save backtest run: {e}")
                raise RuntimeError(f"Failed to save backtest run: {e}")

    def save_session(
        self,
        session_id: str,
        agent_name: str,
        task: str,
        messages: Union[List[Dict[str, Any]], str],
    ) -> None:
        """Upserts a short-term session state.

        Args:
            session_id: Unique identifier for the session.
            agent_name: Name of the agent.
            task: Task description.
            messages: List of message dictionaries representing conversation history.
        """
        fields = {
            "session_id": session_id,
            "agent_name": agent_name,
            "task": task,
            "messages": messages,
        }
        # session_id is already a stable id, reused for the RecordID and filename.
        self._write_through("session", session_id, fields, self._db_save_session)

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
                timestamp: time::now()
            };
            """
            params = {
                "id": self._rid("sessions", record_id),
                "session_id": fields["session_id"],
                "agent_name": fields["agent_name"],
                "task": fields["task"],
                "messages": fields["messages"],
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
            INSERT INTO sessions (session_id, agent_name, task, messages, timestamp)
            VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(session_id) DO UPDATE SET
                agent_name=excluded.agent_name,
                task=excluded.task,
                messages=excluded.messages,
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
    ) -> Union[str, int, None]:
        """Creates a handoff log entry.

        Args:
            sender: The sender agent name.
            recipient: The recipient agent name.
            contract_type: Type of contract (e.g. plan, code).
            contract_path: File path to contract documentation.
            status: Initial status (e.g. pending, approved).

        Returns:
            The primary key ID or record ID of the created handoff.
        """
        fields = {
            "sender": sender,
            "recipient": recipient,
            "contract_type": contract_type,
            "contract_path": contract_path,
            "status": status,
        }
        return self._write_through(
            "handoff", self._mint_id("handoff"), fields, self._db_log_handoff
        )

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
            INSERT INTO handoffs (sender, recipient, contract_type, contract_path, status)
            VALUES (?, ?, ?, ?, ?)
            """
            try:
                with self._sqlite_conn() as conn:
                    cursor = conn.cursor()
                    cursor.execute(
                        query,
                        (
                            fields["sender"],
                            fields["recipient"],
                            fields["contract_type"],
                            fields["contract_path"],
                            fields["status"],
                        ),
                    )
                    conn.commit()
                    return cursor.lastrowid
            except sqlite3.Error as e:
                logging.error(f"Failed to log handoff: {e}")
                raise RuntimeError(f"Failed to log handoff: {e}")

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
            query = "SELECT * FROM handoffs WHERE id = ?"
            try:
                with self._sqlite_conn() as conn:
                    cursor = conn.cursor()
                    cursor.execute(query, (handoff_id,))
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
            query = "SELECT * FROM decisions WHERE id = ?"
            try:
                with self._sqlite_conn() as conn:
                    cursor = conn.cursor()
                    cursor.execute(query, (decision_id,))
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
            query = "SELECT * FROM milestones WHERE id = ?"
            try:
                with self._sqlite_conn() as conn:
                    cursor = conn.cursor()
                    cursor.execute(query, (milestone_id,))
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
            query = "SELECT * FROM backtest_runs WHERE id = ?"
            try:
                with self._sqlite_conn() as conn:
                    cursor = conn.cursor()
                    cursor.execute(query, (backtest_id,))
                    row = cursor.fetchone()
                    return dict(row) if row else None
            except sqlite3.Error as e:
                logging.error(f"Failed to retrieve backtest run: {e}")
                raise RuntimeError(f"Failed to retrieve backtest run: {e}")

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
            A list of dictionaries containing the non-terminal issues.
        """
        if self.backend == "surrealdb":
            query = (
                "SELECT * FROM issues "
                "WHERE status IS NONE OR status IS NULL OR status NOT IN $terminal"
            )
            try:
                res = self._run_surreal(query, {"terminal": list(TERMINAL_STATUSES)})
                return self._extract_list(res)
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
                    return [dict(row) for row in rows]
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

        Returns:
            A dictionary with keys 'type', 'agent', 'task', 'status', 'timestamp'
            (and 'contract_path' for handoffs, pointing to the handoff contract
            artifact), or None if no activity exists.
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
            return {
                "type": "session",
                "agent": latest_session.get("agent_name"),
                "task": latest_session.get("task"),
                "status": "active",
                "timestamp": latest_session.get("timestamp"),
            }
        else:
            assert latest_handoff is not None
            return {
                "type": "handoff",
                "agent": f"{latest_handoff.get('sender')} -> {latest_handoff.get('recipient')}",
                "task": latest_handoff.get("contract_type"),
                "status": latest_handoff.get("status"),
                "contract_path": latest_handoff.get("contract_path"),
                "timestamp": latest_handoff.get("timestamp"),
            }

    def save_loop_run(
        self,
        stage: str,
        target: str,
        decision: str,
        status: str,
        session_id: str,
    ) -> Union[str, int, None]:
        """Append one loop-run entry to the auditable ledger.

        Each driven stage records what it advanced and the outcome, so the loop's
        own decisions become an auditable trail. The concurrent-driver guard is
        the lockfile, not this ledger, because under the SQLite fallback each
        worktree gets a separate database and a cross-worktree count would be
        invisible.
        """
        if self.backend == "surrealdb":
            query = """
            INSERT INTO loop_runs {
                stage: $stage,
                target: $target,
                decision: $decision,
                status: $status,
                session_id: $session_id,
                created_at: time::now()
            }
            """
            params = {
                "stage": stage,
                "target": target,
                "decision": decision,
                "status": status,
                "session_id": session_id,
            }
            try:
                res = self.db.query(query, params)
                return self._extract_id(res)
            except Exception as e:
                logging.error(f"Failed to save loop run in SurrealDB: {e}")
                raise RuntimeError(f"Failed to save loop run in SurrealDB: {e}")
        else:
            query = """
            INSERT INTO loop_runs (stage, target, decision, status, session_id)
            VALUES (?, ?, ?, ?, ?)
            """
            try:
                with self._sqlite_conn() as conn:
                    cursor = conn.cursor()
                    cursor.execute(query, (stage, target, decision, status, session_id))
                    conn.commit()
                    return cursor.lastrowid
            except sqlite3.Error as e:
                logging.error(f"Failed to save loop run: {e}")
                raise RuntimeError(f"Failed to save loop run: {e}")

    def list_loop_runs(self, limit: int = 20) -> List[Dict[str, Any]]:
        """List loop runs, most recent first."""
        if self.backend == "surrealdb":
            try:
                res = self.db.query(
                    f"SELECT * FROM loop_runs ORDER BY created_at DESC LIMIT {int(limit)}"
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
                    f"SELECT * FROM decisions ORDER BY created_at DESC LIMIT {int(limit)}"
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
                    f"SELECT * FROM handoffs ORDER BY timestamp DESC LIMIT {int(limit)}"
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
    _RELATION_EDGES = ("blocks", "supersedes", "contains", "produced", "addresses")
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

    @_resilient
    def relate(self, edge: str, from_id: Any, to_id: Any, **fields: Any) -> Optional[str]:
        """Create a graph edge ``from_id -[edge]-> to_id`` and return its record id.

        ``from_id``/``to_id`` are RecordIDs or ``table:key`` strings (the typed
        helpers below build them from natural keys). Extra keyword fields are stored
        on the edge record. SurrealDB-only.
        """
        self._require_surreal("graph relations")
        edge = self._safe_ident(edge, "edge name")
        params: Dict[str, Any] = {"rel_from": self._parse_rid(from_id), "rel_to": self._parse_rid(to_id)}
        if fields:
            assignments = []
            for key, val in fields.items():
                self._safe_ident(key, "edge field")
                assignments.append(f"{key} = ${key}")
                params[key] = val
            query = f"RELATE $rel_from->{edge}->$rel_to SET {', '.join(assignments)};"
        else:
            query = f"RELATE $rel_from->{edge}->$rel_to;"
        res = self._run_surreal(query, params)
        return self._extract_id(res)

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

    @_resilient
    def record_metric(self, name: str, value: float, tags: Optional[Dict[str, Any]] = None, at: Any = None) -> Union[str, int, None]:
        """Append one timeseries metric point (name, value, tags, time).

        Works on BOTH backends so statistics survive a SQLite fallback. ``at`` is an
        optional datetime or ISO-8601 string; it defaults to the current time.
        """
        tags = tags or {}
        if self.backend == "surrealdb":
            if at is None:
                query = "CREATE metrics CONTENT {name: $name, value: $value, tags: $tags, time: time::now()};"
                params: Dict[str, Any] = {"name": name, "value": float(value), "tags": tags}
            else:
                query = "CREATE metrics CONTENT {name: $name, value: $value, tags: $tags, time: $time};"
                params = {"name": name, "value": float(value), "tags": tags, "time": self._coerce_dt(at)}
            try:
                res = self._run_surreal(query, params)
                return self._extract_id(res)
            except _ConnectionLost:
                raise
            except Exception as e:
                logging.error(f"Failed to record metric in SurrealDB: {e}")
                raise RuntimeError(f"Failed to record metric in SurrealDB: {e}")
        else:
            ts = self._coerce_dt_iso(at)
            if ts is None:
                query = "INSERT INTO metrics (name, value, tags) VALUES (?, ?, ?)"
                args: tuple = (name, float(value), json.dumps(tags))
            else:
                query = "INSERT INTO metrics (name, value, tags, time) VALUES (?, ?, ?, ?)"
                args = (name, float(value), json.dumps(tags), ts)
            try:
                with self._sqlite_conn() as conn:
                    cursor = conn.cursor()
                    cursor.execute(query, args)
                    conn.commit()
                    return cursor.lastrowid
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
            query = f"SELECT * FROM metrics WHERE {where} ORDER BY time DESC LIMIT {int(limit)};"
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
        when its ``status`` is ``failure``.
        """
        self._require_surreal("loop-run aggregation")
        params: Dict[str, Any] = {}
        where = ""
        if since is not None:
            where = "WHERE created_at >= $since "
            params["since"] = self._coerce_dt(since)
        query = (
            f"SELECT count() AS total, count(status = 'failure') AS failures "
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
        Results are ``[{"key", "value", "category", "distance"}, ...]`` nearest first.
        """
        self._require_surreal("semantic search")
        q_vec = self._embedder.embed(query)
        params: Dict[str, Any] = {"q": q_vec}
        cat_clause = ""
        if category is not None:
            cat_clause = "category = $category AND "
            params["category"] = category
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
