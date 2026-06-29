import os
import json
import sqlite3
import logging
import sys
from contextlib import contextmanager
from typing import Generator, Any, Dict, List, Optional, Union


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
        payload = {"fact": fact}
        if scope:
            payload["scope"] = scope
        resp = self.session.post(url, json=payload, timeout=self.timeout)
        resp.raise_for_status()
        return resp.json()

    def recall(self, query: str, scope: Optional[List[str]] = None) -> Any:
        url = f"{self.endpoint}/api/v1/{self.context}/query"
        payload = {"query": query}
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


class DatabaseClient:
    """A client to manage SQLite or SurrealDB database operations for the agent harness."""

    backend: str
    db: Any
    db_path: Optional[str]
    busy_timeout_seconds: float
    harness_dir: str

    def __init__(
        self, db_path: Optional[str] = None, harness_dir: Optional[str] = None
    ) -> None:
        """Initializes the database client and selects the appropriate backend.

        Args:
            db_path: Optional custom path to the SQLite database file (if using SQLite).
            harness_dir: The agent (or template) directory that owns .agent/config.json
                and the memory store. Passed explicitly by the thin agent entrypoint;
                when omitted it falls back to this file's package location.
        """
        self.backend = "sqlite"
        self.db = None
        self.spectron = None
        self.db_path = db_path

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
                namespace = db_config.get("namespace", "solomon")
                database = _resolve_database(db_config.get("database"), project_root)

                try:
                    self.db = Surreal(url)
                    if hasattr(self.db, "connect"):
                        self.db.connect()
                    # SDK 2.x uses username/password keys (1.x used user/pass).
                    self.db.signin({"username": username, "password": password})
                    self.db.use(namespace, database)

                    # Initialize SurrealDB tables. IF NOT EXISTS makes this
                    # idempotent: SurrealDB v2+ errors on re-DEFINE otherwise.
                    init_query = (
                        "DEFINE TABLE IF NOT EXISTS decisions SCHEMALESS; "
                        "DEFINE TABLE IF NOT EXISTS memory SCHEMALESS; "
                        "DEFINE TABLE IF NOT EXISTS milestones SCHEMALESS; "
                        "DEFINE TABLE IF NOT EXISTS issues SCHEMALESS; "
                        "DEFINE TABLE IF NOT EXISTS backtest_runs SCHEMALESS; "
                        "DEFINE TABLE IF NOT EXISTS sessions SCHEMALESS; "
                        "DEFINE TABLE IF NOT EXISTS handoffs SCHEMALESS; "
                        "DEFINE TABLE IF NOT EXISTS releases SCHEMALESS;"
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
                                from surrealdb import Spectron
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
                    sys.stderr.write(f"Warning: Connection to SurrealDB failed: {e}\n")
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
                # HARNESS_DB_PATH lets tests (and ad-hoc runs) redirect the SQLite
                # store to a temp file so the real project memory is never touched
                # (issue #24). Falls back to the per-project memory dir.
                env_db = os.environ.get("HARNESS_DB_PATH")
                if env_db:
                    os.makedirs(os.path.dirname(os.path.abspath(env_db)), exist_ok=True)
                    self.db_path = env_db
                else:
                    db_dir: str = os.path.join(project_root, "memory", "long_term")
                    os.makedirs(db_dir, exist_ok=True)
                    self.db_path = os.path.join(db_dir, "harness.db")
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
        ]

        try:
            with self._sqlite_conn() as conn:
                cursor = conn.cursor()
                for query in queries:
                    cursor.execute(query)
                conn.commit()
        except sqlite3.Error as e:
            logging.error(f"SQLite database initialization failed: {e}")
            raise RuntimeError(f"SQLite database initialization failed: {e}")

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
        """Turn a 'table:id' string (or RecordID) into a RecordID for querying."""
        if id_value is None:
            return None
        if type(id_value).__name__ == "RecordID":
            return id_value
        s = str(id_value)
        if ":" in s:
            from surrealdb import RecordID

            table, _, rid = s.partition(":")
            return RecordID(table, rid)
        return s

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
        if self.backend == "surrealdb":
            query = """
            INSERT INTO decisions {
                title: $title,
                rationale: $rationale,
                outcome: $outcome,
                author: $author,
                branch: $branch,
                commit_sha: $commit_sha,
                created_at: time::now()
            }
            """
            params = {
                "title": title,
                "rationale": rationale,
                "outcome": outcome,
                "author": author,
                "branch": branch,
                "commit_sha": commit_sha,
            }
            try:
                res = self.db.query(query, params)
                return self._extract_id(res)
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
                        query, (title, rationale, outcome, author, branch, commit_sha)
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
        if self.backend == "surrealdb":
            if self.spectron is not None:
                try:
                    self.spectron.remember(fact=value, scope=[category, key])
                except Exception as e:
                    logging.warning(f"Failed to save memory in Spectron: {e}")

            # Upsert by a deterministic record id derived from the key, so
            # re-saving the same key updates in place.
            query = """
            UPSERT $id CONTENT {
                key: $key,
                value: $value,
                category: $category,
                updated_at: time::now()
            };
            """
            params = {
                "id": self._rid("memory", key),
                "key": key,
                "value": value,
                "category": category,
            }
            try:
                self.db.query(query, params)
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
        """Deletes a memory entry by key (no-op if it does not exist)."""
        if self.backend == "surrealdb":
            try:
                self.db.query("DELETE memory WHERE key = $key;", {"key": key})
            except Exception as e:
                logging.error(f"Failed to delete memory in SurrealDB: {e}")
        else:
            try:
                with self._sqlite_conn() as conn:
                    conn.execute("DELETE FROM memory WHERE key = ?", (key,))
                    conn.commit()
            except sqlite3.Error as e:
                logging.error(f"Failed to delete memory: {e}")

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
                res = self.db.query(query, {"key": key})
                return self._extract_field(res, "value")
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
        if self.backend == "surrealdb":
            query = """
            INSERT INTO milestones {
                title: $title,
                description: $description,
                due_date: $due_date,
                state: $state,
                created_at: time::now()
            }
            """
            params = {
                "title": title,
                "description": description,
                "due_date": due_date,
                "state": state,
            }
            try:
                res = self.db.query(query, params)
                return self._extract_id(res)
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
                    cursor.execute(query, (title, description, due_date, state))
                    conn.commit()
                    return cursor.lastrowid
            except sqlite3.Error as e:
                logging.error(f"Failed to create milestone: {e}")
                raise RuntimeError(f"Failed to create milestone: {e}")

    def list_milestones(self) -> List[Dict[str, Any]]:
        """List milestones, most recent first."""
        if self.backend == "surrealdb":
            try:
                res = self.db.query("SELECT * FROM milestones ORDER BY created_at DESC")
                return self._extract_list(res)
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
        if self.backend == "surrealdb":
            query = """
            INSERT INTO releases {
                version: $version,
                tag: $tag,
                notes: $notes,
                issue_github_id: $issue_github_id,
                milestone_id: $milestone_id,
                commit_sha: $commit_sha,
                released_at: time::now()
            }
            """
            params = {
                "version": version,
                "tag": tag,
                "notes": notes,
                "issue_github_id": issue_github_id,
                "milestone_id": mid,
                "commit_sha": commit_sha,
            }
            try:
                res = self.db.query(query, params)
                return self._extract_id(res)
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
                        query, (version, tag, notes, issue_github_id, mid, commit_sha)
                    )
                    conn.commit()
                    return cursor.lastrowid
            except sqlite3.Error as e:
                logging.error(f"Failed to save release: {e}")
                raise RuntimeError(f"Failed to save release: {e}")

    def get_release(self, release_id: Union[str, int]) -> Optional[Dict[str, Any]]:
        """Retrieve a release by id."""
        if self.backend == "surrealdb":
            try:
                res = self.db.query(
                    "SELECT * FROM $id", {"id": self._parse_rid(release_id)}
                )
                return self._extract_record(res)
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

    def list_releases(self, limit: int = 20) -> List[Dict[str, Any]]:
        """List delivered releases, most recent first."""
        if self.backend == "surrealdb":
            try:
                res = self.db.query(
                    f"SELECT * FROM releases ORDER BY released_at DESC LIMIT {int(limit)}"
                )
                return self._extract_list(res)
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
    ) -> None:
        """Logs a GitHub issue.

        Args:
            github_id: Numeric or string ID of the GitHub issue.
            title: Title of the issue.
            type_: Type of issue (e.g., bug, feature, refactor).
            status: Status (e.g., open, closed).
            milestone_id: Associated milestone ID in the database.
        """
        if self.backend == "surrealdb":
            query = """
            UPSERT $id CONTENT {
                github_id: $github_id,
                title: $title,
                type_: $type_,
                status: $status,
                milestone_id: $milestone_id,
                created_at: time::now()
            };
            """
            params = {
                "id": self._rid("issues", github_id),
                "github_id": github_id,
                "title": title,
                "type_": type_,
                "status": status,
                "milestone_id": milestone_id,
            }
            try:
                self.db.query(query, params)
            except Exception as e:
                logging.error(f"Failed to log issue in SurrealDB: {e}")
                raise RuntimeError(f"Failed to log issue in SurrealDB: {e}")
        else:
            query = """
            INSERT INTO issues (github_id, title, type_, status, milestone_id)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(github_id) DO UPDATE SET
                title=excluded.title,
                type_=excluded.type_,
                status=excluded.status,
                milestone_id=excluded.milestone_id
            """
            try:
                with self._sqlite_conn() as conn:
                    conn.execute(query, (github_id, title, type_, status, milestone_id))
                    conn.commit()
            except sqlite3.Error as e:
                logging.error(f"Failed to log issue: {e}")
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
        if self.backend == "surrealdb":
            query = """
            INSERT INTO backtest_runs {
                strategy_name: $strategy_name,
                sharpe_ratio: $sharpe_ratio,
                max_drawdown: $max_drawdown,
                profit_factor: $profit_factor,
                parameters: $parameters,
                dataset: $dataset,
                commit_sha: $commit_sha,
                created_at: time::now()
            }
            """
            params = {
                "strategy_name": strategy_name,
                "sharpe_ratio": sharpe_ratio,
                "max_drawdown": max_drawdown,
                "profit_factor": profit_factor,
                "parameters": parameters,
                "dataset": dataset,
                "commit_sha": commit_sha,
            }
            try:
                res = self.db.query(query, params)
                return self._extract_id(res)
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
                            strategy_name,
                            sharpe_ratio,
                            max_drawdown,
                            profit_factor,
                            parameters,
                            dataset,
                            commit_sha,
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
                "id": self._rid("sessions", session_id),
                "session_id": session_id,
                "agent_name": agent_name,
                "task": task,
                "messages": messages,
            }
            try:
                self.db.query(query, params)
            except Exception as e:
                logging.error(f"Failed to save session in SurrealDB: {e}")
                raise RuntimeError(f"Failed to save session in SurrealDB: {e}")
        else:
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
                        query, (session_id, agent_name, task, serialized_messages)
                    )
                    conn.commit()
            except sqlite3.Error as e:
                logging.error(f"Failed to save session: {e}")
                raise RuntimeError(f"Failed to save session: {e}")

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
                res = self.db.query(query, {"session_id": session_id})
                return self._extract_record(res)
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
        if self.backend == "surrealdb":
            query = """
            INSERT INTO handoffs {
                sender: $sender,
                recipient: $recipient,
                contract_type: $contract_type,
                contract_path: $contract_path,
                status: $status,
                timestamp: time::now()
            }
            """
            params = {
                "sender": sender,
                "recipient": recipient,
                "contract_type": contract_type,
                "contract_path": contract_path,
                "status": status,
            }
            try:
                res = self.db.query(query, params)
                return self._extract_id(res)
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
                        query, (sender, recipient, contract_type, contract_path, status)
                    )
                    conn.commit()
                    return cursor.lastrowid
            except sqlite3.Error as e:
                logging.error(f"Failed to log handoff: {e}")
                raise RuntimeError(f"Failed to log handoff: {e}")

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
                res = self.db.query(
                    query, {"id": self._parse_rid(handoff_id)}
                )
                return self._extract_record(res)
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
                res = self.db.query(
                    query, {"id": self._parse_rid(decision_id)}
                )
                return self._extract_record(res)
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
                res = self.db.query(
                    query, {"id": self._parse_rid(milestone_id)}
                )
                return self._extract_record(res)
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
                res = self.db.query(query, {"github_id": github_id})
                return self._extract_record(res)
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
                res = self.db.query(
                    query, {"id": self._parse_rid(backtest_id)}
                )
                return self._extract_record(res)
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

    def get_open_issues(self) -> List[Dict[str, Any]]:
        """Retrieves all open issues.

        Returns:
            A list of dictionaries containing open issues.
        """
        if self.backend == "surrealdb":
            query = "SELECT * FROM issues WHERE status = 'open'"
            try:
                res = self.db.query(query)
                return self._extract_list(res)
            except Exception as e:
                logging.error(f"Failed to retrieve open issues from SurrealDB: {e}")
                raise RuntimeError(
                    f"Failed to retrieve open issues from SurrealDB: {e}"
                )
        else:
            query = "SELECT * FROM issues WHERE status = 'open'"
            try:
                with self._sqlite_conn() as conn:
                    cursor = conn.cursor()
                    cursor.execute(query)
                    rows = cursor.fetchall()
                    return [dict(row) for row in rows]
            except sqlite3.Error as e:
                logging.error(f"Failed to retrieve open issues: {e}")
                raise RuntimeError(f"Failed to retrieve open issues: {e}")

    def list_issues(self) -> List[Dict[str, Any]]:
        """Retrieves every issue for this tenant regardless of status.

        Read-only. Unlike get_open_issues (status='open' only), this returns all
        issues including Done, so the cockpit board can render the full seven
        columns. No row is created or mutated.
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

    def get_latest_activity(self) -> Optional[Dict[str, Any]]:
        """Retrieves the most recent entry from the handoffs or sessions table.

        Returns:
            A dictionary with keys 'type', 'agent', 'task', 'status', 'timestamp'
            (and 'contract_path' for handoffs, pointing to the handoff contract
            artifact), or None if no activity exists.
        """
        latest_session = None
        if self.backend == "surrealdb":
            query = "SELECT * FROM sessions ORDER BY timestamp DESC LIMIT 1"
            try:
                res = self.db.query(query)
                latest_session = self._extract_record(res)
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
                res = self.db.query(query)
                latest_handoff = self._extract_record(res)
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
