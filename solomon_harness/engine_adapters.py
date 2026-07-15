"""Native non-interactive command builders for supported model hosts.

This module deliberately contains no workflow policy.  It is the process-adapter
edge of the harness: callers provide a workspace and optional native capabilities,
and receive an argv list suitable for ``subprocess`` without shell interpolation.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Iterable, Mapping, Optional, Sequence


ENGINES = ("agy", "claude", "codex")


def _unique_paths(paths: Iterable[os.PathLike[str] | str]) -> tuple[str, ...]:
    """Return paths in first-seen order without emitting duplicate flags."""

    result: list[str] = []
    seen: set[str] = set()
    for value in paths:
        path = str(Path(value))
        if path not in seen:
            seen.add(path)
            result.append(path)
    return tuple(result)


def build_engine_command(
    engine: str,
    workspace_root: os.PathLike[str] | str,
    *,
    executable: Optional[str] = None,
    json_output: bool = False,
    allowed_tools: Optional[str | Sequence[str]] = None,
    add_dirs: Iterable[os.PathLike[str] | str] = (),
    session_id: Optional[str] = None,
    print_timeout: str = "20m0s",
) -> list[str]:
    """Build a host-native headless argv.

    Prompts are supplied on stdin.  Claude's ``-p`` reads stdin when no prompt
    argument follows it; AGY and Codex make that contract explicit with ``-``.
    The defaults retain hook discovery and trust checks.  In particular, Codex's
    hook-trust bypass flag is never emitted.

    ``json_output`` enables a documented structured stream where the host has
    one.  Current AGY has no supported ``-o json`` equivalent, so the flag does
    not change its argv; callers must not infer USD cost from its plain output.
    """

    normalized = engine.strip().lower()
    if normalized not in ENGINES:
        choices = ", ".join(ENGINES)
        raise ValueError(f"unknown engine {engine!r}; expected one of: {choices}")

    root = str(Path(workspace_root))
    extra_dirs = _unique_paths(add_dirs)

    if normalized == "claude":
        command = [executable or "claude", "-p"]
        if json_output:
            command.extend(["--output-format", "json"])
        if allowed_tools:
            if isinstance(allowed_tools, str):
                value = allowed_tools
            else:
                value = ", ".join(str(tool) for tool in allowed_tools)
            if value.strip():
                command.extend(["--allowed-tools", value])
        for directory in extra_dirs:
            command.extend(["--add-dir", directory])
        return command

    if normalized == "agy":
        # Keep ``-p -`` adjacent: it is AGY's stable, native non-interactive
        # surface and makes accidental reintroduction of the removed ``-o``
        # option visible in command-contract tests.
        command = [executable or "agy", "-p", "-", "--sandbox"]
        if session_id:
            command.extend(["--conversation", session_id])
        if print_timeout:
            command.extend(["--print-timeout", print_timeout])
        for directory in extra_dirs:
            command.extend(["--add-dir", directory])
        return command

    command = [
        executable or "codex",
        "exec",
        "--sandbox",
        "workspace-write",
        "-C",
        root,
    ]
    if json_output:
        command.append("--json")
    for directory in extra_dirs:
        command.extend(["--add-dir", directory])
    command.append("-")
    return command


def build_engine_environment(
    base: Optional[Mapping[str, str]] = None,
    *,
    session_id: Optional[str] = None,
) -> dict[str, str]:
    """Return the common child-process environment for a headless stage.

    Git can export repository-local variables while invoking hooks.  Carrying
    those variables into a different worktree makes Git operate on the wrong
    repository, so the adapter removes the local Git context while preserving
    ordinary user configuration such as ``GIT_SSH_COMMAND``.
    """

    environment = dict(os.environ if base is None else base)
    for name in (
        "GIT_ALTERNATE_OBJECT_DIRECTORIES",
        "GIT_COMMON_DIR",
        "GIT_DIR",
        "GIT_INDEX_FILE",
        "GIT_OBJECT_DIRECTORY",
        "GIT_PREFIX",
        "GIT_WORK_TREE",
    ):
        environment.pop(name, None)
    environment["SOLOMON_SUBPROCESS"] = "1"
    if session_id:
        environment["SOLOMON_SESSION_ID"] = session_id
    return environment
