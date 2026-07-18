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
import threading
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FuturesTimeoutError
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence, Tuple

from opentelemetry import trace
from opentelemetry.trace.propagation.tracecontext import TraceContextTextMapPropagator

from solomon_harness.tools.database_client import (
    BOARD_COLUMNS,
    STATUS_DISPLAY_COLUMNS,
    DatabaseClient,
    normalize_status,
    person_key_or_unassigned,
)

_tracer = trace.get_tracer("solomon_harness.cockpit_read")

# The canonical delivery-board columns (Ideas -> Backlog -> Ready -> In Progress ->
# Code Review -> QA -> Done) are defined once in the memory adapter and imported
# here, so this read side and the board adapter share one source of truth
# (ADR-0006). An issue whose status maps to none of these is not coerced into a
# column; it is counted in ``unmapped`` so nothing is dropped.

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


def _card(issue: Dict[str, Any]) -> Dict[str, Any]:
    """Copy an issue row into a swimlane card carrying its canonical person key.

    The card is a copy so the source row is never mutated, and ``personKey`` reads
    the stored ``assignee`` through ``person_key_or_unassigned`` (ADR-0012): a null
    assignee resolves to the reserved ``unassigned`` pseudo-key, and the key is
    never re-derived from email/login here (that happened at the #118 capture seam).
    """
    return {**issue, "personKey": person_key_or_unassigned(issue.get("assignee"))}


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

        # Resolve each stored status to a display column through the shared
        # vocabulary (ADR-0006): a canonical token (in_progress, closed) and the
        # legacy display value (In Progress, Done) both normalize to the same
        # column, so delivered work no longer falls into unmapped.
        by_column: Dict[str, List[Dict[str, Any]]] = {name: [] for name in BOARD_COLUMNS}
        mapped = 0
        for issue in issues:
            status = normalize_status(issue.get("status"))
            column = STATUS_DISPLAY_COLUMNS.get(status) if status else None
            if column in by_column:
                by_column[column].append(_card(issue))
                mapped += 1

        columns: List[Dict[str, Any]] = [
            {"name": name, "count": len(by_column[name]), "issues": by_column[name]}
            for name in BOARD_COLUMNS
        ]

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


def _filter_lane(lane: Dict[str, Any], person_key: str) -> Dict[str, Any]:
    """Narrow one OK swimlane to the cards whose personKey matches (pure).

    Keeps only the matching card in each column, recomputes that column's count
    and the lane total, and zeroes ``unmapped``: an unmapped issue carries no
    card and so cannot be attributed to a person. Because it only removes cards
    already in this lane, it cannot pull in another tenant's row.
    """
    columns: List[Dict[str, Any]] = []
    for column in lane["columns"]:
        kept = [card for card in column["issues"] if card.get("personKey") == person_key]
        columns.append({"name": column["name"], "count": len(kept), "issues": kept})
    total = sum(column["count"] for column in columns)
    return {**lane, "columns": columns, "total": total, "unmapped": 0}


def filter_portfolio(payload: Dict[str, Any], person_key: str) -> Dict[str, Any]:
    """Narrow a composed portfolio payload to one person key (pure).

    Operates on the already-composed, per-tenant-isolated payload, so it can only
    REMOVE non-matching cards within each lane — it never joins lanes, and tenant
    isolation (ADR-0002 compose-never-join) holds by construction. Within each OK
    swimlane it keeps the cards whose surfaced ``personKey`` matches and re-sums
    that lane; it keeps one swimlane per project (an unmatched project becomes a
    present-but-empty lane, never hidden) and leaves degraded (UNREACHABLE/
    FORBIDDEN) lanes untouched, since they already carry no rows. It re-sums the
    seven portfolio column counts and the portfolio total over the matched set,
    re-asserts the reconciliation invariant, stamps ``filteredUser``, and passes
    ``aggregateStatus``/``overflow``/``notice`` straight through.
    """
    swimlanes = [
        _filter_lane(lane, person_key) if lane["status"] == STATUS_OK else lane
        for lane in payload["swimlanes"]
    ]
    columns = _portfolio_columns(swimlanes)
    total = sum(lane["total"] for lane in swimlanes)
    unmapped = sum(lane["unmapped"] for lane in swimlanes)
    _assert_reconciles(total, columns, unmapped)
    return {
        **payload,
        "swimlanes": swimlanes,
        "columns": columns,
        "total": total,
        "unmapped": unmapped,
        "filteredUser": person_key,
    }


