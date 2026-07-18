import contextlib
import io
import json
import os
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from solomon_harness import workflows
from solomon_harness import loop_lock
from solomon_harness import loop_policy
from solomon_harness import loop_budget
from solomon_harness.loop_lock import LoopLock
from solomon_harness.worktree import worktree_root


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


def _workspace_with_canonical_command(stage: str, body: str) -> str:
    tmp = tempfile.mkdtemp()
    cmd_dir = os.path.join(tmp, ".agents", "solomon", "workflows")
    os.makedirs(cmd_dir)
    with open(os.path.join(cmd_dir, f"solomon-{stage}.md"), "w", encoding="utf-8") as f:
        f.write(body)
    return tmp


def _source_workspace_with_catalog_and_bridge(
    stage: str,
    catalog_body: str,
    bridge_body: str,
) -> str:
    tmp = tempfile.mkdtemp()
    catalog = os.path.join(tmp, "solomon_harness", "catalog", "workflows")
    bridge = os.path.join(tmp, ".claude", "commands")
    os.makedirs(catalog)
    os.makedirs(bridge)
    with open(os.path.join(catalog, f"solomon-{stage}.md"), "w", encoding="utf-8") as f:
        f.write(catalog_body)
    with open(os.path.join(bridge, f"solomon-{stage}.md"), "w", encoding="utf-8") as f:
        f.write(bridge_body)
    return tmp


def _git_workspace_with_command(stage: str, body: str) -> str:
    # worktree_root() shells out to git to resolve the main worktree, so the
    # --add-dir tests (#199) need a real (minimal) repo, unlike the plain
    # tempdir _workspace_with_command uses for every other run_stage test.
    root = _workspace_with_command(stage, body)
    subprocess.run(["git", "init", "-q"], cwd=root, check=True)
    subprocess.run(["git", "config", "user.email", "t@example.com"], cwd=root, check=True)
    subprocess.run(["git", "config", "user.name", "t"], cwd=root, check=True)
    open(os.path.join(root, ".keep"), "w").close()
    subprocess.run(["git", "add", "."], cwd=root, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "init"], cwd=root, check=True)
    return root


def _git_workspace_with_loop(stage: str, body: str, loop_block: dict) -> str:
    root = _git_workspace_with_command(stage, body)
    os.makedirs(os.path.join(root, ".agent"), exist_ok=True)
    with open(os.path.join(root, ".agent", "config.json"), "w", encoding="utf-8") as f:
        json.dump({"agent_name": "x", "loop": loop_block}, f)
    return root


