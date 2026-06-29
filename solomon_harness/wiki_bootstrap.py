"""Shared primitives for the GitHub wiki bootstrap degrade ladder (issue #117).

GitHub creates a repository's ``<repo>.wiki.git`` content repository only after
the first wiki page is saved through its web UI, and exposes no REST, GraphQL or
``gh`` path to create that first page. These helpers are the observable detection
seam shared by the wiki step and the init detect-and-hint
(``solomon_harness.bootstrap``): they resolve the wiki URLs from a repository
remote and probe the remote for refs. None of them drive a browser or block on
input, so they are safe in headless and CI contexts.

The interactive top of the ladder builds on those helpers: ``choose_tier`` is the
NOOP/DEGRADE/GUIDE/AUTOMATE routing decision.

TODO(#117, next step on this same branch): ``bootstrap_wiki`` orchestrates the
chosen tier over an injected ``BrowserBootstrapper`` port (whose only real adapter
drives the claude-in-chrome MCP from the host), verifying success by re-probing
the refs rather than trusting the port. The no-browser floor in this module and in
scripts/wiki-sync.sh stands alone without it.
"""

from __future__ import annotations

import enum
import subprocess
from typing import Any, Callable


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