# ---------------------------------------------------------------------------
# Per-user velocity (issue #55, slice 3a; ADR-0002 amendment).
#
# Velocity reads board_history, the real board transitions captured by
# github.record_transition, not the created_at approximation. Each issue's Done
# transition (the entry whose column maps to the Done display column) carries a
# naive local-time ISO entered_at; a delivery counts when that timestamp falls
# inside the selected window. Counts are keyed on the stored canonical person key
# (ADR-0012) and never re-derived. compose_velocity sums the per-person counts
# across tenants (compose-never-join): a tenant's rows never meet another's.
# ---------------------------------------------------------------------------

# The delivery-board Done display column. A board_history entry or an issue
# status counts as delivered only when it maps to this column.
DONE_COLUMN = "Done"

# The memory-key prefix github.record_transition writes the per-card timeline
# under: board_history:<github_id> -> JSON list of {column, entered_at}.
BOARD_HISTORY_PREFIX = "board_history:"


def _is_done(value: Optional[str]) -> bool:
    """Report whether a stored status or transition column maps to Done.

    Routes the value through the shared status vocabulary (ADR-0006) so every
    spelling of delivered (closed, done, Done) resolves to the one Done display
    column. A null value is never delivered.
    """
    if value is None:
        return False
    normalized = normalize_status(value)
    if normalized is None:
        return False
    return STATUS_DISPLAY_COLUMNS.get(normalized) == DONE_COLUMN


def _parse_naive(entered_at: Any) -> Optional[datetime]:
    """Parse a board_history entered_at into a naive datetime, or None.

    entered_at is a naive local-time ISO string (no offset; see
    record_transition), so it parses onto the same clock basis the window bounds
    use. A non-string or unparseable value yields None so a malformed entry is
    skipped, never crashing the read. A timezone-tagged value (not the contract,
    but defended against) is coerced to naive so the comparison stays single-basis.
    """
    if not isinstance(entered_at, str):
        return None
    try:
        parsed = datetime.fromisoformat(entered_at)
    except ValueError:
        return None
    return parsed.replace(tzinfo=None) if parsed.tzinfo is not None else parsed


def _in_window(entered: datetime, now: datetime, days: int) -> bool:
    """Report whether entered falls inside the [now - days, now] window.

    Both bounds and entered are naive datetimes compared on one clock basis. The
    lower bound is inclusive, so a Done exactly at now - days counts.
    """
    return now - timedelta(days=days) <= entered <= now


def _parse_board_history(raw: Optional[str]) -> List[Dict[str, Any]]:
    """Parse one issue's board_history JSON string, defensively.

    Returns an empty list for a missing value or one that is not a JSON list,
    so a thin or malformed history degrades to "no tracked transitions" rather
    than raising.
    """
    if not raw:
        return []
    try:
        history = json.loads(raw)
    except (ValueError, TypeError):
        return []
    return history if isinstance(history, list) else []


def _load_transition_histories(
    client: Any, github_ids: Sequence[str]
) -> Dict[str, List[Dict[str, Any]]]:
    """Read the first-class transitions rows, adapted to the history-entry shape.

    Each transitions row becomes ``{column: to_status, entered_at}`` so every
    downstream consumer (``_latest_done_entered_at``, ``_is_done``) works
    unchanged on either source. Best-effort: a read failure degrades to an
    empty dict so the caller falls back to the legacy board_history keys — the
    cockpit renders a partial figure rather than failing the read (ADR-0002).
    """
    try:
        grouped = client.get_status_transitions(github_ids)
    except Exception:
        return {}
    return {
        gid: [
            {"column": row.get("to_status"), "entered_at": row.get("entered_at")}
            for row in rows
        ]
        for gid, rows in grouped.items()
        if rows
    }