class TestWorkflows(unittest.TestCase):
    def test_source_checkout_executes_catalog_body_instead_of_thin_claude_bridge(self):
        root = _source_workspace_with_catalog_and_bridge(
            "issue",
            "---\ndescription: canonical\n---\nCreate the issue for {{arguments}}.",
            "---\nallowed-tools: Bash(gh:*), AskUserQuestion\n---\nRead the catalog for $ARGUMENTS.",
        )

        prompt = workflows.build_prompt(root, "issue", ["portable", "install"])

        self.assertEqual(prompt, "Create the issue for portable install.")

    def test_allowed_tools_come_from_claude_bridge_not_neutral_catalog(self):
        root = _source_workspace_with_catalog_and_bridge(
            "issue",
            "---\ndescription: canonical\n---\nCreate {{arguments}}.",
            "---\nallowed-tools: Bash(gh:*), AskUserQuestion\n---\nRead the catalog.",
        )

        self.assertEqual(workflows._allowed_tools(root, "issue"), "Bash(gh:*)")

    def test_build_prompt_prefers_canonical_catalog_and_substitutes_neutral_args(self):
        root = _workspace_with_canonical_command(
            "issue",
            "---\ndescription: x\n---\n\nShape {{arguments}} through the canonical workflow.",
        )
        legacy = os.path.join(root, ".claude", "commands")
        os.makedirs(legacy)
        with open(os.path.join(legacy, "solomon-issue.md"), "w", encoding="utf-8") as f:
            f.write("legacy $ARGUMENTS")

        prompt = workflows.build_prompt(root, "issue", ["host", "neutral"])

        self.assertIn("host neutral through the canonical workflow", prompt)
        self.assertNotIn("legacy", prompt)
        self.assertNotIn("{{arguments}}", prompt)

    def test_build_prompt_rejects_a_symlinked_canonical_workflow(self):
        root = tempfile.mkdtemp()
        outside = os.path.join(root, "outside-issue.md")
        with open(outside, "w", encoding="utf-8") as f:
            f.write("Run external instructions")
        workflows_dir = os.path.join(root, ".agents", "solomon", "workflows")
        os.makedirs(workflows_dir)
        os.symlink(outside, os.path.join(workflows_dir, "solomon-issue.md"))

        with self.assertRaisesRegex(ValueError, "read path.*symlink"):
            workflows.build_prompt(root, "issue", [])

    def test_build_prompt_rejects_a_legacy_workflow_through_a_symlinked_directory(self):
        root = tempfile.mkdtemp()
        outside = tempfile.mkdtemp()
        with open(
            os.path.join(outside, "solomon-issue.md"), "w", encoding="utf-8"
        ) as f:
            f.write("Run external legacy instructions")
        claude_dir = os.path.join(root, ".claude")
        os.makedirs(claude_dir)
        os.symlink(outside, os.path.join(claude_dir, "commands"))

        with self.assertRaisesRegex(ValueError, "read path.*symlink"):
            workflows.build_prompt(root, "issue", [])

    def test_run_stage_fails_closed_for_every_engine_before_a_symlinked_workflow_runs(self):
        root = tempfile.mkdtemp()
        outside = os.path.join(root, "outside-idea.md")
        with open(outside, "w", encoding="utf-8") as f:
            f.write("Run external instructions")
        workflows_dir = os.path.join(root, ".agents", "solomon", "workflows")
        os.makedirs(workflows_dir)
        os.symlink(outside, os.path.join(workflows_dir, "solomon-idea.md"))

        for engine in ("claude", "agy", "codex"):
            with self.subTest(engine=engine):
                stderr = io.StringIO()
                with (
                    patch(
                        "solomon_harness.engine_adapters.build_engine_command"
                    ) as build_command,
                    contextlib.redirect_stderr(stderr),
                ):
                    rc = workflows.run_stage(root, "idea", [], engine=engine)

                self.assertEqual(rc, 1)
                build_command.assert_not_called()
                self.assertIn("symlink", stderr.getvalue())

    def test_claude_allowed_tools_rejects_symlinked_host_metadata(self):
        root = _workspace_with_canonical_command("idea", "Capture the idea")
        outside = os.path.join(root, "outside-skill.md")
        with open(outside, "w", encoding="utf-8") as f:
            f.write("---\nallowed-tools: Bash(*)\n---\n")
        skill_dir = os.path.join(root, ".claude", "skills", "solomon-idea")
        os.makedirs(skill_dir)
        os.symlink(outside, os.path.join(skill_dir, "SKILL.md"))

        stderr = io.StringIO()
        with (
            patch(
                "solomon_harness.engine_adapters.build_engine_command"
            ) as build_command,
            contextlib.redirect_stderr(stderr),
        ):
            rc = workflows.run_stage(root, "idea", [], engine="claude")

        self.assertEqual(rc, 1)
        build_command.assert_not_called()
        self.assertIn("symlink", stderr.getvalue())

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

    def test_build_prompt_omits_autonomous_directive_by_default(self):
        # A standalone `workflow` invocation (not driven by `loop`) must keep
        # presenting the interactive decision card unchanged (#194).
        root = _workspace_with_command(
            "workflow", "---\nx\n---\n## 3. Propose as an enumerated decision card, confirm, run"
        )
        prompt = workflows.build_prompt(root, "workflow", [])
        self.assertNotIn("headless", prompt.lower())
        self.assertNotIn(workflows.LOOP_AUTONOMOUS_MODE_DIRECTIVE, prompt)

    def test_build_prompt_injects_autonomous_directive_when_loop_driven(self):
        # The `loop` stage dispatches the same `workflow` command file, but with
        # `loop_driven=True` it must tell the model to skip the decision card and
        # go straight into the Autonomous Mode branch (#194).
        root = _workspace_with_command(
            "workflow", "---\nx\n---\n## 3. Propose as an enumerated decision card, confirm, run"
        )
        prompt = workflows.build_prompt(root, "workflow", [], loop_driven=True)
        self.assertIn(workflows.LOOP_AUTONOMOUS_MODE_DIRECTIVE, prompt)
        self.assertIn("no human is present", prompt.lower())
        self.assertIn(
            '"## 3. Propose as an enumerated decision card, confirm, run"', prompt
        )
        self.assertIn("AskUserQuestion", prompt)
        self.assertIn("Autonomous Mode", prompt)
        # The directive comes before the command file's own body.
        self.assertLess(
            prompt.index(workflows.LOOP_AUTONOMOUS_MODE_DIRECTIVE),
            prompt.index("## 3. Propose as an enumerated decision card, confirm, run"),
        )

    def test_run_stage_rejects_unknown_stage(self):
        self.assertEqual(workflows.run_stage(".", "nonsense", []), 1)

    def test_run_stage_rejects_unknown_engine(self):
        root = _workspace_with_command("idea", "body $ARGUMENTS")
        self.assertEqual(workflows.run_stage(root, "idea", ["x"], engine="bogus"), 1)

    def test_run_stage_supports_codex_with_native_trust_preserving_command(self):
        root = _workspace_with_canonical_command("idea", "Capture {{arguments}}")

        class _Proc:
            returncode = 0

        with patch("subprocess.run", return_value=_Proc()) as mock_run:
            rc = workflows.run_stage(root, "idea", ["x"], engine="codex")

        self.assertEqual(rc, 0)
        command = mock_run.call_args.args[0]
        self.assertEqual(command[:4], ["codex", "exec", "--sandbox", "workspace-write"])
        self.assertEqual(command[-1], "-")
        self.assertNotIn("--dangerously-bypass-hook-trust", command)

    def test_run_stage_uses_supported_agy_flags(self):
        root = _workspace_with_canonical_command("idea", "Capture {{arguments}}")

        class _Proc:
            returncode = 0

        with patch("subprocess.run", return_value=_Proc()) as mock_run:
            rc = workflows.run_stage(root, "idea", ["x"], engine="agy")

        self.assertEqual(rc, 0)
        command = mock_run.call_args.args[0]
        self.assertEqual(command[:3], ["agy", "-p", "-"])
        self.assertNotIn("-o", command)
        self.assertNotIn("--dangerously-skip-permissions", command)

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
        self.assertEqual(kwargs["cwd"], root)

    def test_run_stage_passes_allowed_tools_frontmatter_to_claude_engine(self):
        # #179: the headless engine has no TTY, so any tool outside the ambient
        # settings.json allowlist silently blocks. Each command file already
        # declares the exact tools it needs via `allowed-tools:`; run_stage must
        # forward that declaration to the claude engine instead of discarding it.
        root = _workspace_with_command(
            "refine",
            "---\nallowed-tools: Bash(gh:*), mcp__solomon-memory__get_issue\n---\nRefine $ARGUMENTS",
        )

        class _Proc:
            returncode = 0

        with patch("subprocess.run", return_value=_Proc()) as mock_run:
            rc = workflows.run_stage(root, "refine", ["172"], engine="claude")
        self.assertEqual(rc, 0)
        args, _kwargs = mock_run.call_args
        cmd = args[0]
        self.assertIn("--allowed-tools", cmd)
        self.assertEqual(
            cmd[cmd.index("--allowed-tools") + 1],
            "Bash(gh:*), mcp__solomon-memory__get_issue",
        )

    def test_run_stage_strips_askuserquestion_from_headless_allowed_tools(self):
        # #195: the headless engine has no TTY to answer AskUserQuestion, and
        # this repo's own frontmatter serves both the interactive Claude Code
        # command loader and this headless --allowed-tools passthrough. Forward
        # every declared tool except the ones that require a live human, so a
        # merge-style confirmation gate is unreachable headlessly by
        # construction, not by unverified tool behavior.
        root = _workspace_with_command(
            "review",
            "---\nallowed-tools: Bash(gh:*), AskUserQuestion, Task\n---\nReview $ARGUMENTS",
        )

        class _Proc:
            returncode = 0

        with patch("subprocess.run", return_value=_Proc()) as mock_run:
            rc = workflows.run_stage(root, "review", ["195"], engine="claude")
        self.assertEqual(rc, 0)
        args, _kwargs = mock_run.call_args
        cmd = args[0]
        self.assertIn("--allowed-tools", cmd)
        forwarded = cmd[cmd.index("--allowed-tools") + 1]
        self.assertNotIn("AskUserQuestion", forwarded)
        self.assertEqual(forwarded, "Bash(gh:*), Task")

    def test_run_stage_omits_allowed_tools_flag_when_only_interactive_only_tools_declared(self):
        root = _workspace_with_command(
            "review", "---\nallowed-tools: AskUserQuestion\n---\nReview $ARGUMENTS"
        )

        class _Proc:
            returncode = 0

        with patch("subprocess.run", return_value=_Proc()) as mock_run:
            workflows.run_stage(root, "review", ["195"], engine="claude")
        args, _kwargs = mock_run.call_args
        self.assertEqual(args[0], ["claude", "-p"])

    def test_run_stage_omits_allowed_tools_flag_when_frontmatter_declares_none(self):
        root = _workspace_with_command("start", "---\nx\n---\nDo work on $ARGUMENTS")

        class _Proc:
            returncode = 0

        with patch("subprocess.run", return_value=_Proc()) as mock_run:
            workflows.run_stage(root, "start", ["42"], engine="claude")
        args, _kwargs = mock_run.call_args
        self.assertEqual(args[0], ["claude", "-p"])

    def test_run_stage_does_not_pass_allowed_tools_to_non_claude_engine(self):
        root = _workspace_with_command(
            "refine",
            "---\nallowed-tools: Bash(gh:*)\n---\nRefine $ARGUMENTS",
        )

        class _Proc:
            returncode = 0

        with patch("subprocess.run", return_value=_Proc()) as mock_run:
            workflows.run_stage(root, "refine", ["172"], engine="agy")
        args, _kwargs = mock_run.call_args
        self.assertNotIn("--allowed-tools", args[0])

    def _run_stage_capturing_engine_cmd(self, root, stage, args, engine):
        # worktree_root() (and LoopLock's `ps` liveness probe) call the real
        # subprocess.run; only the actual engine launch (claude/agy)
        # must be faked, so real git calls resolve against the git repo
        # _git_workspace_with_command set up rather than a blanket mock.
        real_run = subprocess.run
        captured = []

        def fake_run(cmd, *a, **kw):
            if cmd and os.path.basename(cmd[0]) in ("claude", "agy", "codex"):
                captured.append(cmd)

                class _Proc:
                    returncode = 0

                return _Proc()
            return real_run(cmd, *a, **kw)

        with patch("subprocess.run", side_effect=fake_run):
            workflows.run_stage(root, stage, args, engine=engine)
        return captured[0]

    def test_run_stage_grants_add_dir_for_every_engine_on_a_locked_stage(self):
        # #199/#240: each nested engine's file tools are confined to
        # workspace_root; `start` (and any LOCKED_STAGES) does its real work
        # inside a sibling worktree outside that boundary. Grant exactly that
        # directory, nothing broader.
        for engine in ("claude", "agy", "codex"):
            with self.subTest(engine=engine):
                root = _git_workspace_with_command(
                    "start", "---\nx\n---\nDo work on $ARGUMENTS"
                )
                cmd = self._run_stage_capturing_engine_cmd(
                    root, "start", ["199"], engine
                )
                self.assertIn("--add-dir", cmd)
                self.assertEqual(
                    cmd[cmd.index("--add-dir") + 1], worktree_root(root)
                )

    def test_run_stage_omits_add_dir_for_a_non_locked_stage(self):
        root = _git_workspace_with_command("idea", "body $ARGUMENTS")
        cmd = self._run_stage_capturing_engine_cmd(root, "idea", ["x"], "claude")
        self.assertNotIn("--add-dir", cmd)

    def test_run_stage_grants_add_dir_under_l2_cost_capture(self):
        # #199: the cmd list is built once, before the capture_cost branch
        # picks which subprocess.run call captures cost — confirm --add-dir
        # survives into that branch too, not just the default human-level path.
        root = _git_workspace_with_loop(
            "start", "---\nx\n---\nDo work on $ARGUMENTS", {"autonomy": "L2"}
        )
        cmd = self._run_stage_capturing_engine_cmd(root, "start", ["199"], "claude")
        self.assertIn("--add-dir", cmd)
        self.assertEqual(cmd[cmd.index("--add-dir") + 1], worktree_root(root))


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
        # GIT_TERMINAL_PROMPT=0 is deliberately (re)set by clean_git_env so a
        # stalled credential prompt fails fast; it is the one GIT_* key allowed
        # through. No *inherited* GIT_* var may leak.
        self.assertFalse(any(k.startswith("GIT_") for k in env if k != "GIT_TERMINAL_PROMPT"))

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
        # GIT_TERMINAL_PROMPT=0 is deliberately (re)set by clean_git_env so a
        # stalled credential prompt fails fast; it is the one GIT_* key allowed
        # through. No *inherited* GIT_* var may leak.
        self.assertFalse(any(k.startswith("GIT_") for k in env if k != "GIT_TERMINAL_PROMPT"))


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

    def test_board_mutating_idea_stage_respects_the_lock(self):
        root = _workspace_with_command("idea", "---\nx\n---\nCapture $ARGUMENTS")
        self._foreign_live_lock(root)
        with patch("subprocess.run") as mock_run:
            rc = workflows.run_stage(root, "idea", ["x"], engine="claude")
        self.assertEqual(rc, 1)
        self.assertFalse(
            [
                call
                for call in mock_run.call_args_list
                if call.args and call.args[0][:2] == ["claude", "-p"]
            ]
        )


