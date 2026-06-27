import os
import json
import sqlite3
import logging
import sys
from contextlib import contextmanager
from typing import Generator, Any, Dict, List, Optional, Union


class DatabaseClient:
    """A client to manage SQLite or SurrealDB database operations for the agent harness."""
    backend: str
    db: Any
    db_path: Optional[str]

    def __init__(self, db_path: Optional[str] = None) -> None:
        """Initializes the database client and selects the appropriate backend.

        Args:
            db_path: Optional custom path to the SQLite database file (if using SQLite).
        """
        self.backend = "sqlite"
        self.db = None
        self.db_path = db_path

        # Locate the repository root by traversing upwards to find '.git' or typical workspace directories
        current_dir: str = os.path.dirname(os.path.abspath(__file__))
        project_root: str = current_dir
        found_root: bool = False
        while project_root and project_root != os.path.dirname(project_root):
            if os.path.exists(os.path.join(project_root, ".git")):
                found_root = True
                break
            if (os.path.exists(os.path.join(project_root, "agents")) and
                os.path.exists(os.path.join(project_root, "memory")) and
                os.path.exists(os.path.join(project_root, "templates"))):
                found_root = True
                break
            project_root = os.path.dirname(project_root)

        if not found_root:
            # Fallback gracefully to the parent of tools/ relative to this file
            project_root = os.path.dirname(current_dir)

        # Attempt to load configuration
        config: Dict[str, Any] = {}
        config_path: str = os.path.join(project_root, ".agent", "config.json")
        if os.path.isfile(config_path):
            try:
                with open(config_path, "r", encoding="utf-8") as f:
                    config = json.load(f)
            except Exception:
                pass

        db_config = config.get("database", {})
        provider = db_config.get("provider")

        if provider == "surrealdb":
            # Dynamically import surrealdb to support dynamic backend loading
            try:
                import surrealdb  # type: ignore[import-not-found]
                Surreal = surrealdb.Surreal
                has_surrealdb = True
            except (ImportError, AttributeError):
                has_surrealdb = False
                Surreal = None

            if has_surrealdb and Surreal is not None:
                url = db_config.get("url", "ws://localhost:8000/rpc")
                username = db_config.get("username", "root")
                password = db_config.get("password", "root")
                namespace = db_config.get("namespace", "solomon")
                database = db_config.get("database", "harness")

                try:
                    self.db = Surreal(url)
                    self.db.connect()
                    self.db.signin({"user": username, "pass": password})
                    self.db.use(namespace, database)

                    # Initialize SurrealDB tables
                    init_query = (
                        "DEFINE TABLE decisions SCHEMALESS; "
                        "DEFINE TABLE memory SCHEMALESS; "
                        "DEFINE TABLE milestones SCHEMALESS; "
                        "DEFINE TABLE issues SCHEMALESS; "
                        "DEFINE TABLE backtest_runs SCHEMALESS; "
                        "DEFINE TABLE sessions SCHEMALESS; "
                        "DEFINE TABLE handoffs SCHEMALESS;"
                    )
                    self.db.query(init_query)
                    self.backend = "surrealdb"
                except Exception as e:
                    sys.stderr.write(f"Warning: Connection to SurrealDB failed: {e}\n")
                    sys.stderr.write("SurrealDB library or server unavailable. Falling back to SQLite backend.\n")
                    if self.db:
                        try:
                            self.db.close()
                        except Exception:
                            pass
                        self.db = None
                    self.backend = "sqlite"
            else:
                sys.stderr.write("SurrealDB library or server unavailable. Falling back to SQLite backend.\n")
                self.backend = "sqlite"

        # Initialize SQLite if backend is sqlite
        if self.backend == "sqlite":
            if self.db_path is None:
                db_dir: str = os.path.join(project_root, "memory", "long_term")
                os.makedirs(db_dir, exist_ok=True)
                self.db_path = os.path.join(db_dir, "harness.db")
            self._init_sqlite_db()

    @contextmanager
    def _sqlite_conn(self) -> Generator[sqlite3.Connection, None, None]:
        """Establishes and returns a SQLite connection context and ensures it is closed on exit."""
        if self.db_path is None:
            raise ValueError("Database path must be set for SQLite backend")
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
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
            """
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

    def _extract_id(self, res: Any) -> Optional[str]:
        """Helper to extract record ID safely from SurrealDB query results."""
        if not res:
            return None
        first = res[0]
        if isinstance(first, list):
            if first:
                item = first[0]
                return item.get("id") if isinstance(item, dict) else None
        elif isinstance(first, dict):
            if "result" in first and isinstance(first["result"], list):
                if first["result"]:
                    item = first["result"][0]
                    return item.get("id") if isinstance(item, dict) else None
            else:
                return first.get("id")
        return None

    def _extract_field(self, res: Any, field_name: str) -> Any:
        """Helper to extract a specific field value safely from SurrealDB query results."""
        if not res:
            return None
        first = res[0]
        if isinstance(first, list):
            if first:
                item = first[0]
                return item.get(field_name) if isinstance(item, dict) else None
        elif isinstance(first, dict):
            if "result" in first and isinstance(first["result"], list):
                if first["result"]:
                    item = first["result"][0]
                    return item.get(field_name) if isinstance(item, dict) else None
            else:
                return first.get(field_name)
        return None

    def _extract_record(self, res: Any) -> Optional[Dict[str, Any]]:
        """Helper to extract a full record dictionary safely from SurrealDB query results."""
        if not res:
            return None
        first = res[0]
        if isinstance(first, list):
            if first:
                item = first[0]
                return dict(item) if isinstance(item, dict) else None
        elif isinstance(first, dict):
            if "result" in first and isinstance(first["result"], list):
                if first["result"]:
                    item = first["result"][0]
                    return dict(item) if isinstance(item, dict) else None
            else:
                return dict(first)
        return None

    def _format_id(self, table: str, record_id: Union[str, int, None]) -> Optional[str]:
        """Formats the ID parameter for SurrealDB queries."""
        if record_id is None:
            return None
        s_id = str(record_id)
        if s_id.startswith(f"{table}:"):
            return s_id
        return f"{table}:{s_id}"

    def log_decision(
        self,
        title: str,
        rationale: str,
        outcome: str,
        author: str,
        branch: str,
        commit_sha: str
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
                "commit_sha": commit_sha
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
                    cursor.execute(query, (title, rationale, outcome, author, branch, commit_sha))
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
            query = """
            UPSERT INTO memory {
                id: $id,
                key: $key,
                value: $value,
                category: $category,
                updated_at: time::now()
            }
            """
            params = {
                "id": f"memory:{key}",
                "key": key,
                "value": value,
                "category": category
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

    def get_memory(self, key: str) -> Optional[str]:
        """Retrieves a memory value by its key.

        Args:
            key: The unique memory key.

        Returns:
            The memory value string or None if not found.
        """
        if self.backend == "surrealdb":
            query = "SELECT value FROM memory WHERE key = $key"
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
        self,
        title: str,
        description: str,
        due_date: str,
        state: str
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
                "state": state
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

    def log_issue(
        self,
        github_id: str,
        title: str,
        type_: str,
        status: str,
        milestone_id: Optional[Union[str, int]]
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
            UPSERT INTO issues {
                id: $id,
                github_id: $github_id,
                title: $title,
                type_: $type_,
                status: $status,
                milestone_id: $milestone_id,
                created_at: time::now()
            }
            """
            params = {
                "id": f"issues:{github_id}",
                "github_id": github_id,
                "title": title,
                "type_": type_,
                "status": status,
                "milestone_id": milestone_id
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
        commit_sha: str
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
                "commit_sha": commit_sha
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
                    cursor.execute(query, (strategy_name, sharpe_ratio, max_drawdown, profit_factor, parameters, dataset, commit_sha))
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
        messages: Union[List[Dict[str, Any]], str]
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
            UPSERT INTO sessions {
                id: $id,
                session_id: $session_id,
                agent_name: $agent_name,
                task: $task,
                messages: $messages,
                timestamp: time::now()
            }
            """
            params = {
                "id": f"sessions:{session_id}",
                "session_id": session_id,
                "agent_name": agent_name,
                "task": task,
                "messages": messages
            }
            try:
                self.db.query(query, params)
            except Exception as e:
                logging.error(f"Failed to save session in SurrealDB: {e}")
                raise RuntimeError(f"Failed to save session in SurrealDB: {e}")
        else:
            serialized_messages = json.dumps(messages) if not isinstance(messages, str) else messages
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
                    conn.execute(query, (session_id, agent_name, task, serialized_messages))
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
        status: str
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
                "status": status
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
                    cursor.execute(query, (sender, recipient, contract_type, contract_path, status))
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
            query = "SELECT * FROM handoffs WHERE id = $id"
            try:
                res = self.db.query(query, {"id": self._format_id("handoffs", handoff_id)})
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
            query = "SELECT * FROM decisions WHERE id = $id"
            try:
                res = self.db.query(query, {"id": self._format_id("decisions", decision_id)})
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
            query = "SELECT * FROM milestones WHERE id = $id"
            try:
                res = self.db.query(query, {"id": self._format_id("milestones", milestone_id)})
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
            query = "SELECT * FROM issues WHERE id = $id"
            try:
                res = self.db.query(query, {"id": self._format_id("issues", github_id)})
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
            query = "SELECT * FROM backtest_runs WHERE id = $id"
            try:
                res = self.db.query(query, {"id": self._format_id("backtest_runs", backtest_id)})
                return self._extract_record(res)
            except Exception as e:
                logging.error(f"Failed to retrieve backtest run from SurrealDB: {e}")
                raise RuntimeError(f"Failed to retrieve backtest run from SurrealDB: {e}")
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

    def _extract_list(self, res: Any) -> List[Dict[str, Any]]:
        """Helper to extract a list of records safely from SurrealDB query results."""
        if not res:
            return []
        first = res[0]
        if isinstance(first, list):
            return [dict(item) for item in first if isinstance(item, dict)]
        elif isinstance(first, dict):
            if "result" in first and isinstance(first["result"], list):
                return [dict(item) for item in first["result"] if isinstance(item, dict)]
            else:
                return [dict(first)]
        return []

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
                raise RuntimeError(f"Failed to retrieve open issues from SurrealDB: {e}")
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

    def get_latest_activity(self) -> Optional[Dict[str, Any]]:
        """Retrieves the most recent entry from the handoffs or sessions table.

        Returns:
            A dictionary containing keys: 'type', 'agent', 'task', 'status', 'timestamp',
            or None if no activity exists.
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

        t_session = parse_time(latest_session.get("timestamp")) if latest_session else -1.0
        t_handoff = parse_time(latest_handoff.get("timestamp")) if latest_handoff else -1.0

        if t_session >= t_handoff:
            assert latest_session is not None
            return {
                "type": "session",
                "agent": latest_session.get("agent_name"),
                "task": latest_session.get("task"),
                "status": "active",
                "timestamp": latest_session.get("timestamp")
            }
        else:
            assert latest_handoff is not None
            return {
                "type": "handoff",
                "agent": f"{latest_handoff.get('sender')} -> {latest_handoff.get('recipient')}",
                "task": latest_handoff.get("contract_type"),
                "status": latest_handoff.get("status"),
                "timestamp": latest_handoff.get("timestamp")
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
        exc_tb: Optional[Any]
    ) -> None:
        self.close()
