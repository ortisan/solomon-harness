"""Neutral ownership contract for merge-managed host adapter files.

Both the installer and the native adapter compiler need to identify the exact
Solomon-owned fragment of a shared host file.  This module is deliberately
independent of both orchestration layers so dependency flow remains one-way.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


TEXT_START = "<!-- solomon-harness:start -->"
TEXT_END = "<!-- solomon-harness:end -->"
TOML_START = "# >>> solomon-harness managed adapter >>>"
TOML_END = "# <<< solomon-harness managed adapter <<<"


class AdapterOwnershipError(RuntimeError):
    """Raised when a merge-managed adapter cannot be inspected unambiguously."""


def strategy_for_adapter(relative: str) -> str:
    """Return the deterministic ownership strategy for a supported adapter path."""

    if relative in {
        ".claude/settings.json",
        ".mcp.json",
        ".agents/hooks.json",
        ".agents/mcp_config.json",
        ".agents/plugins/solomon/mcp_config.json",
        ".codex/hooks.json",
    }:
        return "json-merge"
    if relative == ".codex/config.toml":
        return "toml-merge"
    if relative in {"AGENTS.md", ".claude/CLAUDE.md"}:
        return "marker-merge"
    return "replace"


def contains_solomon_hook(value: Any, *, host: str) -> bool:
    """Return whether a JSON node invokes Solomon for the selected host."""

    text = json.dumps(value, sort_keys=True)
    return "solomon_harness.cli host-hook" in text and f"--host {host}" in text


def _marked_fragment(text: str, start: str, end: str) -> str:
    if text.count(start) != 1 or text.count(end) != 1:
        raise AdapterOwnershipError(
            "Managed adapter markers are missing or ambiguous"
        )
    _, remainder = text.split(start, 1)
    managed, _ = remainder.split(end, 1)
    return f"{start}{managed}{end}"


def _managed_json_fragment(document: dict[str, Any], relative: str) -> Any:
    if relative in {".claude/settings.json", ".codex/hooks.json"}:
        host = "claude" if relative == ".claude/settings.json" else "codex"
        hooks = document.get("hooks")
        managed: dict[str, list[Any]] = {}
        if isinstance(hooks, dict):
            for event in sorted(hooks):
                values = hooks[event]
                if not isinstance(values, list):
                    continue
                nodes = [item for item in values if contains_solomon_hook(item, host=host)]
                if nodes:
                    managed[event] = nodes
        return {"hooks": managed}
    if relative == ".agents/hooks.json":
        names = ("solomon-loop-guard", "solomon-session-resume")
        return {name: document[name] for name in names if name in document}
    if relative in {
        ".agents/mcp_config.json",
        ".agents/plugins/solomon/mcp_config.json",
        ".mcp.json",
    }:
        servers = document.get("mcpServers")
        value = servers.get("solomon-memory") if isinstance(servers, dict) else None
        return {"mcpServers": {"solomon-memory": value}}
    raise AdapterOwnershipError(f"Unsupported managed JSON adapter: {relative}")


def managed_adapter_digest(path: Path, relative: str) -> str:
    """Hash only the Solomon-owned fragment of one shared adapter.

    Preconditions: ``relative`` names a merge-managed adapter and ``path`` is
    readable.  The result is stable across changes to user-owned siblings.
    Missing or ambiguous markers and malformed JSON fail closed with
    :class:`AdapterOwnershipError`.
    """

    strategy = strategy_for_adapter(relative)
    try:
        if strategy == "marker-merge":
            content = _marked_fragment(
                path.read_text(encoding="utf-8"), TEXT_START, TEXT_END
            ).encode()
        elif strategy == "toml-merge":
            content = _marked_fragment(
                path.read_text(encoding="utf-8"), TOML_START, TOML_END
            ).encode()
        elif strategy == "json-merge":
            document = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(document, dict):
                raise AdapterOwnershipError(
                    f"Managed JSON adapter is not an object: {path}"
                )
            fragment = _managed_json_fragment(document, relative)
            content = json.dumps(
                fragment,
                ensure_ascii=False,
                separators=(",", ":"),
                sort_keys=True,
            ).encode()
        else:
            raise AdapterOwnershipError(f"Adapter is not merge-managed: {relative}")
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise AdapterOwnershipError(
            f"Cannot inspect managed adapter {path}"
        ) from exc
    return hashlib.sha256(content).hexdigest()
