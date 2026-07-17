"""Host detection and workflow invocation rendering.

Claude Code and Gemini expose Solomon workflows as slash commands. Codex
exposes the same workflows as skills invoked with ``$``. User-facing output
must render the syntax accepted by the active host so suggested commands can
be copied without translation.
"""

import os
from typing import Mapping, Optional


def current_host(environ: Optional[Mapping[str, str]] = None) -> str:
    """Return the active host name, preferring an explicit Solomon override."""
    env = os.environ if environ is None else environ
    configured = env.get("SOLOMON_HOST", "").strip().lower()
    if configured:
        return configured
    if env.get("CODEX_THREAD_ID") or env.get("CODEX_CI"):
        return "codex"
    if env.get("CLAUDECODE"):
        return "claude"
    if env.get("GEMINI_CLI"):
        return "gemini"
    return "unknown"


def workflow_invocation(stage: str, arguments: str = "", host: str = "unknown") -> str:
    """Render one copyable Solomon workflow invocation for ``host``."""
    name = stage if stage.startswith("solomon-") else f"solomon-{stage}"
    prefix = "$" if host == "codex" else "/"
    invocation = f"{prefix}{name}"
    return f"{invocation} {arguments}" if arguments else invocation
