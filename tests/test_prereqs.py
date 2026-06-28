import io
import unittest
from unittest.mock import patch

from solomon_harness import prereqs


class TestPrereqs(unittest.TestCase):
    def test_python_ok_for_current_interpreter(self):
        # The suite runs on 3.10+, so this is always true here.
        self.assertTrue(prereqs.python_ok())

    def test_command_exists_uses_which(self):
        with patch("shutil.which", return_value="/usr/bin/git"):
            self.assertTrue(prereqs.command_exists("git"))
        with patch("shutil.which", return_value=None):
            self.assertFalse(prereqs.command_exists("nope"))

    def test_report_all_present_returns_true(self):
        out = io.StringIO()
        with patch.object(prereqs, "command_exists", return_value=True):
            ok = prereqs.check_prerequisites(auto_install=False, out=out)
        self.assertTrue(ok)
        self.assertIn("All required prerequisites are present", out.getvalue())

    def test_missing_required_returns_false_without_installing(self):
        out = io.StringIO()
        # git missing -> required; --no-install must not attempt an install.
        def exists(cmd):
            return cmd != "git"

        with (
            patch.object(prereqs, "command_exists", side_effect=exists),
            patch.object(prereqs, "install_uv") as mock_install,
        ):
            ok = prereqs.check_prerequisites(auto_install=False, out=out)
        self.assertFalse(ok)
        mock_install.assert_not_called()
        self.assertIn("git (required)", out.getvalue())

    def test_uv_autoinstalled_when_missing(self):
        out = io.StringIO()

        def exists(cmd):
            return cmd != "uv"

        with (
            patch.object(prereqs, "command_exists", side_effect=exists),
            patch.object(prereqs, "install_uv", return_value=True) as mock_install,
        ):
            prereqs.check_prerequisites(auto_install=True, out=out)
        mock_install.assert_called_once()
        self.assertIn("uv (installed)", out.getvalue())


if __name__ == "__main__":
    unittest.main()
