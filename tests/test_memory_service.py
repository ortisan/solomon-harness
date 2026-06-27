import os
import sys
import tempfile
import unittest

WORKSPACE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if WORKSPACE not in sys.path:
    sys.path.insert(0, WORKSPACE)

from solomon_harness.memory_service import MemoryService, resolve_harness_dir  # noqa: E402


class TestMemoryService(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.svc = MemoryService(db_path=os.path.join(self.tmp.name, "memory.db"))

    def tearDown(self):
        self.svc.close()
        self.tmp.cleanup()

    def test_decision_roundtrip(self):
        result = self.svc.save_decision("Adopt MCP", "expose memory", "Approved", "qa")
        decision_id = result["decision_id"]
        self.assertIsNotNone(decision_id)
        decision = self.svc.get_decision(decision_id)["decision"]
        self.assertEqual(decision["title"], "Adopt MCP")

    def test_memory_roundtrip(self):
        self.svc.save_memory("k", "v", "cat")
        self.assertEqual(self.svc.get_memory("k")["value"], "v")

    def test_open_issues(self):
        self.svc.log_issue("gh-1", "Open one", "feature", "open")
        self.svc.log_issue("gh-2", "Closed one", "bug", "closed")
        issues = self.svc.get_open_issues()["issues"]
        self.assertEqual(len(issues), 1)
        self.assertEqual(issues[0]["github_id"], "gh-1")
        self.assertEqual(self.svc.get_issue("gh-1")["issue"]["title"], "Open one")

    def test_session_handoff_and_latest_activity(self):
        self.svc.save_session("s1", "qa", "ship it", [{"role": "user", "content": "hi"}])
        session = self.svc.get_session("s1")["session"]
        self.assertEqual(session["agent_name"], "qa")

        handoff = self.svc.log_handoff("qa", "sre", "plan", "/p", "pending")
        self.assertIsNotNone(handoff["handoff_id"])

        activity = self.svc.get_latest_activity()["activity"]
        self.assertIsNotNone(activity)

    def test_resolve_harness_dir_finds_package(self):
        self.assertEqual(resolve_harness_dir(WORKSPACE), WORKSPACE)


if __name__ == "__main__":
    unittest.main()
