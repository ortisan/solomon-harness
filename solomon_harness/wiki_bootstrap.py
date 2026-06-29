"""Shared primitives for the GitHub wiki bootstrap degrade ladder (issue #117).

GitHub creates a repository's ``<repo>.wiki.git`` content repository only after
the first wiki page is saved through its web UI, and exposes no REST, GraphQL or
``gh`` path to create that first page. These helpers are the observable detection
seam shared by the wiki step and the init detect-and-hint
(``solomon_harness.bootstrap``): they resolve the wiki URLs from a repository
remote and probe the remote for refs. None of them drive a browser or block on
input, so they are safe in headless and CI contexts.

The interactive top of the ladder builds on those helpers: ``choose_tier`` is the
NOOP/DEGRADE/GUIDE/AUTOMATE routing decision, and ``bootstrap_wiki`` orchestrates
the chosen tier over an injected ``BrowserBootstrapper`` port. The port's only
real adapter drives the claude-in-chrome MCP from the host LLM and so cannot be
called from pure Python; the pure-CLI path injects no bootstrapper and therefore
only ever GUIDEs or DEGRADEs. Success is asserted by re-probing the refs
(``wiki_refs_present``), never by trusting the port's return value, so a tampered
or changed editor page cannot report a false success. The no-browser floor in
this module and in scripts/wiki-sync.sh stands alone without the browser tier.
"""

from __future__ import annotations

import enum
import subprocess
from dataclasses import dataclass
from typing import Any, Callable, Protocol


GITHUB_HOSTS = frozenset({"github.com"})


def remote_host(remote_url: str) -> str | None:
    """Parse the bare host from a git remote, or ``None`` when none can be parsed.

    Handles the ``scheme://[user[:secret]@]host[:port]/path`` form (https and
    ssh) and the scp-like ``user@host:path`` form. Any userinfo and port are
    stripped, so the result is the lowercase host alone. This is the basis for
    deciding GitHub identity by an exact host match rather than a bypassable
    substring.
    """
    if not remote_url or remote_url == "none":
        return None
    url = remote_url.strip()
    if "://" in url:
        authority = url.split("://", 1)[1].split("/", 1)[0]
    elif "@" in url and ":" in url.split("@", 1)[1]:
        authority = url.split("@", 1)[1].split("/", 1)[0]
    else:
        return None
    authority = authority.rsplit("@", 1)[-1]  # drop any user[:secret]@
    host = authority.split(":", 1)[0].strip()  # drop any :port or scp :path
    return host.lower() or None


def is_github_remote(
    remote_url: str, *, allowed_hosts: frozenset[str] = GITHUB_HOSTS
) -> bool:
    """Report whether ``remote_url``'s host is an allowlisted GitHub host.

    The decision is an exact host match against ``allowed_hosts`` (default
    ``github.com``; pass a configured GitHub Enterprise host to extend it), so a
    crafted remote such as ``git@github.com.evil.com:o/r.git`` is rejected
    rather than accepted by a substring check and handed to the browser.
    """
    host = remote_host(remote_url)
    return host is not None and host in allowed_hosts


def _strip_url_userinfo(url: str) -> str:
    """Remove ``user[:secret]@`` userinfo from a URL's authority before it is
    echoed in a message, so a token embedded in a remote cannot leak. scp-like
    ``git@host:path`` remotes (no ``//``) are left untouched: that user is the
    conventional ``git`` account, not a secret.
    """
    if "://" not in url:
        return url
    scheme, _, rest = url.partition("://")
    authority, slash, path = rest.partition("/")
    if "@" in authority:
        authority = authority.rsplit("@", 1)[-1]
    return f"{scheme}://{authority}{slash}{path}"


