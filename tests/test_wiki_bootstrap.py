"""Unit tests for the shared wiki-bootstrap detection primitives (issue #117).

These cover the no-browser, no-network seam used by both the wiki step and the
init detect-and-hint: URL resolution and the ls-remote-based ref probe (with the
git call injected so the tests stay hermetic). The browser-automation tier
(choose_tier / bootstrap_wiki) is deferred and not exercised here.
"""

import contextlib
import io
import subprocess
import unittest

from solomon_harness.bootstrap import hint_uninitialized_wiki
from solomon_harness.wiki_bootstrap import (
    resolve_web_wiki_url,
    resolve_wiki_clone_url,
    wiki_refs_present,
)


class _FakeCompleted:
    def __init__(self, returncode, stdout):
        self.returncode = returncode
        self.stdout = stdout


def _runner_returning(returncode, stdout):
    def _run(cmd, **kwargs):
        return _FakeCompleted(returncode, stdout)

    return _run


def _runner_raising(exc):
    def _run(cmd, **kwargs):
        raise exc

    return _run


class TestResolveWikiCloneUrl(unittest.TestCase):
    def test_maps_repo_remotes_to_wiki_git(self):
        cases = {
            "https://github.com/o/r.git": "https://github.com/o/r.wiki.git",
            "https://github.com/o/r": "https://github.com/o/r.wiki.git",
            "https://github.com/o/r/": "https://github.com/o/r.wiki.git",
            "git@github.com:o/r.git": "git@github.com:o/r.wiki.git",
            "https://github.com/o/r.wiki.git": "https://github.com/o/r.wiki.git",
        }
        for remote, expected in cases.items():
            self.assertEqual(resolve_wiki_clone_url(remote), expected, remote)

    def test_returns_none_without_a_usable_remote(self):
        self.assertIsNone(resolve_wiki_clone_url("none"))
        self.assertIsNone(resolve_wiki_clone_url(""))


class TestResolveWebWikiUrl(unittest.TestCase):
    def test_maps_remotes_to_the_first_page_editor_url(self):
        cases = {
            "https://github.com/o/r.git": "https://github.com/o/r/wiki/_new",
            "https://github.com/o/r": "https://github.com/o/r/wiki/_new",
            "git@github.com:o/r.git": "https://github.com/o/r/wiki/_new",
            "ssh://git@github.com/o/r.git": "https://github.com/o/r/wiki/_new",
            "https://github.com/o/r.wiki.git": "https://github.com/o/r/wiki/_new",
        }
        for remote, expected in cases.items():
            self.assertEqual(resolve_web_wiki_url(remote), expected, remote)

    def test_returns_none_without_a_usable_remote(self):
        self.assertIsNone(resolve_web_wiki_url("none"))
        self.assertIsNone(resolve_web_wiki_url(""))


class TestWikiRefsPresent(unittest.TestCase):
    def test_true_when_a_head_is_advertised(self):
        runner = _runner_returning(0, "deadbeef\trefs/heads/master\n")
        self.assertIs(wiki_refs_present("u", runner=runner), True)

    def test_false_on_zero_refs(self):
        self.assertIs(wiki_refs_present("u", runner=_runner_returning(0, "")), False)

    def test_false_when_remote_not_found(self):
        # git ls-remote exits non-zero for a missing repository.
        self.assertIs(wiki_refs_present("u", runner=_runner_returning(128, "")), False)

    def test_none_on_timeout(self):
        runner = _runner_raising(subprocess.TimeoutExpired(["git"], 10))
        self.assertIsNone(wiki_refs_present("u", runner=runner))

    def test_none_when_git_unavailable(self):
        self.assertIsNone(wiki_refs_present("u", runner=_runner_raising(FileNotFoundError())))


class TestInitDetectAndHint(unittest.TestCase):
    """Regression: init detects an uninitialized wiki and only hints; it never
    bootstraps (it opens no browser and creates no page)."""

    def _hint(self, **kwargs):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            result = hint_uninitialized_wiki("/ws", "https://github.com/o/r.git", **kwargs)
        return result, buf.getvalue()

    def test_hints_with_the_new_url_when_enabled_and_zero_refs(self):
        result, out = self._hint(
            wiki_enabled_checker=lambda _ws: True,
            refs_checker=lambda url, timeout=10.0: False,
        )
        self.assertIsNone(result)
        self.assertIn("https://github.com/o/r/wiki/_new", out)
        self.assertIn("not been initialized", out)

    def test_hints_when_detection_is_inconclusive(self):
        _result, out = self._hint(
            wiki_enabled_checker=lambda _ws: True,
            refs_checker=lambda url, timeout=10.0: None,
        )
        self.assertIn("/wiki/_new", out)

    def test_silent_when_refs_present(self):
        _result, out = self._hint(
            wiki_enabled_checker=lambda _ws: True,
            refs_checker=lambda url, timeout=10.0: True,
        )
        self.assertEqual(out, "")

    def test_skips_network_probe_when_wiki_feature_not_confirmed(self):
        calls = []

        def _refs(url, timeout=10.0):
            calls.append(url)
            return False

        _result, out = self._hint(wiki_enabled_checker=lambda _ws: None, refs_checker=_refs)
        self.assertEqual(out, "")
        self.assertEqual(calls, [], "init probed the network when the feature was unconfirmed")

    def test_silent_without_a_github_remote(self):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            hint_uninitialized_wiki(
                "/ws",
                "none",
                wiki_enabled_checker=lambda _ws: True,
                refs_checker=lambda url, timeout=10.0: False,
            )
        self.assertEqual(buf.getvalue(), "")


if __name__ == "__main__":
    unittest.main()
