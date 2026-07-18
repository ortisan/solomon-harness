"""Cross-round review finding dedup (#341 package 15).

A review finding is keyed so a later round can recognise one it has already
seen: a finding a human marked ``invalid``, or one already ``resolved``, is not
re-flagged unless the code at its location actually changed. The key is stable
across small line drift (the line is bucketed) and case, so re-running a review
on an unchanged file produces the same key.
"""

import hashlib
import os
import re
from typing import Iterable, Optional

LIFECYCLE_STATES = ("pending", "valid", "invalid", "resolved")
_LINE_BUCKET = 5


def _normalize_category(category: Optional[str]) -> str:
    text = (category or "").strip().lower()
    return re.sub(r"[^a-z0-9]+", "-", text).strip("-") or "uncategorized"


def finding_dedup_key(file: Optional[str], line: Optional[int], category: Optional[str]) -> str:
    """A stable key for a review finding: file + bucketed line + category.

    The line is bucketed into a small window so a finding that drifts by a few
    lines between rounds still keys the same; the file path is normalised and
    the category slugified. Returns a short hex digest.
    """
    path = os.path.normpath((file or "").strip()) if file else "unknown"
    try:
        bucket = (int(line) // _LINE_BUCKET) if line is not None else -1
    except (TypeError, ValueError):
        bucket = -1
    raw = f"{path}:{bucket}:{_normalize_category(category)}"
    return hashlib.blake2b(raw.encode("utf-8"), digest_size=8).hexdigest()


def is_suppressed(state: Optional[str]) -> bool:
    """True when a finding in this lifecycle state should not be re-flagged
    (it was triaged away or already fixed) absent a code change at its location.
    """
    return str(state or "").strip().lower() in ("invalid", "resolved")


def new_findings(
    current_keys: Iterable[str], prior_by_key: dict
) -> list:
    """The subset of ``current_keys`` that is genuinely new this round: a key
    unseen before, or one whose prior finding is not in a suppressed state.
    """
    fresh = []
    for key in current_keys:
        prior = prior_by_key.get(key)
        if prior is None or not is_suppressed(prior.get("lifecycle")):
            fresh.append(key)
    return fresh
