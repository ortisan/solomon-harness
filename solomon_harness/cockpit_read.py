"""Read-only composer for the delivery cockpit (slice 1a).

This module is the in-process read side of the cockpit. It reads one tenant
through the ADR-0002 read port (``DatabaseClient``) and groups that tenant's
issues into the seven ordered delivery-board columns. It performs no writes:
no auto-seed, no status write-back. The Next.js route is a thin driving adapter
that bridges to this composer over a non-shell subprocess; the cross-tenant
aggregation and the 207/403 partial-render contract are slice 1b (#59).
"""

import argparse
import json
import sys
from typing import Any, Callable, Dict, List, Optional, Sequence

from opentelemetry import trace

from solomon_harness.tools.database_client import DatabaseClient

_tracer = trace.get_tracer("solomon_harness.cockpit_read")

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
    with _tracer.start_as_current_span("cockpit.read_board") as span:
        span.set_attribute("cockpit.project", project)
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

        span.set_attribute("cockpit.total_issues", len(issues))
        span.set_attribute("cockpit.unmapped_issues", len(issues) - mapped)
        return {
            "project": project,
            "columns": columns,
            "total": len(issues),
            "unmapped": len(issues) - mapped,
        }


def empty_board(project: str) -> Dict[str, Any]:
    """Return the seven columns at count zero for ``project``.

    Used for an empty or unselectable tenant: every column header still renders
    with count 0 and nothing is fabricated.
    """
    return {
        "project": project,
        "columns": [{"name": n, "count": 0, "issues": []} for n in BOARD_COLUMNS],
        "total": 0,
        "unmapped": 0,
    }


def discover_projects(list_databases: Callable[[], List[str]]) -> List[str]:
    """List the harness-managed tenants on this machine, sorted, read-only.

    Takes the read port's tenant lister (e.g. ``DatabaseClient.list_databases``)
    rather than a concrete client, so the composer never names infrastructure and
    the discovery source can be swapped without touching this code. It only reads:
    nothing is created and no tenant is seeded.
    """
    return sorted(list_databases())


def board_payload(
    project: str,
    harness_dir: Optional[str] = None,
    client_factory: Optional[Callable[[], Any]] = None,
) -> Dict[str, Any]:
    """Build the board for ``project`` after validating it against discovery.

    The requested project is checked against the discovered-tenant allowlist
    before any board is read. An unknown (or shell-injection) value is never run
    as a command: it yields an empty board flagged ``found: false`` so the driving
    adapter can return 404. A known tenant binds that exact tenant on the read
    port via ``use_tenant`` before the read, so the board is keyed to the selected
    project and never the host tenant, then yields the grouped board, ``found: true``.

    ``client_factory`` lets a test inject a fake read port; by default it opens a
    real ``DatabaseClient`` for the harness directory.
    """
    factory = client_factory or (lambda: DatabaseClient(harness_dir=harness_dir))
    client = factory()
    try:
        available = discover_projects(client.list_databases)
        if project not in available:
            payload = empty_board(project)
            payload["found"] = False
            return payload
        client.use_tenant(project)
        payload = build_board(client, project)
        payload["found"] = True
        return payload
    finally:
        client.close()


def main(argv: Optional[Sequence[str]] = None) -> int:
    """JSON CLI for the Node-to-Python read bridge.

    ``projects`` prints the discovered tenants; ``board --project <p>`` prints the
    board for one tenant. Output is JSON on stdout so the Next route can parse it.
    """
    parser = argparse.ArgumentParser(prog="solomon_harness.cockpit_read")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("projects", help="list the harness-managed tenants")
    board_parser = sub.add_parser("board", help="render one tenant's board")
    board_parser.add_argument("--project", required=True)
    args = parser.parse_args(argv)

    if args.command == "projects":
        client = DatabaseClient()
        try:
            print(json.dumps(discover_projects(client.list_databases)))
        finally:
            client.close()
    elif args.command == "board":
        print(json.dumps(board_payload(args.project)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
