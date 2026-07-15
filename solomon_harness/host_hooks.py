"""Normalize native lifecycle-hook payloads into one Solomon contract."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any, Iterable, Mapping, Optional


HOOK_HOSTS = ("agy", "claude", "codex")
_SHELL_TOOLS = {"bash", "command", "run_command", "shell"}
_PATCH_TOOLS = {"apply_patch", "patch"}
_WRITE_TOOLS = {
    "edit",
    "multiedit",
    "notebookedit",
    "replace_file_content",
    "multi_replace_file_content",
    "write",
    "write_to_file",
}
_PATH_KEYS = (
    "TargetFile",
    "targetFile",
    "target_file",
    "file_path",
    "notebook_path",
    "path",
)
_PATCH_PATH_RE = re.compile(
    r"^(?:\*\*\* (?:Add|Delete|Update) File:|\*\*\* Move to:|---|\+\+\+)\s+(.+?)\s*$"
)


@dataclass(frozen=True)
class NormalizedHookInput:
    """Host-independent facts used by the loop guard."""

    host: str
    session_id: str
    tool_kind: str
    command: str = ""
    target_paths: tuple[str, ...] = ()


@dataclass(frozen=True)
class HookVerdict:
    """Portable policy decision before host-specific serialization."""

    allow: bool
    reason: str = ""


@dataclass(frozen=True)
class HookExecution:
    """Bytes and status a hook command writes back to its host."""

    exit_code: int
    stdout: str = ""
    stderr: str = ""


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _text(value: Any) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, (list, tuple)) and all(isinstance(item, str) for item in value):
        return " ".join(value)
    return ""


def _deduplicate(values: Iterable[str]) -> tuple[str, ...]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        clean = value.strip().strip('"\'')
        if clean.startswith("a/") or clean.startswith("b/"):
            clean = clean[2:]
        if not clean or clean == "/dev/null" or clean in seen:
            continue
        seen.add(clean)
        result.append(clean)
    return tuple(result)


def _nested_paths(value: Any) -> Iterable[str]:
    if isinstance(value, Mapping):
        for key, child in value.items():
            if key in _PATH_KEYS and isinstance(child, str):
                yield child
            elif isinstance(child, (Mapping, list, tuple)):
                yield from _nested_paths(child)
    elif isinstance(value, (list, tuple)):
        for child in value:
            yield from _nested_paths(child)


def extract_patch_paths(patch: str) -> tuple[str, ...]:
    """Extract every target named by apply_patch or unified-diff text."""

    values: list[str] = []
    for line in patch.splitlines():
        match = _PATCH_PATH_RE.match(line)
        if not match:
            continue
        path = match.group(1)
        # Unified diffs may suffix a timestamp after a tab.
        values.append(path.split("\t", 1)[0])
    return _deduplicate(values)


def normalize_hook_input(host: str, payload: Mapping[str, Any]) -> NormalizedHookInput:
    """Translate a Claude, AGY, or Codex PreToolUse payload.

    Missing optional fields are represented by empty strings/tuples.  An
    unsupported host or non-object payload is rejected instead of being
    silently treated as an allow decision by downstream policy code.
    """

    normalized_host = host.strip().lower()
    if normalized_host not in HOOK_HOSTS:
        choices = ", ".join(HOOK_HOSTS)
        raise ValueError(f"unknown hook host {host!r}; expected one of: {choices}")
    if not isinstance(payload, Mapping):
        raise TypeError("hook payload must be an object")

    if normalized_host == "agy":
        call = _mapping(payload.get("toolCall"))
        tool_name = _text(call.get("name"))
        tool_input = _mapping(call.get("args"))
        session_id = _text(payload.get("conversationId"))
    else:
        tool_name = _text(payload.get("tool_name") or payload.get("tool"))
        tool_input = _mapping(payload.get("tool_input") or payload.get("input"))
        session_id = _text(payload.get("session_id") or payload.get("sessionId"))

    lowered_tool = tool_name.lower()
    command = ""
    paths: tuple[str, ...] = ()
    if lowered_tool in _SHELL_TOOLS:
        tool_kind = "shell"
        command = _text(
            tool_input.get("command")
            or tool_input.get("CommandLine")
            or tool_input.get("command_line")
        )
    elif lowered_tool in _PATCH_TOOLS:
        tool_kind = "patch"
        command = _text(
            tool_input.get("command")
            or tool_input.get("patch")
            or tool_input.get("input")
        )
        paths = extract_patch_paths(command)
    elif lowered_tool in _WRITE_TOOLS:
        tool_kind = "write"
        paths = _deduplicate(_nested_paths(tool_input))
    else:
        tool_kind = "other"
        paths = _deduplicate(_nested_paths(tool_input))

    return NormalizedHookInput(
        host=normalized_host,
        session_id=session_id,
        tool_kind=tool_kind,
        command=command,
        target_paths=paths,
    )


def serialize_hook_verdict(host: str, verdict: HookVerdict) -> HookExecution:
    """Serialize one policy verdict using a host's native hook protocol."""

    normalized_host = host.strip().lower()
    if normalized_host not in HOOK_HOSTS:
        raise ValueError(f"unknown hook host {host!r}")
    reason = verdict.reason.strip()
    if normalized_host == "agy":
        payload = {
            "decision": "allow" if verdict.allow else "deny",
            "reason": reason,
        }
        return HookExecution(exit_code=0, stdout=json.dumps(payload, sort_keys=True) + "\n")
    if verdict.allow:
        return HookExecution(exit_code=0)
    return HookExecution(exit_code=2, stderr=(reason or "Blocked by Solomon policy") + "\n")


def serialize_session_context(
    host: str,
    context: str,
    *,
    invocation_number: Optional[int] = None,
) -> HookExecution:
    """Serialize session-resume context for the three lifecycle protocols."""

    normalized_host = host.strip().lower()
    if normalized_host not in HOOK_HOSTS:
        raise ValueError(f"unknown hook host {host!r}")
    if normalized_host == "agy":
        steps = []
        if invocation_number in (None, 0) and context:
            steps.append({"ephemeralMessage": context})
        return HookExecution(
            exit_code=0,
            stdout=json.dumps({"injectSteps": steps}, sort_keys=True) + "\n",
        )
    return HookExecution(exit_code=0, stdout=context)
