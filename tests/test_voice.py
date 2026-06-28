import unittest

from solomon_harness import voice


class TestVoice(unittest.TestCase):
    def test_icon_is_the_sage(self):
        self.assertEqual(voice.ICON, "\U0001f9d9")

    def test_say_prefixes_icon_and_name(self):
        out = voice.say("project status")
        self.assertTrue(out.startswith(voice.ICON))
        self.assertIn("Solomon:", out)
        self.assertTrue(out.endswith("project status"))

    def test_prefix_composition(self):
        self.assertEqual(voice.PREFIX, f"{voice.ICON} Solomon:")


if __name__ == "__main__":
    unittest.main()
