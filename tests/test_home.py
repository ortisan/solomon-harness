import os
import socket
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from solomon_harness import home


class TestHarnessHome(unittest.TestCase):
    def test_default_home(self):
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("SOLOMON_HARNESS_HOME", None)
            self.assertEqual(home.harness_home(), os.path.abspath(os.path.expanduser("~/.solomon-harness")))

    def test_env_override(self):
        with patch.dict(os.environ, {"SOLOMON_HARNESS_HOME": "/tmp/sh-test"}):
            self.assertEqual(home.harness_home(), os.path.abspath("/tmp/sh-test"))


class TestSlugFromRemote(unittest.TestCase):
    def test_scp_form(self):
        self.assertEqual(
            home.slug_from_remote("git@github.com:ortisan/solomon-harness.git"),
            "ortisan-solomon-harness",
        )

    def test_https_form(self):
        self.assertEqual(
            home.slug_from_remote("https://github.com/ortisan/solomon-harness.git"),
            "ortisan-solomon-harness",
        )

    def test_https_without_git_suffix(self):
        self.assertEqual(
            home.slug_from_remote("https://gitlab.com/team/sub/proj"),
            "sub-proj",
        )

    def test_sanitizes_uppercase_and_symbols(self):
        self.assertEqual(
            home.slug_from_remote("git@github.com:Acme/My.Cool_Repo.git"),
            "acme-my-cool_repo",
        )


class TestDeriveTenant(unittest.TestCase):
    def test_uses_remote_slug_when_present(self):
        with patch.object(home, "_git_remote", return_value="git@github.com:ortisan/solomon-harness.git"):
            self.assertEqual(home.derive_tenant("/any/path"), "ortisan-solomon-harness")

    def test_fallback_is_dirname_plus_hash(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch.object(home, "_git_remote", return_value=None):
                tenant = home.derive_tenant(tmp)
        base = os.path.basename(os.path.abspath(tmp)).lower()
        self.assertTrue(tenant.startswith(home._sanitize_tenant(base)))
        # The hash suffix makes it unique and SurrealDB-safe.
        self.assertRegex(tenant, r"-[0-9a-f]{6}$")

    def test_fallback_distinguishes_same_named_dirs(self):
        with tempfile.TemporaryDirectory() as a, tempfile.TemporaryDirectory() as b:
            da, db = os.path.join(a, "proj"), os.path.join(b, "proj")
            os.makedirs(da)
            os.makedirs(db)
            with patch.object(home, "_git_remote", return_value=None):
                ta = home.derive_tenant(da)
                tb = home.derive_tenant(db)
        self.assertNotEqual(ta, tb)

    def test_real_git_repo_resolves_remote(self):
        # Clear GIT_* so the temp repo is not redirected to an enclosing repo or
        # worktree (the suite itself may run inside one).
        env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
        with tempfile.TemporaryDirectory() as tmp:
            subprocess.run(["git", "init"], cwd=tmp, capture_output=True, env=env)
            subprocess.run(
                ["git", "remote", "add", "origin", "git@github.com:acme/widget.git"],
                cwd=tmp, capture_output=True, env=env,
            )
            self.assertEqual(home.derive_tenant(tmp), "acme-widget")


class TestPortAssignment(unittest.TestCase):
    def test_find_free_port_returns_preferred_when_free(self):
        # A high, almost-certainly-free port should be returned as-is.
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.bind(("127.0.0.1", 0))
        free = s.getsockname()[1]
        s.close()
        self.assertEqual(home.find_free_port(free), free)

    def test_find_free_port_skips_a_taken_port(self):
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.bind(("127.0.0.1", 0))
        s.listen(1)
        taken = s.getsockname()[1]
        try:
            chosen = home.find_free_port(taken)
            self.assertNotEqual(chosen, taken)
            self.assertGreater(chosen, taken)
        finally:
            s.close()

    def test_assigned_port_is_persisted_and_reused(self):
        with tempfile.TemporaryDirectory() as h:
            first = home.assigned_memory_port(h)
            self.assertTrue(os.path.isfile(os.path.join(h, home.MEMORY_CONFIG)))
            # A later call reuses the recorded port, ignoring a different preference.
            again = home.assigned_memory_port(h, preferred=first + 500)
            self.assertEqual(first, again)

    def test_assigns_free_port_when_preferred_is_taken(self):
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.bind(("127.0.0.1", 0))
        s.listen(1)
        taken = s.getsockname()[1]
        try:
            with tempfile.TemporaryDirectory() as h:
                port = home.assigned_memory_port(h, preferred=taken)
            self.assertNotEqual(port, taken)
        finally:
            s.close()


if __name__ == "__main__":
    unittest.main()
