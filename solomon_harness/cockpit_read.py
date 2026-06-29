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
import os
import sys
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FuturesTimeoutError
from typing import Any, Callable, Dict, List, Optional, Sequence

from opentelemetry import trace
from opentelemetry.trace.propagation.tracecontext import TraceContextTextMapPropagator

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

# Per-project read outcomes for the cross-tenant fan-out (slice 1b). A clean read
# is OK; a permission failure is FORBIDDEN; a timeout or any other read failure is
# UNREACHABLE. Degraded (non-OK) projects carry no issue rows.
STATUS_OK = "OK"
STATUS_UNREACHABLE = "UNREACHABLE"
STATUS_FORBIDDEN = "FORBIDDEN"

# A FORBIDDEN swimlane carries 403 per-project semantics inside the 207 envelope.
FORBIDDEN_HTTP_STATUS = 403

# Aggregate HTTP status: 200 when every project read cleanly, else 207 Multi-Status.
AGGREGATE_OK = 200
AGGREGATE_MULTI_STATUS = 207

# The portfolio fan-out is capped so a host with many tenants cannot blow the
# p95 latency envelope (R-06): at most this many projects are read and rendered,
# the rest reported as an overflow count. The cap is on the sorted set, so the
# excluded tail is stable across loads.
MAX_PROJECTS = 25

# Bounded concurrency for the fan-out: at most this many tenants are read at once
# so the reads run in parallel without unbounded thread or connection growth.
MAX_FANOUT_WORKERS = 8

# A per-project read that blocks past this many seconds is classified UNREACHABLE
# rather than allowed to stall the fan-out (DoS mitigation, R-04).
PER_PROJECT_TIMEOUT_S = 5.0

# Read-failure messages matching one of these patterns are treated as an access
# denial (FORBIDDEN) rather than an unreachable tenant.
_PERMISSION_PATTERNS = ("permission", "forbidden", "denied", "unauthor", "not allowed")


def build_board(client: Any, project: str) -> Dict[str, Any]:
    """Group one tenant's issues into the seven ordered board columns.

    Reads every issue for the tenant via the read port's ``list_issues`` and
    buckets it by status into the fixed column order. Each column carries its
    issues and a count. ``total`` is the issue count and ``unmapped`` is the
    number of issues whose status is outside the seven columns, so the invariant
    ``total == sum(column counts) + unmapped`` holds and no issue is silently
    dropped. Read-only: it never creates or mutates a row.
    """
    carrier = {"traceparent": os.environ.get("traceparent")} if "traceparent" in os.environ else {}
    context = TraceContextTextMapPropagator().extract(carrier=carrier)
    with _tracer.start_as_current_span("cockpit.read_board", context=context) as span:
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


def _zero_columns() -> List[Dict[str, Any]]:
    """Return the seven board columns at count zero with no issues."""
    return [{"name": name, "count": 0, "issues": []} for name in BOARD_COLUMNS]


def empty_board(project: str) -> Dict[str, Any]:
    """Return the seven columns at count zero for ``project``.

    Used for an empty or unselectable tenant: every column header still renders
    with count 0 and nothing is fabricated.
    """
    return {
        "project": project,
        "columns": _zero_columns(),
        "total": 0,
        "unmapped": 0,
    }


def _ok_swimlane(result: Dict[str, Any]) -> Dict[str, Any]:
    """Build an ``OK`` swimlane from a per-project board, carrying its issues."""
    board = result["board"]
    return {
        "project": result["project"],
        "status": STATUS_OK,
        "columns": board["columns"],
        "total": board["total"],
        "unmapped": board["unmapped"],
    }


def _degraded_swimlane(result: Dict[str, Any]) -> Dict[str, Any]:
    """Build a degraded swimlane that carries its status and no issue rows.

    Both UNREACHABLE and FORBIDDEN render the seven column headers at count 0 so
    the lane is visible, but neither carries any issue data (information
    disclosure mitigation). FORBIDDEN additionally stamps the per-project 403.
    """
    swimlane = {
        "project": result["project"],
        "status": result["status"],
        "columns": _zero_columns(),
        "total": 0,
        "unmapped": 0,
    }
    if result["status"] == STATUS_FORBIDDEN:
        swimlane["httpStatus"] = FORBIDDEN_HTTP_STATUS
    return swimlane


def _swimlane(result: Dict[str, Any]) -> Dict[str, Any]:
    """Build the swimlane for one per-project outcome, OK or degraded."""
    if result["status"] == STATUS_OK:
        return _ok_swimlane(result)
    return _degraded_swimlane(result)


