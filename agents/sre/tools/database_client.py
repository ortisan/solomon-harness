import os
import sqlite3
import logging


class DatabaseClient:
    """A client to manage SQLite database operations for the agent harness."""

    def __init__(self, db_path=None):
        """Initializes the database client and automated table creations.

        Args:
            db_path: Optional custom path to the SQLite database file.
        """
        if db_path is None:
            # Dynamically locate the database directory relative to this file
            tools_dir = os.path.dirname(os.path.abspath(__file__))
            harness_dir = os.path.dirname(tools_dir)
            db_dir = os.path.join(harness_dir, "memory", "long_term")
            os.makedirs(db_dir, exist_ok=True)
            self.db_path = os.path.join(db_dir, "harness.db")
        else:
            self.db_path = db_path

        self._init_db()

    def _get_connection(self):
        """Establishes and returns a SQLite connection with Row factory configured."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self):
        """Creates the required tables if they do not already exist."""
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
            """
        ]

        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                for query in queries:
                    cursor.execute(query)
                conn.commit()
        except sqlite3.Error as e:
            logging.error(f"Database initialization failed: {e}")
            raise RuntimeError(f"Database initialization failed: {e}")

    def log_decision(self, title, rationale, outcome, author, branch, commit_sha):
        """Logs an architectural or design decision to the database.

        Args:
            title: The title of the decision.
            rationale: Explanation and options considered.
            outcome: Chosen course of action.
            author: Person or role logging the decision.
            branch: Current Git branch name.
            commit_sha: Commit SHA representing the change.

        Returns:
            The primary key ID of the inserted record.
        """
        query = """
        INSERT INTO decisions (title, rationale, outcome, author, branch, commit_sha)
        VALUES (?, ?, ?, ?, ?, ?)
        """
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(query, (title, rationale, outcome, author, branch, commit_sha))
                conn.commit()
                return cursor.lastrowid
        except sqlite3.Error as e:
            logging.error(f"Failed to log decision: {e}")
            raise RuntimeError(f"Failed to log decision: {e}")

    def save_memory(self, key, value, category):
        """Upserts a key-value memory entry.

        Args:
            key: Unique key identifying the memory.
            value: Value of the memory entry.
            category: Categorical bucket for the memory.
        """
        query = """
        INSERT INTO memory (key, value, category, updated_at)
        VALUES (?, ?, ?, CURRENT_TIMESTAMP)
        ON CONFLICT(key) DO UPDATE SET
            value=excluded.value,
            category=excluded.category,
            updated_at=CURRENT_TIMESTAMP
        """
        try:
            with self._get_connection() as conn:
                conn.execute(query, (key, value, category))
                conn.commit()
        except sqlite3.Error as e:
            logging.error(f"Failed to save memory: {e}")
            raise RuntimeError(f"Failed to save memory: {e}")

    def get_memory(self, key):
        """Retrieves a memory value by its key.

        Args:
            key: The unique memory key.

        Returns:
            The memory value string or None if not found.
        """
        query = "SELECT value FROM memory WHERE key = ?"
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(query, (key,))
                row = cursor.fetchone()
                return row["value"] if row else None
        except sqlite3.Error as e:
            logging.error(f"Failed to retrieve memory: {e}")
            raise RuntimeError(f"Failed to retrieve memory: {e}")

    def create_milestone(self, title, description, due_date, state):
        """Creates a project milestone record.

        Args:
            title: Milestone title.
            description: Detailed objective list.
            due_date: Target completion date.
            state: Active state (e.g., active, complete, pending).

        Returns:
            The primary key ID of the created milestone.
        """
        query = """
        INSERT INTO milestones (title, description, due_date, state)
        VALUES (?, ?, ?, ?)
        """
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(query, (title, description, due_date, state))
                conn.commit()
                return cursor.lastrowid
        except sqlite3.Error as e:
            logging.error(f"Failed to create milestone: {e}")
            raise RuntimeError(f"Failed to create milestone: {e}")

    def log_issue(self, github_id, title, type_, status, milestone_id):
        """Logs a GitHub issue.

        Args:
            github_id: Numeric or string ID of the GitHub issue.
            title: Title of the issue.
            type_: Type of issue (e.g., bug, feature, refactor).
            status: Status (e.g., open, closed).
            milestone_id: Associated milestone ID in the database.
        """
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
            with self._get_connection() as conn:
                conn.execute(query, (github_id, title, type_, status, milestone_id))
                conn.commit()
        except sqlite3.Error as e:
            logging.error(f"Failed to log issue: {e}")
            raise RuntimeError(f"Failed to log issue: {e}")

    def save_backtest(self, strategy_name, sharpe_ratio, max_drawdown, profit_factor, parameters, dataset, commit_sha):
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
            The primary key ID of the inserted record.
        """
        query = """
        INSERT INTO backtest_runs (strategy_name, sharpe_ratio, max_drawdown, profit_factor, parameters, dataset, commit_sha)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(query, (strategy_name, sharpe_ratio, max_drawdown, profit_factor, parameters, dataset, commit_sha))
                conn.commit()
                return cursor.lastrowid
        except sqlite3.Error as e:
            logging.error(f"Failed to save backtest run: {e}")
            raise RuntimeError(f"Failed to save backtest run: {e}")

    def get_decision(self, decision_id):
        """Retrieves a logged decision by ID.

        Args:
            decision_id: The primary key ID of the decision.

        Returns:
            A dictionary containing the record details or None.
        """
        query = "SELECT * FROM decisions WHERE id = ?"
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(query, (decision_id,))
                row = cursor.fetchone()
                return dict(row) if row else None
        except sqlite3.Error as e:
            logging.error(f"Failed to retrieve decision: {e}")
            raise RuntimeError(f"Failed to retrieve decision: {e}")

    def get_milestone(self, milestone_id):
        """Retrieves a milestone by ID.

        Args:
            milestone_id: The primary key ID of the milestone.

        Returns:
            A dictionary containing the record details or None.
        """
        query = "SELECT * FROM milestones WHERE id = ?"
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(query, (milestone_id,))
                row = cursor.fetchone()
                return dict(row) if row else None
        except sqlite3.Error as e:
            logging.error(f"Failed to retrieve milestone: {e}")
            raise RuntimeError(f"Failed to retrieve milestone: {e}")

    def get_issue(self, github_id):
        """Retrieves an issue by its GitHub ID.

        Args:
            github_id: The primary key GitHub ID of the issue.

        Returns:
            A dictionary containing the record details or None.
        """
        query = "SELECT * FROM issues WHERE github_id = ?"
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(query, (github_id,))
                row = cursor.fetchone()
                return dict(row) if row else None
        except sqlite3.Error as e:
            logging.error(f"Failed to retrieve issue: {e}")
            raise RuntimeError(f"Failed to retrieve issue: {e}")

    def get_backtest(self, backtest_id):
        """Retrieves a backtest run by ID.

        Args:
            backtest_id: The primary key ID of the backtest run.

        Returns:
            A dictionary containing the record details or None.
        """
        query = "SELECT * FROM backtest_runs WHERE id = ?"
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(query, (backtest_id,))
                row = cursor.fetchone()
                return dict(row) if row else None
        except sqlite3.Error as e:
            logging.error(f"Failed to retrieve backtest run: {e}")
            raise RuntimeError(f"Failed to retrieve backtest run: {e}")
