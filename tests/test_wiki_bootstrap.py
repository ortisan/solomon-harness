"""Unit tests for the wiki-bootstrap module (issue #117).

These cover the no-browser, no-network seam used by both the wiki step and the
init detect-and-hint (URL resolution and the ls-remote-based ref probe, with the
git call injected so the tests stay hermetic), plus the interactive degrade
ladder: the ``choose_tier`` routing decision and ``bootstrap_wiki`` orchestrated
over an injected fake ``BrowserBootstrapper`` port. The real claude-in-chrome
adapter is a host-integration seam proven manually at review; it is never driven
from these tests, which inject fakes and a fake ref-checker instead.
"""

import contextlib
import io
import subprocess
import unittest

from solomon_harness.bootstrap import hint_uninitialized_wiki
from solomon_harness.wiki_bootstrap import (
    Tier,
    bootstrap_wiki,
    choose_tier,
    resolve_web_wiki_url,
    resolve_wiki_clone_url,
    wiki_refs_present,
)

REMOTE = "https://github.com/o/r.git"
CLONE_URL = "https://github.com/o/r.wiki.git"
NEW_URL = "https://github.com/o/r/wiki/_new"


class _RefProbe:
    """A fake ``wiki_refs_present`` whose answer can flip after a page is saved.

    Records every probe so a test can assert the bootstrap re-verified by an
    independent ls-remote rather than by trusting the port's return value.
    """

    def __init__(self, value):
        self.value = value
        self.calls = []

    def __call__(self, url, timeout=10.0):
        self.calls.append((url, timeout))
        return self.value


class _FakeBootstrapper:
    """A fake browser port. ``on_create`` simulates the side effect of the save
    (e.g. a ref appearing) so the test controls the observable outcome, never the
    port's return value."""

    def __init__(self, *, authenticated=True, on_create=None):
        self._authenticated = authenticated
        self._on_create = on_create
        self.create_calls = []

    def is_authenticated(self):
        return self._authenticated

    def create_first_page(self, web_new_url):
        self.create_calls.append(web_new_url)
        if self._on_create is not None:
            self._on_create()


def _never_confirm():
    raise AssertionError("confirm() must not be called")


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


class TestChooseTier(unittest.TestCase):
    """The pure routing decision for the degrade ladder (full truth table).

    Precedence: an initialized wiki is always a NO-OP; a non-interactive run is
    always the DEGRADE floor (no browser is ever driven without an operator);
    interactive runs AUTOMATE only with a usable, authenticated browser and a
    confirmed-uninitialized (0 refs) wiki, otherwise GUIDE.
    """

    def test_refs_present_is_always_noop(self):
        # Refs already exist -> idempotent no-op regardless of the other inputs.
        for interactive in (True, False):
            for browser in (True, False):
                for auth in (True, False):
                    self.assertIs(
                        choose_tier(
                            interactive=interactive,
                            browser_available=browser,
                            authenticated=auth,
                            refs_present=True,
                        ),
                        Tier.NOOP,
                        (interactive, browser, auth),
                    )

    def test_non_interactive_always_degrades(self):
        # The headless/CI floor: never drive a browser without an operator, even
        # if a bootstrapper happens to be injected.
        for browser in (True, False):
            for auth in (True, False):
                for refs in (False, None):
                    self.assertIs(
                        choose_tier(
                            interactive=False,
                            browser_available=browser,
                            authenticated=auth,
                            refs_present=refs,
                        ),
                        Tier.DEGRADE,
                        (browser, auth, refs),
                    )

    def test_interactive_without_browser_guides(self):
        self.assertIs(
            choose_tier(
                interactive=True,
                browser_available=False,
                authenticated=False,
                refs_present=False,
            ),
            Tier.GUIDE,
        )

    def test_interactive_with_unauthenticated_browser_guides(self):
        self.assertIs(
            choose_tier(
                interactive=True,
                browser_available=True,
                authenticated=False,
                refs_present=False,
            ),
            Tier.GUIDE,
        )

    def test_interactive_usable_browser_and_zero_refs_automates(self):
        self.assertIs(
            choose_tier(
                interactive=True,
                browser_available=True,
                authenticated=True,
                refs_present=False,
            ),
            Tier.AUTOMATE,
        )

    def test_inconclusive_detection_does_not_automate(self):
        # Detection could not confirm 0 refs; do not auto-create a page that might
        # duplicate an existing wiki -- route an interactive run to GUIDE instead.
        self.assertIs(
            choose_tier(
                interactive=True,
                browser_available=True,
                authenticated=True,
                refs_present=None,
            ),
            Tier.GUIDE,
        )


