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
import os
import subprocess
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from solomon_harness import cli
from solomon_harness.bootstrap import bootstrap_project, hint_uninitialized_wiki
from solomon_harness.bootstrap import hint_uninitialized_wiki as _real_hint
from solomon_harness.wiki_bootstrap import (
    Tier,
    WikiBootstrapResult,
    _confirm_via_input,
    bootstrap_wiki,
    choose_tier,
    is_github_remote,
    remote_host,
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
            # A bare .wiki suffix must be stripped symmetrically with
            # resolve_wiki_clone_url, so it does not yield .../r.wiki/wiki/_new.
            "https://github.com/o/r.wiki": "https://github.com/o/r/wiki/_new",
            "git@github.com:o/r.wiki": "https://github.com/o/r/wiki/_new",
        }
        for remote, expected in cases.items():
            self.assertEqual(resolve_web_wiki_url(remote), expected, remote)

    def test_returns_none_without_a_usable_remote(self):
        self.assertIsNone(resolve_web_wiki_url("none"))
        self.assertIsNone(resolve_web_wiki_url(""))


class TestGitHubHostAllowlist(unittest.TestCase):
    """Security (R-?): "is this GitHub?" is decided by the parsed host equalling an
    allowlisted host, never by a substring. A substring check let crafted remotes
    like git@github.com.evil.com:o/r.git pass and yield a github.com.evil.com web
    URL handed to the authenticated browser on AUTOMATE.
    """

    def test_parses_the_host_from_each_remote_shape(self):
        cases = {
            "https://github.com/o/r.git": "github.com",
            "https://github.com/o/r": "github.com",
            "git@github.com:o/r.git": "github.com",
            "ssh://git@github.com/o/r.git": "github.com",
            "https://x-access-token:SECRET@github.com/o/r.git": "github.com",
            "git@github.com.evil.com:o/r.git": "github.com.evil.com",
            "https://github.com.evil.com/o/r/wiki": "github.com.evil.com",
        }
        for remote, host in cases.items():
            self.assertEqual(remote_host(remote), host, remote)

    def test_legit_github_remotes_are_recognized(self):
        for remote in (
            "https://github.com/o/r.git",
            "https://github.com/o/r",
            "git@github.com:o/r.git",
            "ssh://git@github.com/o/r.git",
            "https://x-access-token:SECRET@github.com/o/r.git",
        ):
            self.assertTrue(is_github_remote(remote), remote)

    def test_bypass_vectors_are_not_github(self):
        # The crafted hosts the substring check accepted; the allowlist rejects
        # them because the parsed host does not equal "github.com".
        for remote in (
            "git@github.com.evil.com:o/r.git",
            "https://github.com.evil.com/o/r.git",
            "https://evilgithub.com/o/r.git",
            "git@evilgithub.com:o/r.git",
            "https://notgithub.com.attacker.net/o/r.git",
            "ssh://git@github.com.evil.com/o/r.git",
        ):
            self.assertFalse(is_github_remote(remote), remote)

    def test_no_usable_remote_is_not_github(self):
        self.assertFalse(is_github_remote("none"))
        self.assertFalse(is_github_remote(""))
        self.assertIsNone(remote_host("none"))


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

    def test_silent_and_no_probe_on_a_spoofed_github_host(self):
        # A remote whose host only looks like GitHub must not be probed or hinted.
        calls = []

        def _refs(url, timeout=10.0):
            calls.append(url)
            return False

        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            hint_uninitialized_wiki(
                "/ws",
                "git@github.com.evil.com:o/r.git",
                wiki_enabled_checker=lambda _ws: True,
                refs_checker=_refs,
            )
        self.assertEqual(buf.getvalue(), "")
        self.assertEqual(calls, [], "a spoofed host must not be probed")


