"""Post-hoc cost budget for autonomous loops (Phase 3).

A loop running unattended should throttle itself rather than spend without bound.
Each driven stage records its reported cost into an append-only ledger anchored at
the git common dir (so every worktree shares one budget). When the rolling daily
spend reaches the configured ceiling, the automation path degrades to report-only
— it stops drafting and merging work, but never blocks a human.

The ceiling is post-hoc by nature (the cost is known only after the engine runs),
so it reacts after a spend, not before; pair it with a per-cycle cap upstream for
a hard stop. The ledger is the record; enforcement reads it.
"""

import datetime
import json
import os
from typing import List, Optional

from solomon_harness.loop_lock import resolve_common_file


def ledger_path(workspace_root: str) -> str:
    return resolve_common_file(workspace_root, "solomon-loop-budget.jsonl", "loop-budget.jsonl")


def _today() -> str:
    return datetime.date.today().isoformat()


def record(workspace_root: str, cost_usd: float, stage: str = "", day: Optional[str] = None) -> None:
    """Append one cost entry to the budget ledger (best-effort)."""
    path = ledger_path(workspace_root)
    entry = {"day": day or _today(), "cost_usd": float(cost_usd), "stage": stage}
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")
    except OSError:
        pass


def _entries(workspace_root: str) -> List[dict]:
    path = ledger_path(workspace_root)
    out: List[dict] = []
    try:
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        out.append(json.loads(line))
                    except json.JSONDecodeError:
                        continue
    except FileNotFoundError:
        return []
    return out


def daily_spend(workspace_root: str, day: Optional[str] = None) -> float:
    day = day or _today()
    return round(sum(e.get("cost_usd", 0.0) for e in _entries(workspace_root) if e.get("day") == day), 6)


def over_ceiling(workspace_root: str, ceiling_usd: Optional[float], day: Optional[str] = None) -> bool:
    """True when today's spend has reached a positive ceiling."""
    if not ceiling_usd or ceiling_usd <= 0:
        return False
    return daily_spend(workspace_root, day) >= float(ceiling_usd)


def parse_engine_cost(stdout: str) -> Optional[float]:
    """Pull total_cost_usd from an engine's --output-format json result."""
    try:
        data = json.loads(stdout)
    except (json.JSONDecodeError, TypeError):
        return None
    if isinstance(data, dict):
        for key in ("total_cost_usd", "cost_usd", "total_cost"):
            if isinstance(data.get(key), (int, float)):
                return float(data[key])
    return None