def _load_board_histories(
    client: Any, github_ids: Iterable[Optional[str]]
) -> Dict[str, List[Dict[str, Any]]]:
    """Bulk-read each issue's board timeline in one round trip per source.

    Prefers the first-class transitions table (ADR-0016) per issue; only the
    ids it does not cover are read from the legacy ``board_history:<github_id>``
    keys through a single ``get_memory_bulk`` call (no N+1), so old cards keep
    their history while new moves come from the indexed table. Returns a dict
    keyed by github_id; an id with no timeline in either source is simply
    absent, so a caller's ``.get(id, [])`` degrades exactly like before.
    """
    ids = sorted({gid for gid in github_ids if gid})
    if not ids:
        return {}
    histories: Dict[str, List[Dict[str, Any]]] = _load_transition_histories(client, ids)
    legacy_ids = [gid for gid in ids if gid not in histories]
    if not legacy_ids:
        return histories
    raw_by_key = client.get_memory_bulk(
        [f"{BOARD_HISTORY_PREFIX}{gid}" for gid in legacy_ids]
    )
    for gid in legacy_ids:
        history = _parse_board_history(raw_by_key.get(f"{BOARD_HISTORY_PREFIX}{gid}"))
        if history:
            histories[gid] = history
    return histories


def _latest_done_entered_at(history: List[Dict[str, Any]]) -> Optional[datetime]:
    """Return the latest Done-transition timestamp in a board_history, or None.

    Takes the max entered_at across the entries whose column maps to Done, so a
    card delivered, reopened, and re-delivered keys on its latest delivery. None
    when the card has no parseable Done transition at all.
    """
    done_times = [
        parsed
        for entry in history
        if isinstance(entry, dict) and _is_done(entry.get("column"))
        for parsed in (_parse_naive(entry.get("entered_at")),)
        if parsed is not None
    ]
    return max(done_times) if done_times else None


def count_tenant_velocity(
    client: Any,
    project: str,
    now: datetime,
    days: int,
    cancel_event: Optional[threading.Event] = None,
) -> Dict[str, Dict[str, Any]]:
    """Count one tenant's in-window deliveries per canonical person key (read-only).

    Reads every issue's ``board_history`` through one ``get_memory_bulk`` call
    (``_load_board_histories``) rather than one read per issue, so the tenant's
    history read costs a single round trip regardless of issue count (no N+1).
    For each issue, resolves the subject through ``person_key_or_unassigned``
    over the stored assignee (ADR-0012; a null assignee buckets under
    ``unassigned``). An issue whose latest Done transition entered the
    ``[now - days, now]`` window adds one to that person's ``count`` and its
    timestamp to ``doneAt`` (the per-person in-window set slice 3b buckets per
    day). An issue currently in the Done column with no tracked Done transition is
    surfaced under ``excluded`` (the coverage affordance) and never counted, so
    the number is auditable rather than silently low. Every assignee is a present
    subject, so a zero-throughput person still has a row. The return is keyed by
    person; ``compose_velocity`` is handed these counts, never rows.

    ``cancel_event``, when given, is checked between issues so a caller that has
    already given up on this read (its bounding timeout elapsed) gets an
    abandoned worker that actually stops instead of running the whole tenant to
    completion after its SLA was already reported (see ``_classify_tenant_read``).
    """
    counts: Dict[str, Dict[str, Any]] = {}
    issues = client.list_issues()
    histories = _load_board_histories(client, (issue.get("github_id") for issue in issues))
    for issue in issues:
        if cancel_event is not None and cancel_event.is_set():
            break
        person = person_key_or_unassigned(issue.get("assignee"))
        bucket = counts.setdefault(person, {"count": 0, "excluded": 0, "doneAt": []})
        done_at = _latest_done_entered_at(histories.get(issue.get("github_id") or "", []))
        if done_at is not None and _in_window(done_at, now, days):
            bucket["count"] += 1
            bucket["doneAt"].append(done_at.isoformat(timespec="seconds"))
        elif done_at is None and _is_done(issue.get("status")):
            bucket["excluded"] += 1
    return counts


