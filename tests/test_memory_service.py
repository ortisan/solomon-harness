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
        from unittest.mock import patch
        self.patcher = patch("os.path.isfile", side_effect=lambda path: False if "config.json" in path else os.path.isfile(path))
        self.patcher.start()
        self.svc = MemoryService(db_path=os.path.join(self.tmp.name, "memory.db"))

    def tearDown(self):
        self.svc.close()
        self.patcher.stop()
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

    def test_milestones_and_releases(self):
        mid = self.svc.create_milestone("M1", "goals", "2026-07-01", "active")["milestone_id"]
        self.assertEqual(len(self.svc.list_milestones()["milestones"]), 1)

        rid = self.svc.save_release(
            "v1.0.0", tag="v1.0.0", notes="first", issue_github_id="42", milestone_id=str(mid)
        )["release_id"]
        self.assertIsNotNone(rid)
        rel = self.svc.get_release(rid)["release"]
        self.assertEqual(rel["version"], "v1.0.0")
        self.assertEqual(rel["issue_github_id"], "42")
        self.assertEqual(len(self.svc.list_releases()["releases"]), 1)

    def test_resolve_harness_dir_finds_package(self):
        self.assertEqual(resolve_harness_dir(WORKSPACE), WORKSPACE)


if __name__ == "__main__":
    unittest.main()
