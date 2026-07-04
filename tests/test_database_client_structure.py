"""Structural guards for solomon_harness/tools/database_client.py (issue #163).

Pins the follow-ups from the 2026-07-03 structure audit so they cannot silently
regress: SurrealQL LIMIT values are bound parameters (never f-string
interpolation), the client exposes an honest public backend accessor, and the
constructor stays split into focused initializers instead of regrowing into one
monolithic block.
"""

import inspect
import os
import re
import sys
import tempfile
import unittest

WORKSPACE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if WORKSPACE not in sys.path:
    sys.path.insert(0, WORKSPACE)

from solomon_harness.tools import database_client  # noqa: E402
from solomon_harness.tools.database_client import DatabaseClient  # noqa: E402


class TestParameterizedLimit(unittest.TestCase):
    """Parameterized queries are the project default; LIMIT is no exception.

    int() coercion happens to neutralize injection for these sites, but the
    rule the audit enforces is structural: no query string is built by
    interpolating a caller-supplied value, so a future edit cannot silently
    downgrade a coerced int into a raw string.
    """

    def test_no_brace_interpolated_limit_in_module_source(self):
        source = inspect.getsource(database_client)
        offenders = [
            line.strip()
            for line in source.splitlines()
            if re.search(r"LIMIT\s*\{", line)
        ]
        self.assertEqual(
            offenders, [], f"brace-interpolated LIMIT found: {offenders}"
        )


def _sqlite_client(tmp: str) -> DatabaseClient:
    """A client forced onto SQLite via an explicit db_path (test isolation)."""
    return DatabaseClient(
        db_path=os.path.join(tmp, "memory.db"),
        harness_dir=tmp,
        mirror_root=os.path.join(tmp, "mirror"),
    )


class TestBackendStatus(unittest.TestCase):
    """backend_status() tells a session which backend serves it, and why."""

    def test_forced_sqlite_is_not_degraded(self):
        # An explicit db_path is a deliberate SQLite choice, not a fallback.
        with tempfile.TemporaryDirectory() as tmp:
            client = _sqlite_client(tmp)
            try:
                status = client.backend_status()
            finally:
                client.close()
        self.assertEqual(
            status,
            {"backend": "sqlite", "degraded": False, "fallback_reason": None},
        )

    def test_missing_credentials_fallback_is_degraded_with_reason(self):
        # A non-local SurrealDB URL with no credentials fails closed to SQLite
        # at construction; the accessor must say so instead of looking pure.
        with tempfile.TemporaryDirectory() as tmp:
            os.makedirs(os.path.join(tmp, ".agent"), exist_ok=True)
            with open(
                os.path.join(tmp, ".agent", "config.json"), "w", encoding="utf-8"
            ) as f:
                f.write(
                    '{"database": {"provider": "surrealdb",'
                    ' "url": "ws://memory.invalid:8000/rpc"}}'
                )
            overridden = ("SURREAL_URL", "SURREAL_USER", "SURREAL_PASS",
                          "HARNESS_DB_PATH", "HARNESS_MIRROR_ROOT")
            env_backup = {key: os.environ.pop(key, None) for key in overridden}
            os.environ["HARNESS_DB_PATH"] = os.path.join(tmp, "memory.db")
            os.environ["HARNESS_MIRROR_ROOT"] = os.path.join(tmp, "mirror")
            try:
                client = DatabaseClient(harness_dir=tmp)
                try:
                    status = client.backend_status()
                finally:
                    client.close()
            finally:
                for key, value in env_backup.items():
                    if value is None:
                        os.environ.pop(key, None)
                    else:
                        os.environ[key] = value
        self.assertEqual(status["backend"], "sqlite")
        self.assertTrue(status["degraded"])
        self.assertIn("credentials", status["fallback_reason"])

    def test_mid_session_fallback_is_degraded_with_reason(self):
        # _activate_sqlite_fallback is the last-resort path after a lost
        # connection; the accessor must report the degradation it creates.
        with tempfile.TemporaryDirectory() as tmp:
            client = _sqlite_client(tmp)
            try:
                client._activate_sqlite_fallback()
                status = client.backend_status()
            finally:
                client.close()
        self.assertEqual(status["backend"], "sqlite")
        self.assertTrue(status["degraded"])
        self.assertIn("connection lost", status["fallback_reason"])


class TestFocusedInit(unittest.TestCase):
    """The 261-line constructor stays split into focused initializers."""

    def test_constructor_delegates_to_focused_initializers(self):
        for name in (
            "_init_embedder",
            "_init_connection_state",
            "_resolve_roots",
            "_load_config",
            "_init_backend",
        ):
            self.assertTrue(
                callable(getattr(DatabaseClient, name, None)),
                f"missing focused initializer: {name}",
            )

    def test_constructor_stays_small(self):
        lines = len(inspect.getsource(DatabaseClient.__init__).splitlines())
        self.assertLess(
            lines, 100, f"__init__ regrew to {lines} lines; keep it delegating"
        )


if __name__ == "__main__":
    unittest.main()
