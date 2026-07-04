import contextlib
import io
import json
import os
import tempfile
import unittest
from unittest.mock import patch

from solomon_harness import workflows
from solomon_harness import loop_lock
from solomon_harness import loop_policy
from solomon_harness import loop_budget
from solomon_harness.loop_lock import LoopLock


def _workspace_with_loop(stage, body, loop_block):
    root = _workspace_with_command(stage, body)
    os.makedirs(os.path.join(root, ".agent"), exist_ok=True)
    with open(os.path.join(root, ".agent", "config.json"), "w", encoding="utf-8") as f:
        json.dump({"agent_name": "x", "loop": loop_block}, f)
    return root


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


class TestRunStageGitEnvHygiene(unittest.TestCase):
    """run_stage's two engine launches must not leak inherited GIT_* vars into
    the child process (they would redirect a git call the engine makes back to
    whatever repo/worktree the harness happened to be invoked from)."""

    def _leaked_git_env(self):
        return patch.dict(
            os.environ,
            {"GIT_DIR": "/tmp/leaked/.git", "GIT_WORK_TREE": "/tmp/leaked", "GIT_INDEX_FILE": "/tmp/leaked/index"},
        )

    def test_default_path_strips_git_env(self):
        # Human level (default): the plain, non-cost-capturing subprocess.run call.
        root = _workspace_with_command("start", "---\nx\n---\nDo work on $ARGUMENTS")

        class _Proc:
            returncode = 0

        with self._leaked_git_env():
            with patch("subprocess.run", return_value=_Proc()) as mock_run:
                rc = workflows.run_stage(root, "start", ["1"], engine="claude")
        self.assertEqual(rc, 0)
        _, kwargs = mock_run.call_args
        env = kwargs.get("env")
        self.assertIsNotNone(env, "run_stage must pass an explicit, scrubbed env")
        self.assertFalse(any(k.startswith("GIT_") for k in env))

    def test_cost_capture_path_strips_git_env(self):
        # L2: the cost-capturing subprocess.run call (a second, separate call site).
        root = _workspace_with_loop("start", "---\nx\n---\nGo $ARGUMENTS", {"autonomy": "L2"})

        class _Proc:
            returncode = 0
            stdout = '{"total_cost_usd": 0.5}'

        with self._leaked_git_env():
            with patch("subprocess.run", return_value=_Proc()) as mock_run:
                rc = workflows.run_stage(root, "start", ["1"], engine="claude")
        self.assertEqual(rc, 0)
        _, kwargs = mock_run.call_args
        env = kwargs.get("env")
        self.assertIsNotNone(env, "run_stage must pass an explicit, scrubbed env")
        self.assertFalse(any(k.startswith("GIT_") for k in env))


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
        # Never reach the engine while another driver holds the lock. Staleness
        # checking may itself shell out to `ps` (through this same seam) to
        # compare process start times, so assert on the engine call specifically.
        self.assertFalse(
            [c for c in mock_run.call_args_list if c.args and c.args[0][:2] == ["claude", "-p"]]
        )

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