def compose_velocity(tenant_results: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    """Compose per-tenant velocity counts into one per-person payload (pure).

    Sums each person's count across the OK tenants — compose-never-join: it is
    handed per-person counts tagged with their tenant, never issue rows, so a
    tenant's rows never meet another's and isolation holds by construction. One
    row per person carries the summed count, the per-tenant breakdown (only the
    tenants where the person delivered), the summed ``excluded`` coverage gap, and
    the aggregated in-window ``doneAt`` set (slice 3b). A degraded (non-OK) tenant
    carries no counts and moves no figure, but because it could have held
    deliveries for any person, every row is flagged ``partial`` with the degraded
    tenant name(s) and ``aggregateStatus`` becomes 207: the figure is the
    reachable subtotal, never presented as complete. Rows are sorted by person key
    for a deterministic render.
    """
    degraded = [result["project"] for result in tenant_results if result["status"] != STATUS_OK]
    ok_results = [result for result in tenant_results if result["status"] == STATUS_OK]
    people = sorted({person for result in ok_results for person in result["velocity"]})

    rows: List[Dict[str, Any]] = []
    for person in people:
        per_tenant: Dict[str, int] = {}
        count = 0
        excluded = 0
        done_at: List[str] = []
        for result in ok_results:
            figures = result["velocity"].get(person)
            if figures is None:
                continue
            if figures["count"]:
                per_tenant[result["project"]] = figures["count"]
            count += figures["count"]
            excluded += figures["excluded"]
            done_at.extend(figures["doneAt"])
        rows.append(
            {
                "personKey": person,
                "count": count,
                "perTenant": per_tenant,
                "excluded": excluded,
                "doneAt": sorted(done_at),
                "partial": bool(degraded),
                "partialTenants": list(degraded),
            }
        )

    return {
        "rows": rows,
        "aggregateStatus": AGGREGATE_OK if not degraded else AGGREGATE_MULTI_STATUS,
        "degraded": degraded,
    }


def _is_permission_failure(error: Exception) -> bool:
    """Report whether a read failure reads as an access denial (FORBIDDEN)."""
    message = str(error).lower()
    return any(pattern in message for pattern in _PERMISSION_PATTERNS)


def _read_tenant_board(
    client_factory: Callable[[], Any], project: str
) -> Dict[str, Any]:
    """Own one tenant's whole read lifecycle inside the timed worker.

    Creating the client (``client_factory``), binding the tenant (``use_tenant``),
    and reading its board (``build_board``) all run here, so a connect-phase
    failure or hang is bounded by the per-project timeout that wraps this worker
    rather than propagating out to collapse the fan-out. The worker owns its
    client and closes it in a ``finally``, so even an abandoned (timed-out) worker
    closes its own connection when the read finally returns or errors, and the
    outer path never closes a client mid-read (no close-during-read race).
    """
    client = client_factory()
    try:
        client.use_tenant(project)
        return build_board(client, project)
    finally:
        client.close()


def _classify_tenant_read(
    worker: Callable[[threading.Event], Any], timeout: float
) -> Tuple[str, Any]:
    """Run one per-tenant read worker bounded by ``timeout`` and classify it.

    Returns ``(status, value)``: ``(OK, value)`` on a clean read; ``(FORBIDDEN,
    None)`` on a ``PermissionError`` or a permission-pattern failure (at connect
    or read); ``(UNREACHABLE, None)`` on a read past ``timeout`` or any other
    failure. The worker owns and closes its own client, so a timed-out worker is
    abandoned (not joined) and the outer path never closes a client mid-read.
    Shared by every per-tenant read (board, velocity) so the bounding,
    classification, and close discipline live in one place.

    ``worker`` receives a ``threading.Event`` that this function sets in its
    ``finally`` block, the instant it stops waiting on the worker (whether that
    is a timeout, a raised error, or a clean return). ``pool.shutdown(wait=False)``
    alone does not stop a still-running worker thread -- it keeps executing past
    its own reported SLA and, across many tenants, those abandoned workers can
    pile up. A worker with a checkpointed loop (e.g. ``count_tenant_velocity``
    iterating issues) that checks this event stops at its next checkpoint
    instead. This is cooperative, not preemptive: a worker blocked in an
    uninterruptible call only stops once that call returns, but any per-item
    loop stops promptly.
    """
    cancel_event = threading.Event()
    pool = ThreadPoolExecutor(max_workers=1)
    try:
        value = pool.submit(worker, cancel_event).result(timeout=timeout)
    except PermissionError:
        return STATUS_FORBIDDEN, None
    except FuturesTimeoutError:
        return STATUS_UNREACHABLE, None
    except Exception as error:
        return (STATUS_FORBIDDEN if _is_permission_failure(error) else STATUS_UNREACHABLE), None
    else:
        return STATUS_OK, value
    finally:
        cancel_event.set()
        pool.shutdown(wait=False)


def read_tenant_swimlane(
    project: str,
    client_factory: Callable[[], Any],
    timeout: float = PER_PROJECT_TIMEOUT_S,
) -> Dict[str, Any]:
    """Read exactly one tenant and classify the outcome (OK/FORBIDDEN/UNREACHABLE).

    Runs the entire per-tenant lifecycle (connect, bind, read, close) inside a
    single one-shot worker bounded by ``timeout``, so per-tenant isolation
    (ADR-0002) holds by construction (a fresh ``DatabaseClient`` bound to exactly
    one tenant via ``use_tenant``) and every phase, connect included, is bounded
    by the per-project deadline. A clean read returns ``OK`` with the grouped
    board; a ``PermissionError`` or a permission-pattern failure (at connect or
    read) returns ``FORBIDDEN`` with no data; a read past ``timeout`` or any other
    failure returns ``UNREACHABLE`` with no data. The worker owns and closes its
    own client, so a timed-out worker is abandoned (not joined) and closes itself
    when its read returns; the outer path never closes a client mid-read. The
    result is the ``compose_portfolio`` input element.
    """
    status, board = _classify_tenant_read(
        lambda cancel_event: _read_tenant_board(client_factory, project), timeout
    )
    return {"project": project, "status": status, "board": board}


def _read_tenant_velocity_counts(
    client_factory: Callable[[], Any],
    project: str,
    now: datetime,
    days: int,
    cancel_event: threading.Event,
) -> Dict[str, Dict[str, Any]]:
    """Own one tenant's whole velocity read inside the timed worker.

    Mirrors ``_read_tenant_board``: create the client, bind the tenant, count its
    in-window deliveries, and close in a ``finally``, so a connect-phase failure
    or hang is bounded by the per-project timeout and the worker always closes its
    own client. ``cancel_event`` is threaded through to ``count_tenant_velocity``
    so an abandoned worker's per-issue loop stops at its next checkpoint instead
    of running to completion after ``_classify_tenant_read`` has already
    reported the timeout.
    """
    client = client_factory()
    try:
        client.use_tenant(project)
        return count_tenant_velocity(client, project, now, days, cancel_event)
    finally:
        client.close()


def read_tenant_velocity(
    project: str,
    client_factory: Callable[[], Any],
    now: datetime,
    days: int,
    timeout: float = PER_PROJECT_TIMEOUT_S,
) -> Dict[str, Any]:
    """Read one tenant's velocity counts and classify the outcome.

    Mirrors ``read_tenant_swimlane``: the entire per-tenant lifecycle runs inside
    a single bounded worker, so per-tenant isolation (ADR-0002) holds by
    construction. A clean read returns ``OK`` with the per-person counts; a
    permission failure returns ``FORBIDDEN``; a timeout or any other failure
    returns ``UNREACHABLE``. A degraded result carries no counts (``velocity``
    is ``None``). The result is the ``compose_velocity`` input element.
    """
    status, velocity = _classify_tenant_read(
        lambda cancel_event: _read_tenant_velocity_counts(
            client_factory, project, now, days, cancel_event
        ),
        timeout,
    )
    return {"project": project, "status": status, "velocity": velocity}


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
    read_one: Callable[[str], Dict[str, Any]],
    max_workers: int,
) -> List[Dict[str, Any]]:
    """Read the projects in parallel under a bounded pool, preserving their order.

    Each project is read by ``read_one`` (the board or velocity per-tenant read),
    which opens its own fresh client, so no connection is shared across workers.
    The results are returned in the input (sorted) order regardless of completion
    order, so the render is deterministic. This owns only the bounded parallelism;
    which per-tenant read runs is the caller's choice.
    """
    if not projects:
        return []
    results: Dict[str, Dict[str, Any]] = {}
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {pool.submit(read_one, project): project for project in projects}
        for future, project in futures.items():
            results[project] = future.result()
    return [results[project] for project in projects]


