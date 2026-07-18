import unittest
from unittest.mock import MagicMock, patch

from solomon_harness import digest, healthcheck

_BANNER = "SQLite fallback (SurrealDB unreachable)"


def _lines(**kw):
    return digest.build_digest(
        resume=None, open_issues=[], last_loop_run=None, prs=None, **kw
    )


class TestDigestBanner(unittest.TestCase):
    def test_deliberate_sqlite_shows_no_banner(self):
        lines = _lines(backend="sqlite", degraded=False)
        self.assertFalse(any(_BANNER in line for line in lines))

    def test_degraded_fallback_shows_banner(self):
        lines = _lines(backend="sqlite", degraded=True)
        self.assertTrue(any(_BANNER in line for line in lines))

    def test_backend_string_is_the_fallback_when_degraded_unknown(self):
        self.assertTrue(any(_BANNER in line for line in _lines(backend="sqlite")))
        self.assertFalse(any(_BANNER in line for line in _lines(backend="surrealdb")))


class TestHealthcheckMemory(unittest.TestCase):
    def _run(self, backend_status):
        client = MagicMock()
        client.__enter__.return_value.backend_status.return_value = backend_status
        with patch.object(
            healthcheck, "_db_config",
            return_value={"provider": "surrealdb", "url": "ws://localhost:8099/rpc"},
        ), patch.object(healthcheck.memory, "is_serving", return_value=True), patch(
            "solomon_harness.tools.database_client.DatabaseClient", return_value=client
        ):
            return healthcheck.check_memory("/x")

    def test_reachable_but_degraded_reports_warn(self):
        result = self._run({"backend": "sqlite", "degraded": True, "fallback_reason": "connection to SurrealDB failed"})
        self.assertEqual(result["status"], healthcheck.WARN)
        self.assertIn("degraded", result["detail"])

    def test_reachable_and_healthy_reports_ok(self):
        result = self._run({"backend": "surrealdb", "degraded": False, "fallback_reason": None})
        self.assertEqual(result["status"], healthcheck.OK)

    def test_supplied_db_status_avoids_a_second_client(self):
        with patch.object(
            healthcheck, "_db_config",
            return_value={"provider": "surrealdb", "url": "ws://localhost:8099/rpc"},
        ), patch.object(healthcheck.memory, "is_serving", return_value=True), patch(
            "solomon_harness.tools.database_client.DatabaseClient"
        ) as client_cls:
            result = healthcheck.check_memory(
                "/x", db_status={"backend": "surrealdb", "degraded": False, "fallback_reason": None}
            )
        self.assertEqual(result["status"], healthcheck.OK)
        client_cls.assert_not_called()

    def test_foreign_process_on_port_reports_warn(self):
        with patch.object(
            healthcheck, "_db_config",
            return_value={"provider": "surrealdb", "url": "ws://localhost:8099/rpc"},
        ), patch.object(healthcheck.memory, "is_serving", return_value=False), patch.object(
            healthcheck.memory, "_tcp_open", return_value=True
        ):
            result = healthcheck.check_memory("/x")
        self.assertEqual(result["status"], healthcheck.WARN)
        self.assertIn("non-SurrealDB", result["detail"])


if __name__ == "__main__":
    unittest.main()
