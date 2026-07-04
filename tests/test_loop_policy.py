"""Tests for governed autonomy (Phase 2): the L1/L2/L3 ladder, denylist, kill-switch."""

import json
import os
import tempfile
import unittest

from solomon_harness import loop_policy
from solomon_harness.loop_policy import LoopPolicy


def _policy(level, root=None, **kw):
    return LoopPolicy(root or tempfile.mkdtemp(), level=level, **kw)


class TestLadder(unittest.TestCase):
    def test_human_allows_everything(self):
        p = _policy("human")
        for stage in ("loop", "start", "review", "idea"):
            self.assertTrue(p.decide_stage(stage).allowed, stage)
        self.assertFalse(p.decide_stage("release").allowed)

    def test_release_is_permanently_human_gated(self):
        for level in ("L1", "L2", "L3"):
            self.assertFalse(_policy(level).decide_stage("release").allowed, level)

    def test_l1_is_report_only(self):
        p = _policy("L1")
        self.assertTrue(p.decide_stage("loop").allowed)
        self.assertFalse(p.decide_stage("start").allowed)
        self.assertFalse(p.decide_stage("idea").allowed)

    def test_l2_l3_allow_up_to_review(self):
        for level in ("L2", "L3"):
            p = _policy(level)
            self.assertTrue(p.decide_stage("start").allowed, level)
            self.assertTrue(p.decide_stage("review").allowed, level)
            self.assertFalse(p.decide_stage("release").allowed, level)

    def test_l3_requires_lock_for_mutating_stages(self):
        p = _policy("L3")
        self.assertTrue(p.requires_lock("start"))
        self.assertFalse(p.requires_lock("loop"))
        self.assertFalse(_policy("L2").requires_lock("start"))

    def test_scan_loops_are_l2_l3_automation(self):
        self.assertTrue(_policy("L2").decide_stage("scan-arch").allowed)
        self.assertTrue(_policy("L3").decide_stage("scan-dedup").allowed)
        self.assertFalse(_policy("L1").decide_stage("scan-arch").allowed)  # not report-only
        self.assertTrue(_policy("human").decide_stage("scan-arch").allowed)

    def test_invalid_level_fails_closed(self):
        # A typo must never silently become unrestricted.
        p = _policy("l2")
        self.assertFalse(p.decide_stage("loop").allowed)
        self.assertFalse(p.decide_stage("start").allowed)


class TestKillSwitch(unittest.TestCase):
    def test_stop_halts_all_stages_then_clears(self):
        root = tempfile.mkdtemp()
        p = LoopPolicy(root, level="L2")
        self.assertTrue(p.decide_stage("start").allowed)
        loop_policy.write_stop(root)
        self.assertTrue(p.is_halted())
        self.assertFalse(p.decide_stage("start").allowed)
        self.assertFalse(p.decide_stage("loop").allowed)  # halt blocks even L1-allowed
        self.assertTrue(loop_policy.clear_stop(root))
        self.assertFalse(p.is_halted())
        self.assertTrue(p.decide_stage("start").allowed)

    def test_halt_blocks_even_human_level(self):
        root = tempfile.mkdtemp()
        loop_policy.write_stop(root)
        self.assertFalse(LoopPolicy(root, level="human").decide_stage("start").allowed)


class TestDenylist(unittest.TestCase):
    def test_denied_paths(self):
        p = _policy("L2")
        for denied in (
            "agents/_audit_probe_/.agent/secure_vault.enc",
            ".agent/config.json",
            "app/secrets/token.txt",
            ".git/config",
            "service/.env",
            "private.pem",
        ):
            self.assertTrue(p.is_denied_path(denied), denied)

    def test_allowed_paths(self):
        p = _policy("L2")
        for ok in ("solomon_harness/cli.py", "tests/test_x.py", "docs/readme.md"):
            self.assertFalse(p.is_denied_path(ok), ok)

    def test_absolute_path_is_relativized_against_root(self):
        root = tempfile.mkdtemp()
        p = LoopPolicy(root, level="L2")
        self.assertTrue(p.is_denied_path(os.path.join(root, ".agent", "config.json")))


class TestDeniedWrite(unittest.TestCase):
    def _policy(self, root=None):
        return LoopPolicy(root or tempfile.mkdtemp(), level="L2")

    def test_blocks_edit_to_denied_path(self):
        block, reason = loop_policy.denied_write_verdict(
            {"tool_name": "Edit", "tool_input": {"file_path": ".agent/config.json"}}, self._policy()
        )
        self.assertTrue(block)
        self.assertIn("denylist", reason)

    def test_blocks_absolute_denied_path(self):
        root = tempfile.mkdtemp()
        block, _ = loop_policy.denied_write_verdict(
            {"tool_name": "Write", "tool_input": {"file_path": os.path.join(root, ".agent", "config.json")}},
            self._policy(root),
        )
        self.assertTrue(block)

    def test_allows_normal_write(self):
        block, _ = loop_policy.denied_write_verdict(
            {"tool_name": "Edit", "tool_input": {"file_path": "solomon_harness/cli.py"}}, self._policy()
        )
        self.assertFalse(block)

    def test_ignores_non_write_tools(self):
        block, _ = loop_policy.denied_write_verdict(
            {"tool_name": "Bash", "tool_input": {"command": "rm .agent/config.json"}}, self._policy()
        )
        self.assertFalse(block)


class TestCheckerSplit(unittest.TestCase):
    def test_split_requires_two_distinct_models(self):
        self.assertTrue(_policy("L2", maker_model="a", checker_model="b").checker_split_ok())
        self.assertFalse(_policy("L2", maker_model="a", checker_model="a").checker_split_ok())
        self.assertFalse(_policy("L2", maker_model="a").checker_split_ok())


class TestFromConfig(unittest.TestCase):
    def _root_with_loop(self, block):
        root = tempfile.mkdtemp()
        os.makedirs(os.path.join(root, ".agent"))
        with open(os.path.join(root, ".agent", "config.json"), "w", encoding="utf-8") as f:
            json.dump({"agent_name": "x", "loop": block}, f)
        return root

    def test_reads_loop_block(self):
        root = self._root_with_loop({"autonomy": "L2", "denylist": ["*.foo"]})
        p = LoopPolicy.from_config(root, env={})
        self.assertEqual(p.level, "L2")
        self.assertTrue(p.is_denied_path("a/b.foo"))

    def test_env_overrides_config(self):
        root = self._root_with_loop({"autonomy": "L1"})
        p = LoopPolicy.from_config(root, env={"SOLOMON_LOOP_AUTONOMY": "L3"})
        self.assertEqual(p.level, "L3")

    def test_default_is_human_when_no_block(self):
        root = tempfile.mkdtemp()
        p = LoopPolicy.from_config(root, env={})
        self.assertEqual(p.level, "human")
        self.assertFalse(p.decide_stage("release").allowed)


if __name__ == "__main__":
    unittest.main()
