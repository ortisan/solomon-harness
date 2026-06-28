import os
import tempfile
import unittest
from unittest.mock import patch

from solomon_harness import workflows
from solomon_harness import loop_lock
from solomon_harness.loop_lock import LoopLock


def _workspace_with_command(stage: str, body: str) -> str:
    tmp = tempfile.mkdtemp()
    cmd_dir = os.path.join(tmp, ".claude", "commands")
    os.makedirs(cmd_dir)
    with open(os.path.join(cmd_dir, f"solomon-{stage}.md"), "w", encoding="utf-8") as f:
        f.write(body)
    return tmp


class TestWorkflows(unittest.TestCase):
    def test_build_prompt_strips_frontmatter_and_substitutes_args(self):
        root = _workspace_with_command(
            "issue",
            "---\ndescription: x\n---\n\nShape this request: $ARGUMENTS into an issue.",
        )
        prompt = workflows.build_prompt(root, "issue", ["add", "rate", "limiting"])
        self.assertFalse(prompt.startswith("---"))
        self.assertIn("add rate limiting", prompt)
        self.assertNotIn("$ARGUMENTS", prompt)

    def test_build_prompt_missing_file_raises(self):
        root = tempfile.mkdtemp()
        with self.assertRaises(FileNotFoundError):
            workflows.build_prompt(root, "issue", [])

    def test_run_stage_rejects_unknown_stage(self):
        self.assertEqual(workflows.run_stage(".", "nonsense", []), 1)

    def test_run_stage_rejects_unknown_engine(self):
        root = _workspace_with_command("idea", "body $ARGUMENTS")
        self.assertEqual(workflows.run_stage(root, "idea", ["x"], engine="bogus"), 1)

    def test_run_stage_invokes_engine_with_prompt_on_stdin(self):
        root = _workspace_with_command("start", "---\nx\n---\nDo work on $ARGUMENTS")

        class _Proc:
            returncode = 0

        with patch("subprocess.run", return_value=_Proc()) as mock_run:
            rc = workflows.run_stage(root, "start", ["42"], engine="claude")
        self.assertEqual(rc, 0)
        args, kwargs = mock_run.call_args
        self.assertEqual(args[0], ["claude", "-p"])
        self.assertIn("Do work on 42", kwargs["input"])


class TestRunStageDriverLock(unittest.TestCase):
    """The portable single-driver gate lives in run_stage (both hosts run it)."""

    def _foreign_live_lock(self, root):
        # A live foreign lock: different session, this process's (alive) pid.
        path = loop_lock.resolve_lock_path(root)
        LoopLock(lock_path=path, session_id="foreign-driver", pid=os.getpid()).acquire()
        return path

    def test_mutating_stage_is_blocked_when_a_foreign_lock_is_held(self):
        root = _workspace_with_command("start", "---\nx\n---\nDo work on $ARGUMENTS")
        self._foreign_live_lock(root)
        with patch("subprocess.run") as mock_run:
            rc = workflows.run_stage(root, "start", ["1"], engine="claude")
        self.assertEqual(rc, 1)
        mock_run.assert_not_called()  # never reach the engine while another driver holds the lock

    def test_mutating_stage_acquires_and_releases_the_lock(self):
        root = _workspace_with_command("start", "---\nx\n---\nDo work on $ARGUMENTS")

        class _Proc:
            returncode = 0

        with patch("subprocess.run", return_value=_Proc()):
            rc = workflows.run_stage(root, "start", ["1"], engine="claude")
        self.assertEqual(rc, 0)
        # The lock is released after the stage completes.
        self.assertFalse(os.path.exists(loop_lock.resolve_lock_path(root)))

    def test_non_mutating_stage_ignores_the_lock(self):
        root = _workspace_with_command("idea", "---\nx\n---\nCapture $ARGUMENTS")
        self._foreign_live_lock(root)

        class _Proc:
            returncode = 0

        with patch("subprocess.run", return_value=_Proc()) as mock_run:
            rc = workflows.run_stage(root, "idea", ["x"], engine="claude")
        self.assertEqual(rc, 0)
        mock_run.assert_called_once()  # idea creates no branch/merge, so it is not gated


if __name__ == "__main__":
    unittest.main()
