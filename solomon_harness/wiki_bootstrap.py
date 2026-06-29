"""Shared primitives for the GitHub wiki bootstrap degrade ladder (issue #117).

GitHub creates a repository's ``<repo>.wiki.git`` content repository only after
the first wiki page is saved through its web UI, and exposes no REST, GraphQL or
``gh`` path to create that first page. These helpers are the observable detection
seam shared by the wiki step and the init detect-and-hint
(``solomon_harness.bootstrap``): they resolve the wiki URLs from a repository
remote and probe the remote for refs. None of them drive a browser or block on
input, so they are safe in headless and CI contexts.

TODO(#117, deferred browser tier on this same branch): steps 5-7 of the plan add
the interactive top of the ladder here -- ``choose_tier`` (the
NOOP/DEGRADE/GUIDE/AUTOMATE decision), ``bootstrap_wiki`` orchestrated over an
injected ``BrowserBootstrapper`` port whose only real adapter drives the
claude-in-chrome MCP, and the cli ``wiki`` wiring. They build on the helpers
below; the no-browser floor in this module and in scripts/wiki-sync.sh stands
alone without them.
"""

from __future__ import annotations

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
