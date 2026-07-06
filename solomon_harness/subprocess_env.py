"""Shared subprocess-environment hygiene.

Any subprocess this codebase spawns -- ``git``, ``gh``, or a headless engine CLI
(``claude``/``agy``) -- must not inherit the caller's ``GIT_*``
environment. Inside a git worktree or a git hook, ``GIT_DIR`` / ``GIT_WORK_TREE``
(and friends) are exported and would redirect a child ``git -C <path>`` call back
to the enclosing repository instead of the intended one; inherited into a ``gh``
call or an engine subprocess they are pure noise that can only cause confusion.

This module is the single, canonical place that strips them. Before this fix the
codebase had three different partial implementations of the same scrub (a
strip-everything version in ``home.py``, a curated seven-name allowlist in
``worktree.py``, and several call sites that stripped nothing at all); every one
of them should now call :func:`clean_git_env` instead of reimplementing it.
"""

import os
from typing import Dict, Optional


def clean_git_env(workspace_root: Optional[str] = None) -> Dict[str, str]:
    """Return a copy of the environment with every ``GIT_*`` variable removed.

    If ``workspace_root`` is provided, sets ``GIT_CEILING_DIRECTORIES`` to the parent
    of the workspace root so git commands never walk up past the workspace.
    """
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    if workspace_root:
        env["GIT_CEILING_DIRECTORIES"] = os.path.dirname(os.path.abspath(workspace_root))
    return env