def resolve_wiki_clone_url(remote_url: str) -> str | None:
    """Map a repository remote URL to its ``.wiki.git`` clone URL.

    Mirrors the transformation in ``scripts/wiki-sync.sh``. Returns ``None`` when
    there is no usable remote (``"none"`` or empty) so callers skip detection.
    """
    if not remote_url or remote_url == "none":
        return None
    url = remote_url.rstrip("/")
    if url.endswith(".wiki.git"):
        return url
    if url.endswith(".wiki"):
        return url + ".git"
    if url.endswith(".git"):
        return url[: -len(".git")] + ".wiki.git"
    return url + ".wiki.git"


def resolve_web_wiki_url(remote_url: str) -> str | None:
    """Map a repository remote URL to the web URL of its first-page editor.

    Returns the ``https://<host>/<owner>/<repo>/wiki/_new`` URL an operator opens
    to initialize the wiki, normalizing the common SSH shapes to https, or
    ``None`` when no usable remote is configured.
    """
    if not remote_url or remote_url == "none":
        return None
    url = remote_url.rstrip("/")
    if url.endswith(".wiki.git"):
        url = url[: -len(".wiki.git")]
    elif url.endswith(".git"):
        url = url[: -len(".git")]
    if url.startswith("git@"):
        host, _, path = url[len("git@") :].partition(":")
        url = f"https://{host}/{path}"
    elif url.startswith("ssh://git@"):
        url = "https://" + url[len("ssh://git@") :]
    return f"{url}/wiki/_new"