def portfolio_payload(
    harness_dir: Optional[str] = None,
    client_factory: Optional[Callable[[], Any]] = None,
    max_projects: int = MAX_PROJECTS,
    max_workers: int = MAX_FANOUT_WORKERS,
    timeout: float = PER_PROJECT_TIMEOUT_S,
    person: Optional[str] = None,
) -> Dict[str, Any]:
    """Build the cross-tenant portfolio board by fanning out over the tenants.

    Discovers the sorted tenant set, caps it at ``max_projects`` (recording the
    overflow count and a stable notice), fans the capped set out under a bounded
    pool with a per-project read timeout, and composes the per-project outcomes
    into one portfolio board. When ``person`` is given, the composed payload is
    narrowed to that person key through ``filter_portfolio`` (server-side, so a
    non-matching tenant's rows never reach the wire); a falsy ``person`` (``None``
    or ``""``) is a no-op, so every existing caller is unchanged. The whole read
    is wrapped in a
    ``cockpit.portfolio`` span that records the per-project statuses for the audit
    trace. Read-only: every tenant is read through the read port and nothing is
    joined or written.

    ``client_factory`` lets a test inject fakes; by default each call opens a
    fresh ``DatabaseClient`` for the harness directory.
    """
    factory = client_factory or (lambda: DatabaseClient(harness_dir=harness_dir))
    with _tracer.start_as_current_span("cockpit.portfolio") as span:
        available = _discover_with(factory)
        shown = list(available[:max_projects])
        overflow_count = len(available) - len(shown)

        results = _fan_out(
            shown,
            lambda project: read_tenant_swimlane(project, factory, timeout),
            max_workers,
        )
        payload = compose_portfolio(results)
        payload["overflow"] = overflow_count
        payload["notice"] = _overflow_notice(overflow_count)
        # A falsy person (None or "") is a no-op, matching the route/CLI that map
        # a falsy filter value to no narrowing; only a real key narrows the board.
        if person:
            payload = filter_portfolio(payload, person)

        span.set_attribute("cockpit.project_count", len(available))
        span.set_attribute("cockpit.shown_count", len(shown))
        span.set_attribute("cockpit.overflow_count", overflow_count)
        span.set_attribute("cockpit.aggregate_status", payload["aggregateStatus"])
        span.set_attribute(
            "cockpit.project_statuses",
            [f"{s['project']}:{s['status']}" for s in payload["swimlanes"]],
        )
        return payload


