"""The canonical local-date helper.

``_today()`` used to be defined twice -- in loop_budget.py (datetime-based) and
in release.py (shelling out to ``date +%Y-%m-%d``) -- with identical output.
This module is the single definition both import, following the same pattern as
subprocess_env.py: one tiny stdlib-only module for a helper shared by peers.
"""

import datetime


def today_iso() -> str:
    """Local date as YYYY-MM-DD (ISO 8601)."""
    return datetime.date.today().isoformat()
