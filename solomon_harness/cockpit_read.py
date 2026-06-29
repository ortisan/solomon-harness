"""Read-only composer for the delivery cockpit (slice 1a).

This module is the in-process read side of the cockpit. It reads one tenant
through the ADR-0002 read port (``DatabaseClient``) and groups that tenant's
issues into the seven ordered delivery-board columns. It performs no writes:
no auto-seed, no status write-back. The Next.js route is a thin driving adapter
that bridges to this composer over a non-shell subprocess; the cross-tenant
aggregation and the 207/403 partial-render contract are slice 1b (#59).
"""

from typing import Any, Callable, Dict, List

# The canonical delivery-board columns, in fixed left-to-right order, matching
# docs/solomon-workflow.md (Ideas -> Backlog -> Ready -> In Progress ->
# Code Review -> QA -> Done). An issue whose status is not one of these is not
# coerced into a column; it is counted in ``unmapped`` so nothing is dropped.
BOARD_COLUMNS: List[str] = [
    "Ideas",
    "Backlog",
    "Ready",
    "In Progress",
    "Code Review",
    "QA",
    "Done",
]


def build_board(client: Any, project: str) -> Dict[str, Any]:
    """Group one tenant's issues into the seven ordered board columns.

    Reads every issue for the tenant via the read port's ``list_issues`` and
    buckets it by status into the fixed column order. Each column carries its
    issues and a count. ``total`` is the issue count and ``unmapped`` is the
    number of issues whose status is outside the seven columns, so the invariant
    ``total == sum(column counts) + unmapped`` holds and no issue is silently
    dropped. Read-only: it never creates or mutates a row.
    """
    issues = client.list_issues()

    by_status: Dict[Any, List[Dict[str, Any]]] = {}
    for issue in issues:
        by_status.setdefault(issue.get("status"), []).append(issue)

    columns: List[Dict[str, Any]] = []
    mapped = 0
    for name in BOARD_COLUMNS:
        column_issues = by_status.get(name, [])
        mapped += len(column_issues)
        columns.append(
            {"name": name, "count": len(column_issues), "issues": column_issues}
        )

    return {
        "project": project,
        "columns": columns,
        "total": len(issues),
        "unmapped": len(issues) - mapped,
    }


def discover_projects(list_databases: Callable[[], List[str]]) -> List[str]:
    """List the harness-managed tenants on this machine, sorted, read-only.

    Takes the read port's tenant lister (e.g. ``DatabaseClient.list_databases``)
    rather than a concrete client, so the composer never names infrastructure and
    the discovery source can be swapped without touching this code. It only reads:
    nothing is created and no tenant is seeded.
    """
    return sorted(list_databases())