class TestInitWiresTheWikiHint(unittest.TestCase):
    """Regression: bootstrap_project (the init flow) must actually invoke the
    detect-and-hint. The hint helper has its own unit tests, but nothing proved
    init calls it, so the ADR-0012 "detect-and-hint at init" never ran end to end.

    These exercise only the init->hint seam: the cheap pre-hint collaborators are
    stubbed and execution is stopped right after the hint via a sentinel, so the
    heavy remainder of bootstrap_project is not run.
    """

    class _StopAfterHint(Exception):
        pass

    def _run_until_hint(self, hint_side_effect):
        with (
            patch.dict(os.environ, {"SOLOMON_SKIP_GH_CHECK": "true"}),
            patch("solomon_harness.bootstrap._install_harness_files"),
            patch("solomon_harness.prereqs.check_prerequisites"),
            patch(
                "solomon_harness.bootstrap.get_project_metadata",
                return_value=("proj", REMOTE, "Python"),
            ),
            patch(
                "solomon_harness.bootstrap.hint_uninitialized_wiki",
                side_effect=hint_side_effect,
            ) as hint,
        ):
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                with self.assertRaises(self._StopAfterHint):
                    bootstrap_project("/ws")
            return hint, buf.getvalue()

    def test_bootstrap_project_invokes_the_hint_with_the_remote(self):
        hint, _out = self._run_until_hint(self._StopAfterHint)
        hint.assert_called_once_with("/ws", REMOTE)

    def test_init_stays_silent_when_the_wiki_already_has_refs(self):
        # Drive the real hint (feature enabled, refs present) through the wiring to
        # prove the init path prints nothing once the wiki is initialized.
        def _hint_then_stop(ws, remote):
            _real_hint(
                ws,
                remote,
                wiki_enabled_checker=lambda _ws: True,
                refs_checker=lambda url, timeout=10.0: True,
            )
            raise self._StopAfterHint

        _hint, out = self._run_until_hint(_hint_then_stop)
        self.assertNotIn("/wiki/_new", out)


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

    def test_unauthenticated_browser_guides_and_never_creates_a_page(self):
        # R-2 control: a browser is present but not authenticated, so the harness
        # must not assume an identity -- it GUIDEs the operator and never drives
        # the port. choose_tier's is_authenticated wiring is covered above; this
        # pins the orchestration end of that control.
        probe = _RefProbe(False)
        bootstrapper = _FakeBootstrapper(authenticated=False)
        result = bootstrap_wiki(
            REMOTE,
            interactive=True,
            bootstrapper=bootstrapper,
            refs_checker=probe,
            confirm=lambda: True,  # even if the operator confirms, no page is driven
            notify=lambda _m: None,
        )
        self.assertIs(result.tier, Tier.GUIDE)
        self.assertEqual(bootstrapper.create_calls, [], "an unauthenticated browser must not create a page")

    def test_guide_declined_degrades_without_a_reprobe(self):
        # When the operator declines the guide, the step degrades immediately and
        # does not re-probe the refs (only the initial detection probe runs).
        probe = _RefProbe(False)
        result = bootstrap_wiki(
            REMOTE,
            interactive=True,
            bootstrapper=None,
            refs_checker=probe,
            confirm=lambda: False,
            notify=lambda _m: None,
        )
        self.assertIs(result.tier, Tier.GUIDE)
        self.assertFalse(result.proceed)
        self.assertEqual(result.exit_code, 4)
        self.assertEqual(len(probe.calls), 1, "a declined guide must not re-probe")

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

    def test_spoofed_github_host_is_a_noop_and_never_automates(self):
        # A crafted remote whose host only looks like GitHub must be treated as
        # non-GitHub: no probe, no web URL handed to the browser, no AUTOMATE.
        probe = _RefProbe(False)
        bootstrapper = _FakeBootstrapper(authenticated=True)
        for remote in (
            "git@github.com.evil.com:o/r.git",
            "https://github.com.evil.com/o/r.git",
            "https://evilgithub.com/o/r.git",
            "https://notgithub.com.attacker.net/o/r.git",
        ):
            result = bootstrap_wiki(
                remote,
                interactive=True,
                bootstrapper=bootstrapper,
                refs_checker=probe,
                confirm=_never_confirm,
                notify=lambda _m: None,
            )
            self.assertIs(result.tier, Tier.NOOP, remote)
            self.assertTrue(result.proceed, remote)
            self.assertEqual(result.exit_code, 0, remote)
            self.assertEqual(result.message, "", remote)
        self.assertEqual(bootstrapper.create_calls, [], "no first page on a spoofed host")
        self.assertEqual(probe.calls, [], "a spoofed host must not trigger a network probe")

    def test_degrade_message_redacts_url_credentials(self):
        # A token embedded in the remote (x-access-token:SECRET@) must never be
        # echoed in the actionable message.
        probe = _RefProbe(False)
        result = bootstrap_wiki(
            "https://x-access-token:SECRET@github.com/o/r.git",
            interactive=False,
            bootstrapper=None,
            refs_checker=probe,
            confirm=_never_confirm,
            notify=lambda _m: None,
        )
        self.assertIs(result.tier, Tier.DEGRADE)
        self.assertNotIn("SECRET", result.message)
        self.assertNotIn("x-access-token", result.message)
        self.assertIn("https://github.com/o/r.wiki.git", result.message)
        self.assertIn("https://github.com/o/r/wiki/_new", result.message)