class TestRunStageSessionIdPropagation(unittest.TestCase):
    """#197: the loop-driven `claude -p` child must inherit the driver's own
    session_id, so a nested `solomon-harness dev <stage>` it shells out to
    (the Autonomous Mode branch acting on its own scan) resolves the SAME
    session_id and reenters the still-held parent lock instead of being
    refused as a foreign competing driver."""

    def test_engine_subprocess_env_carries_the_drivers_session_id(self):
        root = _workspace_with_command("start", "---\nx\n---\nDo work on $ARGUMENTS")

        class _Proc:
            returncode = 0

        with patch.dict(os.environ, {"SOLOMON_SESSION_ID": "driver-42"}):
            with patch("subprocess.run", return_value=_Proc()) as mock_run:
                rc = workflows.run_stage(root, "start", ["1"], engine="claude")
        self.assertEqual(rc, 0)
        _, kwargs = mock_run.call_args
        env = kwargs.get("env")
        self.assertIsNotNone(env)
        self.assertEqual(env.get("SOLOMON_SESSION_ID"), "driver-42")

    def test_default_session_id_fallback_still_propagates_to_the_child(self):
        # The actual gap in #197: SOLOMON_SESSION_ID is usually never set
        # upstream at all, so the acquired lock's session_id falls back to a
        # computed default that only ever lived on the LoopLock instance,
        # never as an exported env var; it must be explicitly injected into the
        # child's env for a nested call to resolve the same one. That default
        # now comes from claim.get_current_session_id() (host:pid:entropy,
        # cached), the SINGLE source the per-issue claim layer uses too, so the
        # lock and the claim never diverge and a nested start cannot
        # self-deadlock on its own claim.
        root = _workspace_with_command("start", "---\nx\n---\nDo work on $ARGUMENTS")
        stripped = {
            k: v for k, v in os.environ.items()
            if k not in ("SOLOMON_SESSION_ID", "CLAUDE_SESSION_ID")
        }

        class _Proc:
            returncode = 0

        from solomon_harness import claim
        with patch.dict(os.environ, stripped, clear=True):
            with patch("subprocess.run", return_value=_Proc()) as mock_run:
                rc = workflows.run_stage(root, "start", ["1"], engine="claude")
            # Resolved inside the stripped env: returns the same cached identity
            # the lock acquired during run_stage.
            expected = claim.get_current_session_id()
        self.assertEqual(rc, 0)
        _, kwargs = mock_run.call_args
        env = kwargs.get("env")
        self.assertIsNotNone(env)
        self.assertEqual(env.get("SOLOMON_SESSION_ID"), expected)
        self.assertEqual(expected.count(":"), 2, "unified identity carries the entropy suffix")

    def test_cost_capture_path_also_carries_the_drivers_session_id(self):
        # L2: the cost-capturing subprocess.run call is a second, separate call
        # site -- confirm the same propagation happens there too.
        root = _workspace_with_loop("start", "---\nx\n---\nGo $ARGUMENTS", {"autonomy": "L2"})

        class _Proc:
            returncode = 0
            stdout = '{"total_cost_usd": 0.5}'

        with patch.dict(os.environ, {"SOLOMON_SESSION_ID": "driver-42"}):
            with patch("subprocess.run", return_value=_Proc()) as mock_run:
                rc = workflows.run_stage(root, "start", ["1"], engine="claude")
        self.assertEqual(rc, 0)
        _, kwargs = mock_run.call_args
        env = kwargs.get("env")
        self.assertIsNotNone(env)
        self.assertEqual(env.get("SOLOMON_SESSION_ID"), "driver-42")

    def test_nested_dev_stage_reenters_the_still_held_parent_lock(self):
        # Reproduces the exact reported scenario: the parent `dev loop` process
        # holds the lock (session "outer-driver") and is synchronously blocked
        # on its `claude -p` child. From inside that child, the model shells
        # out to `solomon-harness dev review 195`; that nested process resolves
        # its LoopLock's session_id from the propagated SOLOMON_SESSION_ID env
        # var, so it must reenter rather than be refused.
        root = _workspace_with_command("review", "---\nx\n---\nReview $ARGUMENTS")
        path = loop_lock.resolve_lock_path(root)
        LoopLock(lock_path=path, session_id="outer-driver", pid=os.getpid()).acquire()

        class _Proc:
            returncode = 0

        with patch.dict(os.environ, {"SOLOMON_SESSION_ID": "outer-driver"}):
            with patch("subprocess.run", return_value=_Proc()) as mock_run:
                rc = workflows.run_stage(root, "review", ["195"], engine="claude")
        self.assertEqual(rc, 0)
        self.assertTrue(
            [c for c in mock_run.call_args_list if c.args and c.args[0][:2] == ["claude", "-p"]]
        )
        # The outer holder's lock must survive: a reentrant nested call must
        # not release the lock out from under its still-running parent.
        held = LoopLock(lock_path=path, session_id="outer-driver").read()
        self.assertIsNotNone(held, "the nested reentrant call must not release the parent's lock")
        self.assertEqual(held["session_id"], "outer-driver")

    def test_a_genuinely_different_session_is_still_refused(self):
        # Regression guard: propagating SOLOMON_SESSION_ID must not become a
        # blanket bypass -- a DIFFERENT session_id is still a foreign driver.
        root = _workspace_with_command("review", "---\nx\n---\nReview $ARGUMENTS")
        path = loop_lock.resolve_lock_path(root)
        LoopLock(lock_path=path, session_id="outer-driver", pid=os.getpid()).acquire()

        with patch.dict(os.environ, {"SOLOMON_SESSION_ID": "some-other-driver"}):
            with patch("subprocess.run") as mock_run:
                rc = workflows.run_stage(root, "review", ["195"], engine="claude")
        self.assertEqual(rc, 1)
        self.assertFalse(
            [c for c in mock_run.call_args_list if c.args and c.args[0][:2] == ["claude", "-p"]]
        )


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


