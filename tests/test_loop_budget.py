"""Tests for the post-hoc cost budget (Phase 3)."""

import os
import tempfile
import unittest

from solomon_harness import loop_budget


class TestBudget(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp()

    def test_record_and_daily_spend(self):
        loop_budget.record(self.root, 0.12, stage="start", day="2026-06-28")
        loop_budget.record(self.root, 0.08, stage="review", day="2026-06-28")
        loop_budget.record(self.root, 1.00, stage="start", day="2026-06-29")
        self.assertAlmostEqual(loop_budget.daily_spend(self.root, "2026-06-28"), 0.20)
        self.assertAlmostEqual(loop_budget.daily_spend(self.root, "2026-06-29"), 1.00)

    def test_over_ceiling(self):
        loop_budget.record(self.root, 0.5, day="2026-06-28")
        self.assertFalse(loop_budget.over_ceiling(self.root, None, day="2026-06-28"))
        self.assertFalse(loop_budget.over_ceiling(self.root, 0, day="2026-06-28"))
        self.assertFalse(loop_budget.over_ceiling(self.root, 1.0, day="2026-06-28"))
        loop_budget.record(self.root, 0.6, day="2026-06-28")  # total 1.1 >= 1.0
        self.assertTrue(loop_budget.over_ceiling(self.root, 1.0, day="2026-06-28"))

    def test_ledger_anchored_in_dot_solomon_when_not_git(self):
        loop_budget.record(self.root, 0.1, day="d")
        self.assertEqual(
            loop_budget.ledger_path(self.root),
            os.path.join(self.root, ".solomon", "loop-budget.jsonl"),
        )

    def test_parse_engine_cost(self):
        self.assertEqual(loop_budget.parse_engine_cost('{"total_cost_usd": 0.34, "x": 1}'), 0.34)
        self.assertEqual(loop_budget.parse_engine_cost('{"cost_usd": 1.2}'), 1.2)
        self.assertIsNone(loop_budget.parse_engine_cost("not json"))
        self.assertIsNone(loop_budget.parse_engine_cost('{"no_cost": true}'))


if __name__ == "__main__":
    unittest.main()
