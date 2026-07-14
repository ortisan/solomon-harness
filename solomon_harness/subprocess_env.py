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
from typing import Dict


def clean_git_env() -> Dict[str, str]:
    """Return a copy of the environment with every ``GIT_*`` variable removed."""
    return {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