class TestBootstrapWiki(unittest.TestCase):
    """Orchestration over the injected port. Success is asserted by a re-probe of
    the refs (ls-remote), never by trusting the port's return."""

    def test_noop_when_refs_present_does_not_touch_the_port(self):
        probe = _RefProbe(True)
        bootstrapper = _FakeBootstrapper()
        result = bootstrap_wiki(
            REMOTE,
            interactive=True,
            bootstrapper=bootstrapper,
            refs_checker=probe,
            confirm=_never_confirm,
            notify=lambda _m: None,
        )
        self.assertIs(result.tier, Tier.NOOP)
        self.assertTrue(result.proceed)
        self.assertEqual(result.exit_code, 0)
        self.assertEqual(bootstrapper.create_calls, [], "no first page must be created")
        self.assertEqual(len(probe.calls), 1, "no-op must not re-probe")

    def test_automate_success_is_verified_by_a_reprobe_not_the_port(self):
        probe = _RefProbe(False)
        # The save's observable effect: a ref appears. The port itself reports
        # nothing back; success comes only from the re-probe.
        bootstrapper = _FakeBootstrapper(on_create=lambda: setattr(probe, "value", True))
        result = bootstrap_wiki(
            REMOTE,
            interactive=True,
            bootstrapper=bootstrapper,
            refs_checker=probe,
            confirm=_never_confirm,
            notify=lambda _m: None,
        )
        self.assertIs(result.tier, Tier.AUTOMATE)
        self.assertTrue(result.proceed)
        self.assertEqual(result.exit_code, 0)
        self.assertEqual(bootstrapper.create_calls, [NEW_URL])
        self.assertEqual(len(probe.calls), 2, "automate must re-probe to verify")

    def test_automate_failure_degrades_when_no_ref_appears(self):
        probe = _RefProbe(False)
        # The port "ran" (create_first_page is called) but no ref appears, so the
        # re-probe still sees 0 refs -> the run must degrade, not falsely succeed.
        bootstrapper = _FakeBootstrapper(on_create=None)
        result = bootstrap_wiki(
            REMOTE,
            interactive=True,
            bootstrapper=bootstrapper,
            refs_checker=probe,
            confirm=_never_confirm,
            notify=lambda _m: None,
        )
        self.assertIs(result.tier, Tier.AUTOMATE)
        self.assertFalse(result.proceed)
        self.assertEqual(result.exit_code, 4)
        self.assertEqual(bootstrapper.create_calls, [NEW_URL])
        self.assertIn("/wiki/_new", result.message)
        self.assertNotIn("Repository not found", result.message)

    def test_guide_success_after_operator_confirms(self):
        probe = _RefProbe(False)
        notes = []

        def _confirm_and_save():
            probe.value = True  # the operator saved the page during the prompt
            return True

        result = bootstrap_wiki(
            REMOTE,
            interactive=True,
            bootstrapper=None,
            refs_checker=probe,
            confirm=_confirm_and_save,
            notify=notes.append,
        )
        self.assertIs(result.tier, Tier.GUIDE)
        self.assertTrue(result.proceed)
        self.assertEqual(result.exit_code, 0)
        self.assertTrue(any("/wiki/_new" in n for n in notes), "guide must print the manual step")
        self.assertEqual(len(probe.calls), 2, "guide must re-probe after confirm")

    def test_guide_still_zero_refs_degrades_with_the_same_message(self):
        probe = _RefProbe(False)
        result = bootstrap_wiki(
            REMOTE,
            interactive=True,
            bootstrapper=None,
            refs_checker=probe,
            confirm=lambda: True,  # operator confirms but nothing was actually saved
            notify=lambda _m: None,
        )
        self.assertIs(result.tier, Tier.GUIDE)
        self.assertFalse(result.proceed)
        self.assertEqual(result.exit_code, 4)
        self.assertIn("/wiki/_new", result.message)
        self.assertNotIn("Repository not found", result.message)

    def test_degrade_headless_attempts_no_browser_and_does_not_prompt(self):
        probe = _RefProbe(False)
        result = bootstrap_wiki(
            REMOTE,
            interactive=False,
            bootstrapper=None,
            refs_checker=probe,
            confirm=_never_confirm,  # must not prompt or block on input
            notify=lambda _m: None,
        )
        self.assertIs(result.tier, Tier.DEGRADE)
        self.assertFalse(result.proceed)
        self.assertEqual(result.exit_code, 4)
        self.assertIn("/wiki/_new", result.message)
        self.assertIn("not been initialized", result.message)
        self.assertNotIn("Repository not found", result.message)

    def test_inconclusive_detection_headless_degrades_with_inconclusive_message(self):
        probe = _RefProbe(None)
        result = bootstrap_wiki(
            REMOTE,
            interactive=False,
            bootstrapper=None,
            refs_checker=probe,
            confirm=_never_confirm,
            notify=lambda _m: None,
        )
        self.assertIs(result.tier, Tier.DEGRADE)
        self.assertFalse(result.proceed)
        self.assertEqual(result.exit_code, 4)
        self.assertIn("inconclusive", result.message.lower())
        self.assertIn("/wiki/_new", result.message)

    def test_proceeds_without_a_github_remote_and_never_probes(self):
        probe = _RefProbe(False)
        result = bootstrap_wiki(
            "none",
            interactive=False,
            bootstrapper=None,
            refs_checker=probe,
            confirm=_never_confirm,
            notify=lambda _m: None,
        )
        self.assertTrue(result.proceed)
        self.assertEqual(result.exit_code, 0)
        self.assertEqual(probe.calls, [], "no remote must not trigger a network probe")


if __name__ == "__main__":
    unittest.main()
