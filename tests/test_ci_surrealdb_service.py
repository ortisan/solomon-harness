"""Regression guard: CI must run a live SurrealDB.

``.github/workflows/ci.yml`` runs ``uv run pytest`` with no SurrealDB service
available, so every test gated on a live SurrealDB probe
(``tests/test_database_client_multimodel.py``'s ``TestMultiModelLive``,
``tests/test_memory_service.py``'s live tests, and
``tests/test_harness_invariants.py``'s ``TestSurrealIntegration``) silently
skips in CI; only the mocked counterparts run, so real SurrealQL is never
exercised there. These checks lock in that the ``validate`` job starts a real
SurrealDB service (mirroring ``docker-compose.yml``) publishing the port and
credentials the live tests already default to, and exports the one env var
with no built-in default (``SURREAL_TEST_URL``), so the live suites actually
run instead of skipping.
"""

import os
import unittest

import yaml

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CI_WORKFLOW = os.path.join(REPO_ROOT, ".github", "workflows", "ci.yml")


def _validate_job():
    with open(CI_WORKFLOW, encoding="utf-8") as fh:
        data = yaml.safe_load(fh)
    return data["jobs"]["validate"]


def _pytest_step(job):
    for step in job.get("steps", []):
        if step.get("run", "").strip() == "uv run pytest":
            return step
    return None


class TestCiRunsLiveSurrealDB(unittest.TestCase):
    """The validate job must stand up SurrealDB before ``uv run pytest``."""

    def test_validate_job_defines_a_surrealdb_service(self):
        job = _validate_job()
        services = job.get("services") or {}
        self.assertIn(
            "surrealdb",
            services,
            "the validate job must run a surrealdb service container so the "
            "live-integration tests do not skip",
        )

    def test_surrealdb_service_publishes_the_port_tests_default_to(self):
        # tests/test_database_client_multimodel.py and test_memory_service.py
        # default SURREAL_URL to ws://localhost:8099/rpc, matching
        # docker-compose.yml's host port.
        job = _validate_job()
        service = job["services"]["surrealdb"]
        ports = [str(p) for p in service.get("ports", [])]
        self.assertIn(
            "8099:8000",
            ports,
            "the surrealdb service must publish 8099:8000 to match the "
            "SURREAL_URL default of ws://localhost:8099/rpc",
        )

    def test_surrealdb_service_actually_starts_the_server(self):
        # The image's entrypoint prints the banner and exits unless given the
        # "start" subcommand with credentials, exactly as docker-compose.yml
        # does.
        job = _validate_job()
        command = job["services"]["surrealdb"].get("command", "")
        self.assertIn("start", command)
        self.assertIn("--username", command)
        self.assertIn("--password", command)

    def test_pytest_step_exports_surreal_test_url(self):
        # test_harness_invariants.py's TestSurrealIntegration is gated on
        # SURREAL_TEST_URL specifically (not SURREAL_URL), so it must be set
        # for that live test to run. It must point at the same host:port the
        # service publishes.
        job = _validate_job()
        step = _pytest_step(job)
        self.assertIsNotNone(step, "expected a `uv run pytest` step in the validate job")
        env = step.get("env") or {}
        self.assertTrue(
            env.get("SURREAL_TEST_URL"),
            "the `uv run pytest` step must export a non-empty SURREAL_TEST_URL "
            "so TestSurrealIntegration runs instead of skipping",
        )
        self.assertIn("8099", env["SURREAL_TEST_URL"])

    def test_pytest_step_does_not_override_surreal_url(self):
        # test_database_client.py and test_memory.py construct DatabaseClient /
        # call _read_db_url with config-specified (non-default) SurrealDB URLs
        # and assert those exact values are used. Exporting SURREAL_URL here
        # would override the environment for the whole `uv run pytest`
        # invocation and break those assertions, since the env var wins over
        # config by design (see database_client.py and memory.py).
        job = _validate_job()
        step = _pytest_step(job)
        env = step.get("env") or {}
        self.assertNotIn(
            "SURREAL_URL",
            env,
            "SURREAL_URL already defaults to ws://localhost:8099/rpc in the live "
            "tests; exporting it here would leak into and break config-driven "
            "URL/credential unit tests",
        )


if __name__ == "__main__":
    unittest.main()