class TestRunStageAutonomyPolicy(unittest.TestCase):
    """The portable governed-autonomy gate, enforced in run_stage on both hosts."""

    def test_l1_blocks_a_mutating_stage(self):
        root = _workspace_with_loop("start", "---\nx\n---\nGo $ARGUMENTS", {"autonomy": "L1"})
        with patch("subprocess.run") as mock_run:
            rc = workflows.run_stage(root, "start", ["1"], engine="claude")
        self.assertEqual(rc, 3)
        mock_run.assert_not_called()

    def test_release_is_blocked_even_at_l3(self):
        root = _workspace_with_loop("release", "---\nx\n---\nShip $ARGUMENTS", {"autonomy": "L3"})
        with patch("subprocess.run") as mock_run:
            rc = workflows.run_stage(root, "release", ["1"], engine="claude")
        self.assertEqual(rc, 3)
        mock_run.assert_not_called()

    def test_l2_allows_start(self):
        root = _workspace_with_loop("start", "---\nx\n---\nGo $ARGUMENTS", {"autonomy": "L2"})

        class _Proc:
            returncode = 0

        with patch("subprocess.run", return_value=_Proc()) as mock_run:
            rc = workflows.run_stage(root, "start", ["1"], engine="claude")
        self.assertEqual(rc, 0)
        # The lock also shells out to `ps` (through this same seam) to record
        # the holder's process start time, so assert on the engine call itself.
        engine_calls = [c for c in mock_run.call_args_list if c.args and c.args[0][:2] == ["claude", "-p"]]
        self.assertEqual(len(engine_calls), 1)

    def test_kill_switch_blocks_everything(self):
        root = _workspace_with_command("workflow", "---\nx\n---\nScan $ARGUMENTS")
        loop_policy.write_stop(root)
        with patch("subprocess.run") as mock_run:
            rc = workflows.run_stage(root, "workflow", ["1"], engine="claude")
        self.assertEqual(rc, 3)
        mock_run.assert_not_called()

    def test_l3_requires_lock_on_a_nonmutating_stage(self):
        # At L3 every stage but 'workflow' must hold the lock; a foreign lock blocks idea.
        root = _workspace_with_loop("idea", "---\nx\n---\nCapture $ARGUMENTS", {"autonomy": "L3"})
        path = loop_lock.resolve_lock_path(root)
        LoopLock(lock_path=path, session_id="foreign", pid=os.getpid()).acquire()
        with patch("subprocess.run") as mock_run:
            rc = workflows.run_stage(root, "idea", ["x"], engine="claude")
        self.assertEqual(rc, 1)
        # Staleness checking may itself shell out to `ps` (through this same
        # seam) to compare process start times; assert the engine specifically.
        self.assertFalse(
            [c for c in mock_run.call_args_list if c.args and c.args[0][:2] == ["claude", "-p"]]
        )

    def test_budget_ceiling_blocks_at_l2(self):
        root = _workspace_with_loop(
            "start", "---\nx\n---\nGo $ARGUMENTS",
            {"autonomy": "L2", "daily_cost_ceiling_usd": 1.0},
        )
        loop_budget.record(root, 1.5)  # today's spend already over the $1 ceiling
        with patch("subprocess.run") as mock_run:
            rc = workflows.run_stage(root, "start", ["1"], engine="claude")
        self.assertEqual(rc, 3)
        mock_run.assert_not_called()

    def test_cost_capture_records_at_l2(self):
        root = _workspace_with_loop("start", "---\nx\n---\nGo $ARGUMENTS", {"autonomy": "L2"})

        class _Proc:
            returncode = 0
            stdout = '{"total_cost_usd": 0.5}'

        with patch("subprocess.run", return_value=_Proc()) as mock_run:
            rc = workflows.run_stage(root, "start", ["1"], engine="claude")
        self.assertEqual(rc, 0)
        args, _ = mock_run.call_args
        self.assertEqual(args[0], ["claude", "-p", "--output-format", "json"])
        self.assertAlmostEqual(loop_budget.daily_spend(root), 0.5)


def _answering_ps_probes(engine_procs):
    """side_effect for a subprocess.run mock: answer the loop-lock's
    ``ps -o lstart=`` staleness probes with a fixed start time and hand the
    queued fake procs to every other (engine) invocation."""
    queue = list(engine_procs)

    class _PsProc:
        returncode = 0
        stdout = "boot\n"

    def run(cmd, *args, **kwargs):
        if cmd and cmd[0] == "ps":
            return _PsProc()
        return queue.pop(0)

    return run


def _engine_calls(mock_run):
    """The subprocess.run calls that reached an engine, ignoring lock probes."""
    return [c for c in mock_run.call_args_list if c.args[0][0] != "ps"]


class TestStageRename(unittest.TestCase):
    """The orchestrator is `workflow` (formerly `loop`) and the autonomous
    parallel loop is `loop` (formerly `loop-auto`); `loop-auto` survives only
    as a deprecated alias for `loop`."""

    def test_workflow_stage_is_registered_and_dispatches_its_command_file(self):
        self.assertIn("workflow", workflows.STAGES)
        self.assertIn("workflow", workflows.LOCKED_STAGES)
        self.assertNotIn("loop-auto", workflows.STAGES)
        root = _workspace_with_command("workflow", "---\nx\n---\nScan $ARGUMENTS")

        class _Proc:
            returncode = 0

        with patch("subprocess.run", side_effect=_answering_ps_probes([_Proc()])) as mock_run:
            rc = workflows.run_stage(root, "workflow", ["7"], engine="claude")
        self.assertEqual(rc, 0)
        calls = _engine_calls(mock_run)
        self.assertEqual(len(calls), 1)
        args, kwargs = calls[0]
        self.assertEqual(args[0], ["claude", "-p"])
        self.assertIn("Scan 7", kwargs["input"])

    def test_loop_auto_alias_runs_the_loop_stage_and_warns(self):
        root = _workspace_with_command("workflow", "---\nx\n---\nScan $ARGUMENTS")

        class _Proc:
            returncode = 0

        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr):
            with patch(
                "subprocess.run", side_effect=_answering_ps_probes([_Proc(), _Proc()])
            ) as mock_run:
                rc = workflows.run_stage(
                    root, "loop-auto", ["--concurrency", "2"], engine="claude"
                )
        self.assertEqual(rc, 0)
        self.assertEqual(len(_engine_calls(mock_run)), 2)
        self.assertIn("deprecated", stderr.getvalue())
        self.assertIn("loop", stderr.getvalue())


