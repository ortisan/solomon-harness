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

import ast
import os
import shlex
import unittest

import yaml

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CI_WORKFLOW = os.path.join(REPO_ROOT, ".github", "workflows", "ci.yml")
LIVE_TEST_CLASSES = (
    (
        os.path.join(REPO_ROOT, "tests", "test_database_client_multimodel.py"),
        "TestMultiModelLive",
    ),
    (
        os.path.join(REPO_ROOT, "tests", "test_harness_invariants.py"),
        "TestMcpServerGraphAndVectorTools",
    ),
    (
        os.path.join(REPO_ROOT, "tests", "test_memory_service.py"),
        "TestMemoryServiceMultiModelLive",
    ),
)
NETWORK_TEARDOWN_CALLS = {"close", "connect", "query", "signin", "use"}
# Every live-connection-holding class must release it via the bounded
# conftest helper (a daemon thread, joined with a timeout) so the
# connection's keepalive/recv background threads don't leak for the rest of
# the pytest process.
CLASSES_REQUIRING_BOUNDED_CLOSE = {
    "TestMultiModelLive",
    "TestMemoryServiceMultiModelLive",
    "TestMcpServerGraphAndVectorTools",
}


def _validate_job():
    with open(CI_WORKFLOW, encoding="utf-8") as fh:
        data = yaml.safe_load(fh)
    return data["jobs"]["validate"]


def _pytest_step(job):
    for step in job.get("steps", []):
        command = shlex.split(step.get("run", ""))
        if command[:3] == ["uv", "run", "pytest"]:
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

    def test_validate_job_has_a_bounded_runtime(self):
        timeout = _validate_job().get("timeout-minutes")
        self.assertIsInstance(timeout, int, "the validate job must define timeout-minutes")
        self.assertGreater(timeout, 0)
        self.assertLessEqual(
            timeout,
            60,
            "a blocked SDK call must not consume a runner for more than one hour",
        )

    def test_live_teardowns_do_not_remove_throwaway_databases(self):
        # The SurrealDB 2.x client performs blocking websocket reads without a
        # caller timeout. Removing the selected database during tearDown can
        # therefore block the entire suite. Every live test already uses a
        # unique database and CI destroys its tmpfs-backed service after the
        # job, so tearDown must only restore local process state.
        for module, class_name in LIVE_TEST_CLASSES:
            with self.subTest(module=os.path.basename(module), class_name=class_name):
                with open(module, encoding="utf-8") as fh:
                    source = fh.read()
                tree = ast.parse(source, filename=module)
                classes = [
                    node
                    for node in tree.body
                    if isinstance(node, ast.ClassDef) and node.name == class_name
                ]
                self.assertEqual(len(classes), 1, f"expected live test class {class_name}")
                teardowns = [
                    node
                    for node in classes[0].body
                    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
                    and node.name == "tearDown"
                ]
                self.assertTrue(teardowns, "expected at least one tearDown method")
                for teardown in teardowns:
                    body = ast.get_source_segment(source, teardown) or ""
                    self.assertNotIn("REMOVE DATABASE", body)
                    network_calls = {
                        call.func.attr
                        for call in ast.walk(teardown)
                        if isinstance(call, ast.Call) and isinstance(call.func, ast.Attribute)
                    } & NETWORK_TEARDOWN_CALLS
                    self.assertEqual(
                        network_calls,
                        set(),
                        "live-test tearDown must not perform blocking network I/O",
                    )
                    if class_name in CLASSES_REQUIRING_BOUNDED_CLOSE:
                        bounded_close_calls = [
                            call
                            for call in ast.walk(teardown)
                            if isinstance(call, ast.Call)
                            and isinstance(call.func, ast.Name)
                            and call.func.id == "close_surreal_quietly"
                        ]
                        self.assertTrue(
                            bounded_close_calls,
                            "tearDown must release its live connection via "
                            "close_surreal_quietly (bounded daemon-thread close), "
                            "or every test run leaks that connection's "
                            "keepalive/recv background threads for the rest of "
                            "the pytest process",
                        )


if __name__ == "__main__":
    unittest.main()
