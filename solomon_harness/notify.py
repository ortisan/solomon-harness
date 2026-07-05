"""Outbound-only notification egress (Phase 3).

Decouples the human control plane from the execution host the safe way: status
flows OUT (console, or a Slack / generic incoming webhook), but the only
state-changing approval path stays the human gh review. There is no inbound
listener and no command channel, so this adds no self-hosted loop (C1) and cannot
merge or approve anything (C2). The webhook URL comes from the environment, never
from committed config (secure-by-default).

Disabled by default: with no webhook configured and no explicit console mode, the
notifier is a no-op, so existing behavior is unchanged.
"""

import json
import os
import sys
import urllib.request
from typing import Any, Callable, Dict, Mapping, Optional

DEFAULT_WEBHOOK_ENV = "SOLOMON_NOTIFY_WEBHOOK"


class Notifier:
    def send(self, event: str, message: str) -> None:
        raise NotImplementedError


class ConsoleNotifier(Notifier):
    def __init__(self, stream: Any = None) -> None:
        self.stream = stream if stream is not None else sys.stderr

    def send(self, event: str, message: str) -> None:
        print(f"[solomon:{event}] {message}", file=self.stream)


class WebhookNotifier(Notifier):
    """POSTs a JSON body to an incoming webhook (Slack-compatible 'text' field)."""

    def __init__(self, url: str, opener: Optional[Callable] = None, timeout: float = 5.0) -> None:
        self.url = url
        self.timeout = timeout
        self._opener = opener or urllib.request.urlopen

    def send(self, event: str, message: str) -> None:
        # Only POST to http(s); refuse file:// and other schemes a misconfigured
        # or hostile SOLOMON_NOTIFY_WEBHOOK could otherwise make urlopen open.
        if not self.url.lower().startswith(("http://", "https://")):
            raise ValueError(f"refusing non-http notify URL scheme: {self.url!r}")
        body = json.dumps({"text": f"[solomon:{event}] {message}"}).encode("utf-8")
        req = urllib.request.Request(
            self.url, data=body, headers={"Content-Type": "application/json"}, method="POST"
        )
        self._opener(req, timeout=self.timeout)


def _read_notify_config(workspace_root: str) -> Dict[str, Any]:
    path = os.path.join(workspace_root, ".agent", "config.json")
    try:
        with open(path, "r", encoding="utf-8") as f:
            block = json.load(f).get("notify")
        return block if isinstance(block, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def get_notifier(workspace_root: str, env: Optional[Dict[str, str]] = None) -> Optional[Notifier]:
    """Select an adapter from config + env; None (no-op) when nothing is configured."""
    resolved_env: Mapping[str, str] = os.environ if env is None else env
    cfg = _read_notify_config(workspace_root)
    if cfg.get("enabled") is False:
        return None
    url = resolved_env.get(cfg.get("webhook_env", DEFAULT_WEBHOOK_ENV))
    mode = cfg.get("mode")
    if url and url.lower().startswith(("http://", "https://")) and mode in (None, "webhook"):
        return WebhookNotifier(url)
    if mode == "console":
        return ConsoleNotifier()
    return None


def send(workspace_root: str, event: str, message: str, env: Optional[Dict[str, str]] = None) -> bool:
    """Best-effort notify; returns True if a notification was emitted."""
    try:
        notifier = get_notifier(workspace_root, env=env)
        if notifier is None:
            return False
        notifier.send(event, message)
        return True
    except Exception:
        return False


def log_progress(message: str) -> None:
    """Write progress/informational messages so they are visible to the user.

    It always writes to stderr (so it doesn't pollute stdout for parseable commands).
    If sys.stderr is not a TTY (meaning it is redirected or captured), it additionally writes
    directly to the controlling terminal (/dev/tty) so that the user still sees it.
    """
    formatted = f"[solomon:info] {message}"
    sys.stderr.write(formatted + "\n")
    sys.stderr.flush()
    if not sys.stderr.isatty():
        # Standard error is redirected/captured. Try to write directly to TTY.
        try:
            with open("/dev/tty", "w", encoding="utf-8") as tty:
                tty.write(formatted + "\n")
                tty.flush()
        except OSError:
            pass