def wiki_refs_present(
    wiki_url: str,
    timeout: float = 10.0,
    *,
    runner: Callable[..., Any] = subprocess.run,
) -> bool | None:
    """Report whether the wiki content repository advertises any heads.

    Returns ``True`` for at least one ref (initialized), ``False`` for zero refs
    or a missing remote (uninitialized), and ``None`` when the probe is
    inconclusive (it timed out or could not be run). The git invocation is
    injected via ``runner`` (defaults to ``subprocess.run``) so callers can stub
    it in tests; this never opens a browser or prompts.
    """
    try:
        completed = runner(
            ["git", "ls-remote", "--heads", wiki_url],
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return None
    except Exception:
        return None
    if completed.returncode != 0:
        return False
    return bool(completed.stdout.strip())


class Tier(enum.Enum):
    """The rung of the wiki-bootstrap degrade ladder a run resolves to.

    NOOP: the wiki is already initialized; do nothing and let the sync proceed.
    AUTOMATE: drive the injected browser to create the first page (interactive,
    usable authenticated browser, confirmed 0 refs).
    GUIDE: print the manual step and wait for the operator (interactive, no usable
    browser/auth).
    DEGRADE: the non-negotiable headless/CI floor; emit the actionable message and
    let the caller exit non-zero, attempting no browser action.
    """

    NOOP = "noop"
    AUTOMATE = "automate"
    GUIDE = "guide"
    DEGRADE = "degrade"


def choose_tier(
    *,
    interactive: bool,
    browser_available: bool,
    authenticated: bool,
    refs_present: bool | None,
) -> Tier:
    """Decide the degrade-ladder tier from the run context. Pure, no side effects.

    ``refs_present`` is the tri-state output of :func:`wiki_refs_present` (``True``
    initialized, ``False`` zero refs, ``None`` inconclusive). The decision is
    ordered by precedence so the safe outcome always wins:

    1. An initialized wiki (``refs_present is True``) is always a NO-OP, so the
       bootstrap is idempotent and never touches an existing wiki.
    2. A non-interactive run is always the DEGRADE floor: no browser is driven
       without an operator, even if a bootstrapper was injected (headless/CI).
    3. An interactive run AUTOMATEs only with a usable, authenticated browser AND a
       confirmed-uninitialized wiki (``refs_present is False``); inconclusive
       detection (``None``) never auto-creates a page that might duplicate one.
    4. Any other interactive run GUIDEs the operator through the manual step.
    """
    if refs_present is True:
        return Tier.NOOP
    if not interactive:
        return Tier.DEGRADE
    if browser_available and authenticated and refs_present is False:
        return Tier.AUTOMATE
    return Tier.GUIDE


class BrowserBootstrapper(Protocol):
    """Port for the host-driven browser that saves the first wiki page.

    The only real adapter drives the claude-in-chrome MCP from the host LLM, so it
    cannot be constructed or called from pure Python -- ``bootstrap_wiki`` accepts
    it as an injected dependency. Tests inject a structural fake; the real adapter
    is a documented host-integration seam, proven manually at review. The port's
    return is never trusted: ``bootstrap_wiki`` verifies the save with an
    independent ``git ls-remote`` re-probe (STRIDE tampering control, R-3).
    """

    def is_authenticated(self) -> bool:
        """Report whether the browser holds an authenticated GitHub session.

        Drives the AUTOMATE-vs-GUIDE decision so the harness never assumes an
        identity (STRIDE spoofing control, R-2).
        """
        ...

    def create_first_page(self, web_new_url: str) -> None:
        """Open ``web_new_url`` (``<repo>/wiki/_new``) and save a minimal page.

        Best-effort: it raises nothing observable that the caller relies on, since
        success is confirmed only by the post-save ref re-probe.
        """
        ...


@dataclass(frozen=True)
class WikiBootstrapResult:
    """The outcome of a bootstrap attempt, consumed by the cli ``wiki`` command.

    ``proceed`` is ``True`` when the wiki is ready (already initialized or just
    initialized) and the caller should run the existing refresh; ``False`` when
    the caller must degrade. ``exit_code`` is 0 when proceeding and 4 on degrade.
    ``message`` is the actionable text the caller prints to stderr on degrade
    (it names the cause and the ``<repo>/wiki/_new`` step and carries no raw git
    error).
    """

    tier: Tier
    proceed: bool
    exit_code: int
    message: str


def _uninitialized_message(clone_url: str, web_url: str) -> str:
    clone_url = _strip_url_userinfo(clone_url)
    web_url = _strip_url_userinfo(web_url)
    return (
        "Error: the GitHub wiki has not been initialized.\n"
        f"GitHub creates the wiki content repository ({clone_url}) only after the "
        "first page is saved through the web UI, and exposes no API for that page.\n"
        "Initialize it once: open\n"
        f"  {web_url}\n"
        "and save a page (any content), then re-run the wiki step to publish docs."
    )


def _inconclusive_message(clone_url: str, web_url: str) -> str:
    clone_url = _strip_url_userinfo(clone_url)
    web_url = _strip_url_userinfo(web_url)
    return (
        "Error: could not determine whether the GitHub wiki is initialized.\n"
        "Detection was inconclusive (network or timeout): the wiki content "
        f"repository ({clone_url}) did not respond.\n"
        "If the wiki has never been opened, initialize it once: open\n"
        f"  {web_url}\n"
        "and save a page (any content), then re-run the wiki step."
    )


def _degrade_message(clone_url: str, web_url: str, refs_present: bool | None) -> str:
    """Pick the actionable message by the detection state.

    ``refs_present is None`` means detection was inconclusive (timeout/network);
    any other reached-here state means the wiki advertised zero refs.
    """
    if refs_present is None:
        return _inconclusive_message(clone_url, web_url)
    return _uninitialized_message(clone_url, web_url)


def _guide_message(web_url: str) -> str:
    web_url = _strip_url_userinfo(web_url)
    return (
        "The GitHub wiki has not been initialized, so there is nothing to publish "
        "to yet.\n"
        "Initialize it once: open\n"
        f"  {web_url}\n"
        "and save a page (any content). This run continues once you confirm."
    )


def _emit(message: str) -> None:
    print(message)


def _confirm_via_input() -> bool:
    """Block for the operator in the GUIDE tier. Returns False on EOF or 'skip'.

    Only reached on an interactive run; a headless run resolves to DEGRADE, which
    never calls this, so the step cannot block on input in CI.
    """
    try:
        reply = input(
            "Press Enter once the first wiki page is saved to continue, "
            "or type 'skip' to stop: "
        )
    except EOFError:
        return False
    return reply.strip().lower() != "skip"


def bootstrap_wiki(
    git_remote: str,
    *,
    interactive: bool,
    bootstrapper: BrowserBootstrapper | None = None,
    refs_checker: Callable[..., bool | None] = wiki_refs_present,
    confirm: Callable[[], bool] = _confirm_via_input,
    notify: Callable[[str], None] = _emit,
    timeout: float = 10.0,
) -> WikiBootstrapResult:
    """Run the degrade ladder for the wiki step and report what the caller does.

    The chosen tier (see :func:`choose_tier`) is driven by the run context: the
    injected ``bootstrapper`` (``None`` on the pure-CLI path, so AUTOMATE never
    fires there), its ``is_authenticated`` precheck, ``interactive``, and the
    ``refs_checker`` probe. AUTOMATE drives the port then verifies; GUIDE prints
    the manual step, waits for ``confirm``, then verifies; both succeed only when
    a re-probe shows a ref. DEGRADE returns the actionable message for the caller
    to print and exit 4, attempting no browser action and never prompting. NO-OP
    (already initialized, or no usable GitHub remote) makes no port call and no
    re-probe -- the bootstrap is idempotent.
    """
    clone_url = resolve_wiki_clone_url(git_remote)
    web_url = resolve_web_wiki_url(git_remote)
    # No usable GitHub remote (mock mode, or a non-GitHub host): nothing to
    # bootstrap. The host is matched exactly against the allowlist, never by a
    # substring, so a crafted remote whose host only looks like GitHub is treated
    # as non-GitHub here -- no web URL is built for the browser and AUTOMATE never
    # fires. Proceed without probing the network so the step stays offline-safe.
    if not clone_url or not web_url or not is_github_remote(git_remote):
        return WikiBootstrapResult(Tier.NOOP, proceed=True, exit_code=0, message="")

    refs = refs_checker(clone_url, timeout=timeout)
    browser_available = bootstrapper is not None
    authenticated = bootstrapper.is_authenticated() if bootstrapper is not None else False
    tier = choose_tier(
        interactive=interactive,
        browser_available=browser_available,
        authenticated=authenticated,
        refs_present=refs,
    )

    if tier is Tier.NOOP:
        return WikiBootstrapResult(tier, proceed=True, exit_code=0, message="")
    if tier is Tier.DEGRADE:
        return WikiBootstrapResult(
            tier, proceed=False, exit_code=4, message=_degrade_message(clone_url, web_url, refs)
        )
    if tier is Tier.AUTOMATE and bootstrapper is not None:
        bootstrapper.create_first_page(web_url)
        return _verify(tier, clone_url, web_url, refs_checker, timeout)

    # GUIDE: print the manual step, wait for the operator, then verify.
    notify(_guide_message(web_url))
    if not confirm():
        return WikiBootstrapResult(
            Tier.GUIDE, proceed=False, exit_code=4, message=_degrade_message(clone_url, web_url, refs)
        )
    return _verify(Tier.GUIDE, clone_url, web_url, refs_checker, timeout)


def _verify(
    tier: Tier,
    clone_url: str,
    web_url: str,
    refs_checker: Callable[..., bool | None],
    timeout: float,
) -> WikiBootstrapResult:
    """Re-probe the wiki refs and report success only if a ref now appears.

    This is the tampering control: success is gated on an independent
    ``git ls-remote``, not on the port's or the operator's claim of success.
    """
    refs_after = refs_checker(clone_url, timeout=timeout)
    if refs_after is True:
        return WikiBootstrapResult(tier, proceed=True, exit_code=0, message="")
    return WikiBootstrapResult(
        tier, proceed=False, exit_code=4, message=_degrade_message(clone_url, web_url, refs_after)
    )