def _portfolio_columns(swimlanes: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Sum the seven column counts across swimlanes, keeping the fixed order.

    Degraded swimlanes carry zero-count columns, so they contribute nothing to
    the portfolio totals by construction; only ``OK`` rows move the counts.
    """
    counts = {name: 0 for name in BOARD_COLUMNS}
    for swimlane in swimlanes:
        for column in swimlane["columns"]:
            counts[column["name"]] += column["count"]
    return [{"name": name, "count": counts[name]} for name in BOARD_COLUMNS]


def _assert_reconciles(total: int, columns: List[Dict[str, Any]], unmapped: int) -> None:
    """Guard the portfolio reconciliation invariant against a future regression."""
    column_total = sum(column["count"] for column in columns)
    if total != column_total + unmapped:
        raise RuntimeError(
            "portfolio reconciliation failed: "
            f"total={total} columns={column_total} unmapped={unmapped}"
        )


def compose_portfolio(results: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    """Compose per-project read outcomes into one portfolio board (pure).

    Builds one swimlane per project in the given order, each carrying only its
    own issues, so cross-tenant isolation holds by construction (nothing is
    joined or merged). Sums the seven portfolio column counts and the portfolio
    ``total``/``unmapped`` across swimlanes, asserts the reconciliation invariant
    (``total == sum(column counts) + unmapped``), and sets ``aggregateStatus`` to
    200 when every project is ``OK`` else 207 (Multi-Status). No threads or I/O.
    """
    swimlanes = [_swimlane(result) for result in results]
    columns = _portfolio_columns(swimlanes)
    total = sum(swimlane["total"] for swimlane in swimlanes)
    unmapped = sum(swimlane["unmapped"] for swimlane in swimlanes)
    _assert_reconciles(total, columns, unmapped)
    aggregate_status = (
        AGGREGATE_OK
        if all(result["status"] == STATUS_OK for result in results)
        else AGGREGATE_MULTI_STATUS
    )
    return {
        "swimlanes": swimlanes,
        "columns": columns,
        "total": total,
        "unmapped": unmapped,
        "aggregateStatus": aggregate_status,
    }


def _is_permission_failure(error: Exception) -> bool:
    """Report whether a read failure reads as an access denial (FORBIDDEN)."""
    message = str(error).lower()
    return any(pattern in message for pattern in _PERMISSION_PATTERNS)


def _bind_and_build(client: Any, project: str) -> Dict[str, Any]:
    """Bind the tenant on the read port, then group its board."""
    client.use_tenant(project)
    return build_board(client, project)


def _read_board_within_timeout(
    client: Any, project: str, timeout: float
) -> Dict[str, Any]:
    """Run one tenant's bind-and-read in a worker, abandoning it past ``timeout``.

    A hung tenant must classify as UNREACHABLE rather than block the fan-out, so
    the blocking read runs in a one-shot worker and a deadline-exceeded result
    raises ``TimeoutError`` instead of waiting. The worker is not joined on
    timeout (the tenant is already degraded); the bounded fan-out pool and the
    25-project cap keep the number of abandoned workers small.
    """
    pool = ThreadPoolExecutor(max_workers=1)
    future = pool.submit(_bind_and_build, client, project)
    try:
        return future.result(timeout=timeout)
    finally:
        pool.shutdown(wait=False)


def read_tenant_swimlane(
    project: str,
    client_factory: Callable[[], Any],
    timeout: float = PER_PROJECT_TIMEOUT_S,
) -> Dict[str, Any]:
    """Read exactly one tenant and classify the outcome (OK/FORBIDDEN/UNREACHABLE).

    Owns its own per-tenant client from ``client_factory`` (a fresh
    ``DatabaseClient`` bound to that one tenant via ``use_tenant``), so no
    connection is shared or rebound across the fan-out and per-tenant isolation
    (ADR-0002) holds by construction. A clean read returns ``OK`` with the grouped
    board; a ``PermissionError`` or a permission-pattern read failure returns
    ``FORBIDDEN`` with no data; a read past ``timeout`` or any other read failure
    returns ``UNREACHABLE`` with no data. The result is the ``compose_portfolio``
    input element.
    """
    client = client_factory()
    try:
        board = _read_board_within_timeout(client, project, timeout)
        return {"project": project, "status": STATUS_OK, "board": board}
    except PermissionError:
        return {"project": project, "status": STATUS_FORBIDDEN, "board": None}
    except FuturesTimeoutError:
        return {"project": project, "status": STATUS_UNREACHABLE, "board": None}
    except Exception as error:
        status = STATUS_FORBIDDEN if _is_permission_failure(error) else STATUS_UNREACHABLE
        return {"project": project, "status": status, "board": None}
    finally:
        client.close()


def discover_projects(list_databases: Callable[[], List[str]]) -> List[str]:
    """List the harness-managed tenants on this machine, sorted, read-only.

    Takes the read port's tenant lister (e.g. ``DatabaseClient.list_databases``)
    rather than a concrete client, so the composer never names infrastructure and
    the discovery source can be swapped without touching this code. It only reads:
    nothing is created and no tenant is seeded.
    """
    return sorted(list_databases())


def board_payload(
    project: Optional[str] = None,
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
        selected = project
        if not selected:
            selected = available[0] if available else ""

        if not selected or selected not in available:
            payload = empty_board(selected)
            payload["found"] = False
            payload["projects"] = available
            payload["selectedProject"] = selected
            return payload

        client.use_tenant(selected)
        payload = build_board(client, selected)
        payload["found"] = True
        payload["projects"] = available
        payload["selectedProject"] = selected
        return payload
    finally:
        client.close()


def _discover_with(client_factory: Callable[[], Any]) -> List[str]:
    """Open one client only to discover the sorted tenant set, then close it."""
    client = client_factory()
    try:
        return discover_projects(client.list_databases)
    finally:
        client.close()


def _overflow_notice(count: int) -> Optional[str]:
    """Render the "N project(s) not shown" notice, or None when nothing spills."""
    if count <= 0:
        return None
    noun = "project" if count == 1 else "projects"
    return f"{count} {noun} not shown"


def _fan_out(
    projects: Sequence[str],
    client_factory: Callable[[], Any],
    max_workers: int,
    timeout: float,
) -> List[Dict[str, Any]]:
    """Read the projects in parallel under a bounded pool, preserving their order.

    Each project is read by ``read_tenant_swimlane`` with its own fresh client, so
    no connection is shared across workers. The results are returned in the input
    (sorted) order regardless of completion order, so the render is deterministic.
    """
    if not projects:
        return []
    results: Dict[str, Dict[str, Any]] = {}
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {
            pool.submit(read_tenant_swimlane, project, client_factory, timeout): project
            for project in projects
        }
        for future, project in futures.items():
            results[project] = future.result()
    return [results[project] for project in projects]


def portfolio_payload(
    harness_dir: Optional[str] = None,
    client_factory: Optional[Callable[[], Any]] = None,
    max_projects: int = MAX_PROJECTS,
    max_workers: int = MAX_FANOUT_WORKERS,
    timeout: float = PER_PROJECT_TIMEOUT_S,
) -> Dict[str, Any]:
    """Build the cross-tenant portfolio board by fanning out over the tenants.

    Discovers the sorted tenant set, caps it at ``max_projects`` (recording the
    overflow count and a stable notice), fans the capped set out under a bounded
    pool with a per-project read timeout, and composes the per-project outcomes
    into one portfolio board. The whole read is wrapped in a ``cockpit.portfolio``
    span that records the per-project statuses for the audit trace. Read-only:
    every tenant is read through the read port and nothing is joined or written.

    ``client_factory`` lets a test inject fakes; by default each call opens a
    fresh ``DatabaseClient`` for the harness directory.
    """
    factory = client_factory or (lambda: DatabaseClient(harness_dir=harness_dir))
    with _tracer.start_as_current_span("cockpit.portfolio") as span:
        available = _discover_with(factory)
        shown = list(available[:max_projects])
        overflow_count = len(available) - len(shown)

        results = _fan_out(shown, factory, max_workers, timeout)
        payload = compose_portfolio(results)
        payload["overflow"] = overflow_count
        payload["notice"] = _overflow_notice(overflow_count)

        span.set_attribute("cockpit.project_count", len(available))
        span.set_attribute("cockpit.shown_count", len(shown))
        span.set_attribute("cockpit.overflow_count", overflow_count)
        span.set_attribute("cockpit.aggregate_status", payload["aggregateStatus"])
        span.set_attribute(
            "cockpit.project_statuses",
            [f"{s['project']}:{s['status']}" for s in payload["swimlanes"]],
        )
        return payload


def main(argv: Optional[Sequence[str]] = None) -> int:
    """JSON CLI for the Node-to-Python read bridge.

    ``projects`` prints the discovered tenants; ``board --project <p>`` prints the
    board for one tenant; ``portfolio`` prints the cross-tenant aggregate board.
    Output is JSON on stdout so the Next route can parse it.
    """
    if "traceparent" in os.environ:
        from opentelemetry import trace
        from opentelemetry.trace import ProxyTracerProvider
        try:
            if isinstance(trace.get_tracer_provider(), ProxyTracerProvider):
                from opentelemetry.sdk.trace import TracerProvider
                from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter
                provider = TracerProvider()
                processor = BatchSpanProcessor(ConsoleSpanExporter(out=sys.stderr))
                provider.add_span_processor(processor)
                trace.set_tracer_provider(provider)
        except Exception:
            pass

    parser = argparse.ArgumentParser(prog="solomon_harness.cockpit_read")
    parser.add_argument("--harness-dir", default=None, help="harness directory path")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("projects", help="list the harness-managed tenants")
    board_parser = sub.add_parser("board", help="render one tenant's board")
    board_parser.add_argument("--project", default=None, help="the tenant/project name")
    sub.add_parser("portfolio", help="render the cross-tenant portfolio board")
    args = parser.parse_args(argv)

    if args.command == "projects":
        client = DatabaseClient(harness_dir=args.harness_dir)
        try:
            print(json.dumps(discover_projects(client.list_databases)))
        finally:
            client.close()
    elif args.command == "board":
        print(json.dumps(board_payload(args.project, harness_dir=args.harness_dir)))
    elif args.command == "portfolio":
        print(json.dumps(portfolio_payload(harness_dir=args.harness_dir)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
