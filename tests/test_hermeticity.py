"""Hermeticity regression guard for the test suite (issue #29, slice A/3 of #24).

The suite is hermetic today: it does not write the real project memory DB and does
not spawn a real workflow engine. Nothing enforced that, so a future change could
regress it silently. These guards pin the two fail-closed invariants:

1. A DatabaseClient resolved against a surrealdb-provider config falls back to
   SQLite when the real shared backend is unreachable, and never raises -- so a
   test can never connect to or write the real shared multi-tenant SurrealDB.
2. workflows.run_stage reaches the engine only through the mockable subprocess.run
   seam, so a test can always intercept the spawn and no real process runs.
"""

import json
import os
import tempfile
import unittest
from unittest.mock import patch

from solomon_harness import workflows
from solomon_harness.tools.database_client import DatabaseClient


def _workspace_with_command(stage: str, body: str) -> str:
    tmp = tempfile.mkdtemp()
    cmd_dir = os.path.join(tmp, ".claude", "commands")
    os.makedirs(cmd_dir)
    with open(os.path.join(cmd_dir, f"solomon-{stage}.md"), "w", encoding="utf-8") as f:
        f.write(body)
    return tmp


class TestHermeticityGuard(unittest.TestCase):
    def test_db_fails_closed_to_sqlite_when_real_backend_unreachable(self):
        # An isolated harness dir configured for the surrealdb provider. With the
        # endpoint forced to an unreachable port and creds cleared, the client must
        # fall back to SQLite (writing only inside the temp dir), never connecting
        # to or writing the real shared SurrealDB, and never raising.
        with tempfile.TemporaryDirectory() as tmp:
            os.makedirs(os.path.join(tmp, ".agent"))
            with open(os.path.join(tmp, ".agent", "config.json"), "w", encoding="utf-8") as f:
                json.dump(
                    {
                        "database": {
                            "provider": "surrealdb",
                            "url": "ws://localhost:8000/rpc",
                            "namespace": "solomon",
                            "database": "harness",
                        }
                    },
                    f,
                )
            with patch.dict(
                os.environ,
                {"SURREAL_URL": "ws://127.0.0.1:1/rpc", "SURREAL_USER": "", "SURREAL_PASS": ""},
            ):
                with DatabaseClient(harness_dir=tmp) as client:
                    self.assertEqual(
                        client.backend,
                        "sqlite",
                        "a test reached a real backend instead of failing closed to SQLite",
                    )
                # The SQLite fallback file must live inside the temp dir, not the repo.
                self.assertTrue(
                    client.db_path and client.db_path.startswith(tmp),
                    f"SQLite fell back outside the isolated dir: {client.db_path}",
                )

    def test_run_stage_reaches_engine_only_through_subprocess_run(self):
        root = _workspace_with_command("start", "---\nx\n---\nDo work on $ARGUMENTS")

        class _Proc:
            returncode = 0

        # Patching subprocess.run must fully intercept the engine spawn: if a
        # regression added a non-mockable real-exec path, the patch would not be
        # called (or a real process would run). The loop lock also shells out to
        # `ps` (through this same seam) to record the holder's process start
        # time, so we assert on the specific engine invocation rather than the
        # total call count.
        with patch("subprocess.run", return_value=_Proc()) as mock_run:
            rc = workflows.run_stage(root, "start", ["42"], engine="claude")
        self.assertEqual(rc, 0)
        engine_calls = [c for c in mock_run.call_args_list if c.args and c.args[0][:2] == ["claude", "-p"]]
        self.assertEqual(len(engine_calls), 1)


if __name__ == "__main__":
    unittest.main()
