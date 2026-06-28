"""The harness's interactive voice.

Solomon speaks with a sage icon. This icon appears ONLY in interactive output --
the CLI, the session hooks, and the /solomon-* workflow summaries the host tool
shows the user. It never appears in commits, PRs, documentation, or code
comments: the humanizer rule still bans emojis there.
"""

ICON = "\U0001f9d9"  # sage / wise elder
NAME = "Solomon"
PREFIX = f"{ICON} {NAME}:"


def say(message: str) -> str:
    """Prefix a user-facing line with Solomon's voice."""
    return f"{PREFIX} {message}"