class TestConfirmViaInput(unittest.TestCase):
    """The default GUIDE confirmation prompt. It is only reached on an interactive
    run, but it must still fail safe (treat a closed stdin as 'do not proceed')."""

    def test_returns_false_on_eof(self):
        with patch("builtins.input", side_effect=EOFError):
            self.assertFalse(_confirm_via_input())

    def test_skip_reply_returns_false(self):
        with patch("builtins.input", return_value="skip"):
            self.assertFalse(_confirm_via_input())

    def test_enter_returns_true(self):
        with patch("builtins.input", return_value=""):
            self.assertTrue(_confirm_via_input())


class TestWikiCliWiring(unittest.TestCase):
    """The ``wiki`` command bootstraps before the existing refresh: it degrades
    (exit 4) on an unpublishable wiki and passes through to the refresh on a no-op.
    The orchestration itself is covered above; these tests pin the wiring only."""

    DEGRADE_MESSAGE = (
        "Error: the GitHub wiki has not been initialized.\n"
        "Initialize it once: open\n"
        "  https://github.com/o/r/wiki/_new\n"
        "and save a page, then re-run the wiki step."
    )

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.harness_dir = self._tmp.name

    def _patch_metadata(self):
        return patch(
            "solomon_harness.bootstrap.get_project_metadata",
            return_value=("proj", "https://github.com/o/r.git", "Python"),
        )

    def test_degrade_through_cli_exits_4_and_skips_the_refresh(self):
        captured = {}

        def _fake_bootstrap(git_remote, **kwargs):
            captured.update(kwargs)
            return WikiBootstrapResult(Tier.DEGRADE, False, 4, self.DEGRADE_MESSAGE)

        index = MagicMock()
        err = io.StringIO()
        with (
            self._patch_metadata(),
            patch("solomon_harness.wiki_bootstrap.bootstrap_wiki", side_effect=_fake_bootstrap),
            patch("solomon_harness.bootstrap.index_codebase", index),
            patch("solomon_harness.bootstrap.write_code_overview", MagicMock()),
            contextlib.redirect_stderr(err),
        ):
            with self.assertRaises(SystemExit) as ctx:
                cli.main(harness_dir=self.harness_dir, argv=["wiki"])
        self.assertEqual(ctx.exception.code, 4)
        self.assertIn("/wiki/_new", err.getvalue())
        self.assertIn("not been initialized", err.getvalue())
        self.assertNotIn("Repository not found", err.getvalue())
        index.assert_not_called()
        # The plain CLI path must never inject a concrete browser bootstrapper.
        self.assertIsNone(captured.get("bootstrapper"))
        self.assertIn("interactive", captured)

    def test_noop_passthrough_runs_the_existing_refresh(self):
        def _fake_bootstrap(git_remote, **kwargs):
            return WikiBootstrapResult(Tier.NOOP, True, 0, "")

        index = MagicMock()
        overview = MagicMock(return_value="/x/docs/wiki/Code-Overview.md")
        out = io.StringIO()
        with (
            self._patch_metadata(),
            patch("solomon_harness.wiki_bootstrap.bootstrap_wiki", side_effect=_fake_bootstrap),
            patch("solomon_harness.bootstrap.index_codebase", index),
            patch("solomon_harness.bootstrap.write_code_overview", overview),
            patch("solomon_harness.tools.database_client.DatabaseClient"),
            contextlib.redirect_stdout(out),
        ):
            cli.main(harness_dir=self.harness_dir, argv=["wiki"])
        index.assert_called_once()
        overview.assert_called_once()
        self.assertIn("Updated code-overview wiki page", out.getvalue())


if __name__ == "__main__":
    unittest.main()