def velocity_payload(
    window: int,
    now: Optional[datetime] = None,
    harness_dir: Optional[str] = None,
    client_factory: Optional[Callable[[], Any]] = None,
    max_projects: int = MAX_PROJECTS,
    max_workers: int = MAX_FANOUT_WORKERS,
    timeout: float = PER_PROJECT_TIMEOUT_S,
) -> Dict[str, Any]:
    """Build the cross-tenant per-user velocity payload by fanning out (read-only).

    Discovers the sorted tenant set, caps it at ``max_projects``, fans the capped
    set out under a bounded pool with a per-project read timeout, and composes the
    per-tenant per-person counts into one payload through ``compose_velocity``.
    Each tenant is read by its own fresh client bound via ``use_tenant``, so
    isolation (ADR-0002) holds by construction and the compose sums counts, never
    rows (compose-never-join). ``window`` is the selected day span (the route
    enforces the {7, 14, 30} set); ``now`` is injected so the window compute is
    deterministic in tests and defaults to the wall clock in production. The read
    is wrapped in a ``cockpit.velocity`` span for the audit trace. Read-only:
    every tenant is read through the read port and nothing is joined or written.

    ``client_factory`` lets a test inject fakes; by default each call opens a
    fresh ``DatabaseClient`` for the harness directory.
    """
    factory = client_factory or (lambda: DatabaseClient(harness_dir=harness_dir))
    # Naive UTC, matching the UTC entered_at the transition writers stamp
    # (ADR-0016): both sides of the window comparison share one clock basis.
    # Entries written by the pre-UTC local-clock writer skew by at most the
    # host offset at the window edge, decaying as that data ages out.
    current = (
        now if now is not None else datetime.now(timezone.utc).replace(tzinfo=None)
    )
    with _tracer.start_as_current_span("cockpit.velocity") as span:
        available = _discover_with(factory)
        shown = list(available[:max_projects])

        results = _fan_out(
            shown,
            lambda project: read_tenant_velocity(project, factory, current, window, timeout),
            max_workers,
        )
        payload = compose_velocity(results)
        payload["window"] = window

        span.set_attribute("cockpit.project_count", len(available))
        span.set_attribute("cockpit.shown_count", len(shown))
        span.set_attribute("cockpit.window_days", window)
        span.set_attribute("cockpit.aggregate_status", payload["aggregateStatus"])
        span.set_attribute("cockpit.degraded", list(payload["degraded"]))
        return payload


