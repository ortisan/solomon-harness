import unittest

from solomon_harness import review_dedup


class TestFindingDedupKey(unittest.TestCase):
    def test_same_location_and_category_key_equal(self):
        a = review_dedup.finding_dedup_key("solomon_harness/x.py", 42, "correctness")
        b = review_dedup.finding_dedup_key("solomon_harness/x.py", 42, "Correctness")
        self.assertEqual(a, b)

    def test_small_line_drift_keys_equal(self):
        a = review_dedup.finding_dedup_key("x.py", 40, "perf")
        b = review_dedup.finding_dedup_key("x.py", 43, "perf")
        self.assertEqual(a, b)

    def test_different_file_keys_differ(self):
        a = review_dedup.finding_dedup_key("a.py", 10, "perf")
        b = review_dedup.finding_dedup_key("b.py", 10, "perf")
        self.assertNotEqual(a, b)

    def test_different_category_keys_differ(self):
        a = review_dedup.finding_dedup_key("a.py", 10, "perf")
        b = review_dedup.finding_dedup_key("a.py", 10, "security")
        self.assertNotEqual(a, b)


class TestSuppressionAndNewFindings(unittest.TestCase):
    def test_invalid_and_resolved_are_suppressed(self):
        self.assertTrue(review_dedup.is_suppressed("invalid"))
        self.assertTrue(review_dedup.is_suppressed("resolved"))
        self.assertFalse(review_dedup.is_suppressed("pending"))
        self.assertFalse(review_dedup.is_suppressed("valid"))
        self.assertFalse(review_dedup.is_suppressed(None))

    def test_new_findings_excludes_suppressed_priors(self):
        prior = {
            "k1": {"lifecycle": "invalid"},
            "k2": {"lifecycle": "resolved"},
            "k3": {"lifecycle": "valid"},
        }
        fresh = review_dedup.new_findings(["k1", "k2", "k3", "k4"], prior)
        self.assertEqual(sorted(fresh), ["k3", "k4"])

    def test_lifecycle_states_are_the_documented_set(self):
        self.assertEqual(
            review_dedup.LIFECYCLE_STATES, ("pending", "valid", "invalid", "resolved")
        )


if __name__ == "__main__":
    unittest.main()
