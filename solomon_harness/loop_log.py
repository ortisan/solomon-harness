"""Read-only loop activity feed.

A pure formatter over the project memory (the single source of truth): it merges
loop runs, decisions and handoffs into one chronological "what changed and why"
view, so an otherwise-opaque loop becomes auditable without querying the store by
hand. It writes nothing — there is no second source of truth to drift.
"""

from typing import Any, Dict, List


def _epoch(value: Any) -> float:
    if not value:
        return 0.0
    try:
        import datetime

        s = str(value).replace(" ", "T").rstrip("Z")
        if "+" in s:
            s = s.split("+")[0]
        return datetime.datetime.fromisoformat(s).timestamp()
    except ValueError:
        return 0.0


def gather_feed(db: Any, last: int = 20) -> List[Dict[str, str]]:
    """Collect recent loop runs, decisions and handoffs as feed entries."""
    entries: List[Dict[str, str]] = []

    def _safe(fn, *a):
        try:
            return fn(*a) or []
        except Exception:
            return []

    for r in _safe(db.list_loop_runs, last):
        entries.append(
            {
                "kind": "loop_run",
                "when": str(r.get("created_at", "")),
                "text": f"/solomon-{r.get('stage', '?')} {r.get('target', '')}: "
                f"{r.get('decision', '')} ({r.get('status', '?')})".strip(),
            }
        )
    for d in _safe(getattr(db, "list_decisions", lambda *_: []), last):
        outcome = d.get("outcome")
        entries.append(
            {
                "kind": "decision",
                "when": str(d.get("created_at", "")),
                "text": d.get("title", "") + (f" -> {outcome}" if outcome else ""),
            }
        )
    for h in _safe(getattr(db, "list_handoffs", lambda *_: []), last):
        entries.append(
            {
                "kind": "handoff",
                "when": str(h.get("timestamp", "")),
                "text": f"{h.get('sender', '?')} -> {h.get('recipient', '?')} "
                f"({h.get('status', '?')})",
            }
        )

    entries.sort(key=lambda e: _epoch(e["when"]), reverse=True)
    return entries[:last]


def format_feed(entries: List[Dict[str, str]]) -> List[str]:
    """Render feed entries as concise, newest-first lines (no emojis)."""
    if not entries:
        return ["No loop activity recorded yet."]
    lines = []
    for e in entries:
        when = (e.get("when") or "").replace("T", " ")[:19]
        lines.append(f"{when:<19}  [{e.get('kind', '?'):<9}] {e.get('text', '')}")
    return lines