def _percentile(sorted_vals: List[float], pct: float) -> float:
    """Nearest-rank percentile of an ascending list (0.0 on empty)."""
    if not sorted_vals:
        return 0.0
    idx = min(len(sorted_vals) - 1, int(pct * len(sorted_vals)))
    return sorted_vals[idx]


def compose_delivery_metrics(client: Any, since: Optional[str] = None) -> Dict[str, Any]:
    """Compose the single-tenant delivery-metrics payload (read-only).

    Reads the ``stage_duration_seconds`` points the workflow producer emits and
    groups them by their ``stage`` tag into count/mean/p95/max seconds, then adds
    the loop-run throughput and failure rate. The loop-run aggregations are
    SurrealDB-only; on a SQLite fallback they degrade to empty rather than raising,
    so the stage-duration panel still renders.
    """
    points = client.query_metric("stage_duration_seconds", since=since, limit=10000)
    by_stage: Dict[str, List[float]] = {}
    for point in points:
        tags = point.get("tags") or {}
        stage = str(tags.get("stage", "unknown"))
        by_stage.setdefault(stage, []).append(float(point.get("value", 0.0)))
    stage_durations: Dict[str, Any] = {}
    for stage, vals in sorted(by_stage.items()):
        ordered = sorted(vals)
        stage_durations[stage] = {
            "count": len(vals),
            "mean_seconds": sum(vals) / len(vals),
            "p95_seconds": _percentile(ordered, 0.95),
            "max_seconds": ordered[-1],
        }
    try:
        throughput = client.loop_run_throughput(bucket="day", since=since)
        failure_rate = client.loop_run_failure_rate(since=since)
    except Exception:
        throughput, failure_rate = [], {"total": 0, "failures": 0, "failure_rate": 0.0}
    return {
        "stageDurations": stage_durations,
        "loopRunThroughput": throughput,
        "loopRunFailureRate": failure_rate,
    }


def metrics_payload(
    window_days: Optional[int] = None,
    now: Optional[datetime] = None,
    harness_dir: Optional[str] = None,
    client_factory: Optional[Callable[[], Any]] = None,
) -> Dict[str, Any]:
    """Single-tenant delivery-metrics payload over an optional day window.

    ``window_days`` bounds the sample to the last N days (all history when None);
    ``now`` is injected for deterministic tests. Read-only: opens one fresh client
    and closes it.
    """
    factory = client_factory or (lambda: DatabaseClient(harness_dir=harness_dir))
    since: Optional[str] = None
    if window_days is not None:
        current = now or datetime.now(timezone.utc)
        since = (current - timedelta(days=int(window_days))).isoformat()
    client = factory()
    try:
        return compose_delivery_metrics(client, since=since)
    finally:
        client.close()


def main(argv: Optional[Sequence[str]] = None) -> int:
    """JSON CLI for the Node-to-Python read bridge.

    ``projects`` prints the discovered tenants; ``board --project <p>`` prints the
    board for one tenant; ``portfolio`` prints the cross-tenant aggregate board,
    narrowed to one person key when ``--user <key>`` is given; ``velocity --window
    <days>`` prints the cross-tenant per-user velocity over the window. Output is
    JSON on stdout so the Next route can parse it.
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
    portfolio_parser = sub.add_parser(
        "portfolio", help="render the cross-tenant portfolio board"
    )
    portfolio_parser.add_argument(
        "--user", default=None, help="narrow the portfolio to one person key"
    )
    velocity_parser = sub.add_parser(
        "velocity", help="render the cross-tenant per-user velocity"
    )
    velocity_parser.add_argument(
        "--window", type=int, required=True, help="the velocity window in days"
    )
    metrics_parser = sub.add_parser(
        "metrics", help="render this tenant's delivery metrics (stage durations, loop runs)"
    )
    metrics_parser.add_argument(
        "--window", type=int, default=None, help="bound the sample to the last N days"
    )
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
        print(
            json.dumps(
                portfolio_payload(harness_dir=args.harness_dir, person=args.user)
            )
        )
    elif args.command == "velocity":
        print(
            json.dumps(velocity_payload(args.window, harness_dir=args.harness_dir))
        )
    elif args.command == "metrics":
        print(
            json.dumps(
                metrics_payload(window_days=args.window, harness_dir=args.harness_dir)
            )
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