class TestStandingReconcileStage(unittest.TestCase):
    def test_reconcile_stage_is_registered_and_single_driver_locked(self):
        self.assertIn("reconcile", workflows.STAGES)
        self.assertIn("reconcile", workflows.LOCKED_STAGES)


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

    def test_loop_forwards_the_workflow_stage_allowed_tools(self):
        # #179/#181: `loop` remaps to the `workflow` stage's own command file via
        # prompt_stage — confirm --allowed-tools is forwarded on this path too,
        # not only on a stage invoked directly (e.g. refine/start).
        root = _workspace_with_command(
            "workflow",
            "---\nallowed-tools: Bash(gh:*), mcp__solomon-memory__get_open_issues\n---\nScan $ARGUMENTS",
        )

        class _Proc:
            returncode = 0

        with patch("subprocess.run", side_effect=_answering_ps_probes([_Proc()])) as mock_run:
            rc = workflows.run_stage(root, "loop", [], engine="claude")
        self.assertEqual(rc, 0)
        calls = _engine_calls(mock_run)
        self.assertEqual(len(calls), 1)
        args, _kwargs = calls[0]
        cmd = args[0]
        self.assertIn("--allowed-tools", cmd)
        self.assertEqual(
            cmd[cmd.index("--allowed-tools") + 1],
            "Bash(gh:*), mcp__solomon-memory__get_open_issues",
        )

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