class TestLoopStage(unittest.TestCase):
    """`loop` (the autonomous parallel loop, formerly `loop-auto`) drives N
    iterations of the existing `workflow` stage logic — it must not build a new
    orchestration mechanism, just repeat what `workflow` does per-iteration
    under the same single-driver lock."""

    def test_loop_is_registered_and_dispatches_the_workflow_prompt(self):
        self.assertIn("loop", workflows.STAGES)
        root = _workspace_with_command("workflow", "---\nx\n---\nScan $ARGUMENTS")

        class _Proc:
            returncode = 0

        with patch("subprocess.run", side_effect=_answering_ps_probes([_Proc()])) as mock_run:
            rc = workflows.run_stage(root, "loop", [], engine="claude")
        self.assertEqual(rc, 0)
        calls = _engine_calls(mock_run)
        self.assertEqual(len(calls), 1)
        args, kwargs = calls[0]
        self.assertEqual(args[0], ["claude", "-p"])
        self.assertIn("Scan", kwargs["input"])

    def test_loop_respects_the_concurrency_argument(self):
        root = _workspace_with_command("workflow", "---\nx\n---\nScan $ARGUMENTS")

        class _Proc:
            returncode = 0

        with patch(
            "subprocess.run", side_effect=_answering_ps_probes([_Proc(), _Proc(), _Proc()])
        ) as mock_run:
            rc = workflows.run_stage(root, "loop", ["--concurrency", "3"], engine="claude")
        self.assertEqual(rc, 0)
        self.assertEqual(len(_engine_calls(mock_run)), 3)

    def test_loop_strips_concurrency_before_building_the_prompt(self):
        root = _workspace_with_command("workflow", "---\nx\n---\nScan $ARGUMENTS")

        class _Proc:
            returncode = 0

        with patch("subprocess.run", return_value=_Proc()) as mock_run:
            workflows.run_stage(root, "loop", ["--concurrency", "2", "42"], engine="claude")
        _, kwargs = mock_run.call_args
        self.assertIn("Scan 42", kwargs["input"])
        self.assertNotIn("--concurrency", kwargs["input"])

    def test_loop_stops_at_the_first_failed_iteration(self):
        root = _workspace_with_command("workflow", "---\nx\n---\nScan $ARGUMENTS")

        class _Proc:
            def __init__(self, rc):
                self.returncode = rc

        with patch(
            "subprocess.run", side_effect=_answering_ps_probes([_Proc(1), _Proc(0), _Proc(0)])
        ) as mock_run:
            rc = workflows.run_stage(root, "loop", ["--concurrency", "3"], engine="claude")
        self.assertEqual(rc, 1)
        self.assertEqual(len(_engine_calls(mock_run)), 1)

    def test_loop_invalid_concurrency_errors_without_dispatch(self):
        root = _workspace_with_command("workflow", "---\nx\n---\nScan $ARGUMENTS")
        with patch("subprocess.run") as mock_run:
            rc = workflows.run_stage(root, "loop", ["--concurrency", "nope"], engine="claude")
        self.assertEqual(rc, 1)
        mock_run.assert_not_called()

    def test_loop_acquires_and_releases_the_lock(self):
        root = _workspace_with_command("workflow", "---\nx\n---\nScan $ARGUMENTS")

        class _Proc:
            returncode = 0

        with patch("subprocess.run", return_value=_Proc()):
            rc = workflows.run_stage(root, "loop", ["--concurrency", "2"], engine="claude")
        self.assertEqual(rc, 0)
        # The lock is released once the whole run (all iterations) completes.
        self.assertFalse(os.path.exists(loop_lock.resolve_lock_path(root)))

    def test_loop_is_blocked_when_a_foreign_lock_is_held(self):
        root = _workspace_with_command("workflow", "---\nx\n---\nScan $ARGUMENTS")
        path = loop_lock.resolve_lock_path(root)
        LoopLock(lock_path=path, session_id="foreign-driver", pid=os.getpid()).acquire()
        with patch("subprocess.run") as mock_run:
            rc = workflows.run_stage(root, "loop", ["--concurrency", "2"], engine="claude")
        self.assertEqual(rc, 1)
        # Never reach the engine while another driver holds the lock; the
        # mocked calls that do appear are the lock's own ps staleness probes.
        self.assertEqual(_engine_calls(mock_run), [])


if __name__ == "__main__":
    unittest.main()
