import unittest

from solomon_harness import loop_log


class FakeDb:
    def __init__(self, rows):
        self._rows = rows

    def list_loop_runs(self, last):
        return list(self._rows[:last])


def _run(stage, target, status="failed"):
    return {"stage": stage, "target": target, "status": status}


class TestConsecutiveRunsForTarget(unittest.TestCase):
    def test_counts_a_head_streak(self):
        db = FakeDb([_run("review", "342"), _run("review", "342"), _run("start", "9")])
        self.assertEqual(loop_log.consecutive_runs_for_target(db, "342", "review"), 2)

    def test_an_intervening_different_run_breaks_the_streak(self):
        db = FakeDb([_run("review", "342"), _run("start", "9"), _run("review", "342")])
        self.assertEqual(loop_log.consecutive_runs_for_target(db, "342", "review"), 1)

    def test_streak_is_capped_at_the_limit(self):
        db = FakeDb([_run("review", "342") for _ in range(20)])
        self.assertEqual(loop_log.consecutive_runs_for_target(db, "342", "review", limit=6), 6)

    def test_remediation_limit_reached_true_at_the_cap(self):
        db = FakeDb([_run("review", "342") for _ in range(6)])
        self.assertTrue(loop_log.remediation_limit_reached(db, "342", "review", limit=6))

    def test_remediation_limit_not_reached_below_the_cap(self):
        db = FakeDb([_run("review", "342") for _ in range(5)])
        self.assertFalse(loop_log.remediation_limit_reached(db, "342", "review", limit=6))

    def test_db_failure_reads_as_zero(self):
        class Broken:
            def list_loop_runs(self, last):
                raise RuntimeError("down")

        self.assertEqual(loop_log.consecutive_runs_for_target(Broken(), "1", "review"), 0)


if __name__ == "__main__":
    unittest.main()