class TestLoopInjectsAutonomousModeDirective(unittest.TestCase):
    """#194: a headless `loop`-driven iteration must skip the interactive
    decision card and proceed straight into Autonomous Mode; a direct
    `dev workflow` invocation must keep seeing the unmodified card."""

    def test_loop_dispatches_the_directive_prefixed_prompt(self):
        root = _workspace_with_command(
            "workflow",
            "---\nx\n---\n## 3. Propose as an enumerated decision card, confirm, run\nScan $ARGUMENTS",
        )

        class _Proc:
            returncode = 0

        with patch("subprocess.run", side_effect=_answering_ps_probes([_Proc()])) as mock_run:
            rc = workflows.run_stage(root, "loop", [], engine="claude")
        self.assertEqual(rc, 0)
        calls = _engine_calls(mock_run)
        self.assertEqual(len(calls), 1)
        _, kwargs = calls[0]
        self.assertIn(workflows.LOOP_AUTONOMOUS_MODE_DIRECTIVE, kwargs["input"])
        self.assertIn("AskUserQuestion", kwargs["input"])

    def test_loop_injects_the_directive_on_every_iteration(self):
        root = _workspace_with_command(
            "workflow",
            "---\nx\n---\n## 3. Propose as an enumerated decision card, confirm, run\nScan $ARGUMENTS",
        )

        class _Proc:
            returncode = 0

        with patch(
            "subprocess.run", side_effect=_answering_ps_probes([_Proc(), _Proc()])
        ) as mock_run:
            rc = workflows.run_stage(root, "loop", ["--concurrency", "2"], engine="claude")
        self.assertEqual(rc, 0)
        calls = _engine_calls(mock_run)
        self.assertEqual(len(calls), 2)
        for _, kwargs in calls:
            self.assertIn(workflows.LOOP_AUTONOMOUS_MODE_DIRECTIVE, kwargs["input"])

    def test_direct_workflow_invocation_does_not_receive_the_directive(self):
        # A direct `dev workflow` call (not driven by `loop`) must build the
        # exact same prompt it built before this fix — the decision card stays.
        root = _workspace_with_command(
            "workflow",
            "---\nx\n---\n## 3. Propose as an enumerated decision card, confirm, run\nScan $ARGUMENTS",
        )

        class _Proc:
            returncode = 0

        with patch("subprocess.run", side_effect=_answering_ps_probes([_Proc()])) as mock_run:
            rc = workflows.run_stage(root, "workflow", ["7"], engine="claude")
        self.assertEqual(rc, 0)
        calls = _engine_calls(mock_run)
        self.assertEqual(len(calls), 1)
        _, kwargs = calls[0]
        self.assertNotIn(workflows.LOOP_AUTONOMOUS_MODE_DIRECTIVE, kwargs["input"])
        self.assertNotIn("headless", kwargs["input"].lower())


if __name__ == "__main__":
    unittest.main()
