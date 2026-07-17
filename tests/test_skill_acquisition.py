"""Guards for the single skill-acquisition chokepoint (#108).

Both the broker and the `solomon-harness skills add` CLI must fetch through one
pinned-clone + scan/quarantine/confine + install path. These tests exercise that
path from the acquisition module and the CLI, proving the legacy CLI is no longer
an unpinned, unscanned back door into agents/<name>/skills/.
"""

import json
import os
import subprocess
import tempfile
import unittest

from solomon_harness import skill_acquisition


def _git(cwd, *args):
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    subprocess.run(["git", "-C", cwd, *args], check=True, capture_output=True, text=True, env=env)


def _make_source(root, build):
    """Create a git source repo, let ``build(src)`` populate it, commit, and
    return ``(url, pin)`` where url is a file:// URL and pin is the HEAD SHA."""
    src = os.path.join(root, "src_repo")
    os.makedirs(src)
    _git(src, "init", "-q", "-b", "main")
    _git(src, "config", "user.email", "s@example.com")
    _git(src, "config", "user.name", "Src")
    build(src)
    _git(src, "add", "-A")
    _git(src, "commit", "-q", "-m", "skill")
    rev = subprocess.run(
        ["git", "-C", src, "rev-parse", "HEAD"], check=True, capture_output=True, text=True
    ).stdout.strip()
    return f"file://{src}", rev


class TestAcquireSkillChokepoint(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = self.tmp.name
        os.makedirs(os.path.join(self.root, "agents", "qa", "skills"))
        self.skills_dir = os.path.join(self.root, "agents", "qa", "skills")

    def tearDown(self):
        self.tmp.cleanup()

    def _standalone(self, body):
        def build(src):
            os.makedirs(os.path.join(src, "skills"))
            with open(os.path.join(src, "skills", "demo.md"), "w", encoding="utf-8") as f:
                f.write(body)
        return build

    def test_rejects_unpinned_source(self):
        url, _ = _make_source(self.root, self._standalone("# Demo\n\nbody"))
        with self.assertRaisesRegex(ValueError, "SHA-pin mandatory"):
            skill_acquisition.acquire_skill(
                self.root, {"url": url}, "demo", self.skills_dir
            )

    def test_installs_pinned_valid_skill_and_adapts_content(self):
        url, pin = _make_source(
            self.root, self._standalone("# Demo\n\nplease leverage this 😊")
        )
        target = skill_acquisition.acquire_skill(
            self.root, {"url": url, "pin": pin}, "demo", self.skills_dir
        )
        self.assertTrue(os.path.isfile(target))
        with open(target, encoding="utf-8") as f:
            content = f.read()
        self.assertNotIn("leverage", content)  # cliche adapted
        self.assertNotIn("😊", content)  # emoji stripped

    def test_quarantines_script_bearing_packaged_skill(self):
        def build(src):
            pkg = os.path.join(src, "packaged")
            os.makedirs(os.path.join(pkg, "scripts"))
            with open(os.path.join(pkg, "SKILL.md"), "w", encoding="utf-8") as f:
                f.write("# Packaged")
            evil = os.path.join(pkg, "scripts", "run.sh")
            with open(evil, "w", encoding="utf-8") as f:
                f.write("#!/bin/sh\necho pwned\n")
        url, pin = _make_source(self.root, build)
        with self.assertRaisesRegex(ValueError, "scripts/executables"):
            skill_acquisition.acquire_skill(
                self.root, {"url": url, "pin": pin}, "packaged", self.skills_dir
            )
        self.assertTrue(os.path.isdir(os.path.join(self.root, ".solomon", "quarantine")))
        # The malicious skill was never installed into the agents tree.
        self.assertFalse(os.path.exists(os.path.join(self.skills_dir, "packaged")))

    def test_rejects_symlink_bearing_packaged_skill(self):
        def build(src):
            pkg = os.path.join(src, "packaged")
            os.makedirs(pkg)
            with open(os.path.join(pkg, "SKILL.md"), "w", encoding="utf-8") as f:
                f.write("# Packaged")
            os.symlink("/etc/passwd", os.path.join(pkg, "link.md"))
        url, pin = _make_source(self.root, build)
        with self.assertRaisesRegex(ValueError, "[Ss]ymlink"):
            skill_acquisition.acquire_skill(
                self.root, {"url": url, "pin": pin}, "packaged", self.skills_dir
            )

    def test_rejects_oversized_standalone_skill(self):
        big = "# Demo\n\n" + ("x" * (256 * 1024 + 10))
        url, pin = _make_source(self.root, self._standalone(big))
        with self.assertRaisesRegex(ValueError, "size exceeds"):
            skill_acquisition.acquire_skill(
                self.root, {"url": url, "pin": pin}, "demo", self.skills_dir
            )


class TestSkillsAddCliIsPinned(unittest.TestCase):
    """The legacy `solomon-harness skills add` CLI now goes through the chokepoint."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = self.tmp.name
        os.makedirs(os.path.join(self.root, "agents", "qa", "skills"))

    def tearDown(self):
        self.tmp.cleanup()

    def _write_sources(self, source):
        with open(os.path.join(self.root, "skill-sources.json"), "w", encoding="utf-8") as f:
            json.dump({"sources": [source]}, f)

    def test_cmd_add_rejects_unpinned_source(self):
        from solomon_harness import skills

        def build(src):
            os.makedirs(os.path.join(src, "skills"))
            with open(os.path.join(src, "skills", "demo.md"), "w", encoding="utf-8") as f:
                f.write("# Demo\n\nbody")

        url, _ = _make_source(self.root, build)
        self._write_sources({"name": "unpinned", "type": "git", "url": url})
        rc = skills.cmd_add(self.root, "unpinned", "demo", "qa")
        self.assertEqual(rc, 1)  # unpinned source rejected, nothing installed
        self.assertFalse(
            os.path.exists(os.path.join(self.root, "agents", "qa", "skills", "demo.md"))
        )

    def test_cmd_add_installs_a_pinned_source(self):
        from solomon_harness import skills

        def build(src):
            os.makedirs(os.path.join(src, "skills"))
            with open(os.path.join(src, "skills", "demo.md"), "w", encoding="utf-8") as f:
                f.write("# Demo\n\nbody")

        url, pin = _make_source(self.root, build)
        self._write_sources({"name": "pinned", "type": "git", "url": url, "pin": pin})
        rc = skills.cmd_add(self.root, "pinned", "demo", "qa")
        self.assertEqual(rc, 0)
        self.assertTrue(
            os.path.isfile(os.path.join(self.root, "agents", "qa", "skills", "demo.md"))
        )


if __name__ == "__main__":
    unittest.main()
