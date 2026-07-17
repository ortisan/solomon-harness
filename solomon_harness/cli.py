#!/usr/bin/env python3
"""Harness command line interface, shared by every agent.

Agents invoke this through a thin entrypoint that passes its own directory as
``harness_dir`` so the loop reads that agent's config, persona and memory store.
"""

import argparse
import os
import sys
from typing import Dict, Optional, List, Tuple

from solomon_harness.bootstrap import scaffold_new_agent


def _subparser(parser: argparse.ArgumentParser, name: str) -> argparse.ArgumentParser:
    """Look up a registered subcommand's parser by name, e.g. to print its help."""
    for action in parser._actions:
        if isinstance(action, argparse._SubParsersAction) and name in action.choices:
            return action.choices[name]
    raise KeyError(name)


def _subagent_description(filepath: str) -> str:
    """Return a one-line description for a generated subagent file.

    Prefers the YAML front-matter ``description:`` field, falling back to the
    first non-heading line of the body.
    """
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            lines = f.readlines()
    except OSError:
        return ""

    if lines and lines[0].strip() == "---":
        for line in lines[1:]:
            stripped = line.strip()
            if stripped == "---":
                break
            if stripped.lower().startswith("description:"):
                return stripped.split(":", 1)[1].strip()

    for line in lines:
        stripped = line.strip()
        if stripped and not stripped.startswith("#") and stripped != "---":
            return stripped
    return ""


def _generate_integrations(
    workspace_root: str,
    *,
    allowed_names: Optional[List[str]] = None,
) -> None:
    """Regenerate Claude agents, Gemini commands, and Codex skills.

    Loaded from scripts/generate-integrations.py so the compile step keeps the
    host integrations in sync with the agents/ and .claude/commands/ sources. A
    packaged Claude-only fallback when the project script is absent.
    """
    import importlib.util

    gi_path = os.path.join(workspace_root, "scripts", "generate-integrations.py")
    if not os.path.isfile(gi_path):
        from solomon_harness.integrations import generate_claude_agents

        if allowed_names is None:
            raise ValueError("fallback integration generation requires selected agent names")
        generate_claude_agents(workspace_root, allowed_names=allowed_names)
        return
    spec = importlib.util.spec_from_file_location("generate_integrations", gi_path)
    if spec and spec.loader:
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        module.generate(workspace_root)


def handle_db_init(harness_dir: str) -> None:
    """Initializes the database client for the given harness directory."""
    from solomon_harness.tools.database_client import DatabaseClient

    try:
        with DatabaseClient(harness_dir=harness_dir) as db:
            print(f"Database initialized successfully at: {db.db_path}")
    except Exception as e:
        print(f"Error: Failed to initialize database: {e}", file=sys.stderr)
        sys.exit(1)


def handle_eval(harness_dir: str) -> None:
    """Runs the shared agent evaluation suite against this harness directory."""
    import unittest
    from solomon_harness.evals import build_agent_suite

    print(f"Running agent evaluations for {harness_dir}...")
    suite = build_agent_suite(harness_dir)
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    if not result.wasSuccessful():
        sys.exit(1)
    else:
        sys.exit(0)


def handle_run(harness_dir: str, task=None) -> None:
    """Show where the team stopped and point to the delivery workflows.

    The harness does not run a model itself; Claude Code and Gemini expose the
    workflows as /solomon-* commands, while Codex exposes them as $solomon-*
    skills. This command resumes context from project memory and lists both
    invocation forms. It no longer simulates task execution.
    """
    from solomon_harness.tools.database_client import DatabaseClient

    try:
        db_client = DatabaseClient(harness_dir=harness_dir)
    except Exception as e:
        print(f"Error: Failed to initialize database client: {e}", file=sys.stderr)
        sys.exit(1)

    from solomon_harness.voice import say

    with db_client as db:
        # Determine workspace root
        project_root = harness_dir
        found_root = False
        while project_root and project_root != os.path.dirname(project_root):
            if os.path.exists(os.path.join(project_root, ".git")):
                found_root = True
                break
            project_root = os.path.dirname(project_root)
        workspace_root = project_root if found_root else harness_dir

        try:
            from solomon_harness.bootstrap import scan_project_structure
            scan_project_structure(workspace_root, db)
        except Exception as exc:
            import logging
            logging.warning(f"Project structure scan failed at session start: {type(exc).__name__}")

        print(say("project status"))

        # One-screen board digest: resume point, open work, the last loop run,
        # and PRs awaiting review. Facts only; the next step is decided by
        # /solomon-workflow, never computed here.
        from solomon_harness.digest import gather_digest

        print()
        for line in gather_digest(harness_dir, db):
            print(line)

        # Surface any pending initialization items (Docker down, memory on the
        # SQLite fallback, missing board scope, global install not run).
        try:
            from solomon_harness.healthcheck import pending_summary, run_checks

            pending = pending_summary(run_checks(harness_dir))
            if pending:
                print(say("\nPending initialization (run 'solomon-harness healthcheck' for detail):"))
                for item in pending:
                    print(f"  - {item}")
        except Exception as e:
            print(f"Warning: could not run healthcheck: {e}", file=sys.stderr)

        if task:
            print(
                "\nTasks are not auto-run here. Start this one with a workflow, "
                f'e.g. /solomon-issue "{task}", or $solomon-issue in Codex.'
            )

        print("\nDelivery workflows (Claude/Gemini | Codex):")
        workflows = [
            ("solomon-workflow", "run a task end-to-end, or continue from a previous execution"),
            ("solomon-loop", "autonomous parallel loop over Ready issues"),
            ("solomon-idea", "capture a product idea"),
            ("solomon-issue", "create a feature or story issue"),
            ("solomon-bug", "create a bug report"),
            ("solomon-refine", "refine an issue to Ready"),
            ("solomon-start", "start development: branch, plan, TDD, draft PR"),
            ("solomon-review", "review a pull request"),
            ("solomon-release", "deliver and release"),
        ]
        for name, desc in workflows:
            print(f"  /{name:<20} ${name:<20} {desc}")
        print("\nHeadless (CI/automation):  solomon-harness dev <stage> [args]")


def handle_loop_lock(workspace_root: str, action: str) -> None:
    """Inspect or clear the single-driver loop lock (recovery after a crash)."""
    from solomon_harness.loop_lock import LoopLock

    lock = LoopLock(workspace_root)
    info = lock.read()

    if action == "status":
        if not info:
            print(f"No loop lock held. ({lock.path})")
            return
        state = "STALE (reclaimable)" if lock.is_stale(info) else "live"
        print(f"Loop lock: {lock.path}")
        print(f"  session:   {info.get('session_id')}  pid: {info.get('pid')}  host: {info.get('host')}")
        print(f"  stage:     {info.get('stage')}")
        print(f"  acquired:  {info.get('acquired_at')}")
        print(f"  heartbeat: {info.get('heartbeat_at')}")
        print(f"  state:     {state}")
        return

    # release: force-remove for recovery, warning if a live foreign driver owns it.
    if not info:
        print("No loop lock to release.")
        return
    if info.get("session_id") != lock.session_id and not lock.is_stale(info):
        print(
            f"Warning: lock is held by a live driver (session {info.get('session_id')}, "
            f"pid {info.get('pid')}). Removing anyway.",
            file=sys.stderr,
        )
    try:
        os.remove(lock.path)
        print(f"Released loop lock at {lock.path}")
    except FileNotFoundError:
        print("No loop lock to release.")


def handle_claim(workspace_root: str, action: str, issue_number: int, force: bool = False) -> None:
    """Inspect, acquire, or release an issue claim/lease."""
    from solomon_harness import claim
    import datetime
    import sys

    if action == "acquire":
        # The interactive chokepoint (ADR-0027): /solomon-start runs this
        # before creating any branch or PLAN so interactive sessions get the
        # same mutual exclusion the headless gate enforces. Exit 0 = claim
        # held by this session; exit 1 = refused (holder shown when known).
        current_sess = claim.get_current_session_id()
        if claim.claim_issue(workspace_root, issue_number, current_session_id=current_sess):
            print(f"Claimed issue #{issue_number} for session {current_sess}.")
            return
        # Mirror the headless gate's semantics exactly: any ref still present
        # (well-formed or malformed) means refused; a genuinely absent ref
        # means there is no reachable claims remote -- a no-op environment,
        # where interactive and headless both proceed without a claim.
        ref_info = claim.get_claim_ref(workspace_root, issue_number)
        if ref_info is None:
            print(
                f"Warning: could not record a claim ref for issue #{issue_number} "
                "(no claims remote configured?); proceeding without one.",
                file=sys.stderr,
            )
            return
        holder = ref_info[1]
        if holder is not None:
            acquired_str = holder.get("acquired_at") or "unknown"
            age_str = "unknown"
            try:
                acquired = datetime.datetime.fromisoformat(acquired_str.replace("Z", "+00:00"))
                now = datetime.datetime.now(datetime.timezone.utc)
                age_str = f"{int((now - acquired).total_seconds() / 60)} minutes"
            except Exception:
                pass
            print(
                f"Error: issue #{issue_number} is claimed by session "
                f"'{holder.get('session_id')}' (age: {age_str}), or its PR/review "
                "liveness could not be confirmed. Refusing to claim.",
                file=sys.stderr,
            )
        else:
            print(
                f"Error: issue #{issue_number} carries a malformed claim ref that "
                "could not be reclaimed; inspect with 'solomon-harness claim status' "
                f"and clear it with 'solomon-harness claim release {issue_number} --force'.",
                file=sys.stderr,
            )
        sys.exit(1)

    if action == "status":
        ref_info = claim.get_claim_ref(workspace_root, issue_number)
        if ref_info is not None and ref_info[1] is None:
            # A poisoned ref must not read as "unclaimed" to an operator
            # during a corruption incident: it still occupies the ref.
            print(
                f"Issue #{issue_number} carries a MALFORMED claim ref (recoverable: "
                f"a new claim reclaims it, or 'claim release {issue_number} --force' deletes it)."
            )
            return
        c = ref_info[1] if ref_info else None
        if not c:
            print(f"Issue #{issue_number} is unclaimed.")
            return
        has_pr = claim.has_active_pr_or_review(workspace_root, issue_number)
        current_sess = claim.get_current_session_id()
        active = claim.is_claim_active(c, current_sess, has_open_pr=has_pr)
        status_str = "ACTIVE" if active else "STALE"
        acquired_str = c.get("acquired_at") or "unknown"
        age_str = "unknown"
        try:
            acquired = datetime.datetime.fromisoformat(acquired_str.replace("Z", "+00:00"))
            now = datetime.datetime.now(datetime.timezone.utc)
            diff = now - acquired
            age_str = f"{int(diff.total_seconds() / 60)} minutes"
        except Exception:
            pass
        print(f"Claim status: {status_str}")
        print(f"  Holder (session): {c.get('session_id')}")
        print(f"  Acquired: {acquired_str} (age: {age_str})")
        print(f"  Protected by open PR/review: {has_pr}")
        return

    if action == "release":
        current_sess = claim.get_current_session_id()
        if claim.release_claim(
            workspace_root, issue_number, current_session_id=current_sess, force=force
        ):
            print(f"Released claim on issue #{issue_number}." + (" (forced)" if force else ""))
        else:
            print(
                f"Error: failed to release claim on issue #{issue_number} "
                "(it may be active and owned by another session, or its "
                "PR/review liveness could not be confirmed). An operator who "
                "must clear it anyway can rerun with --force.",
                file=sys.stderr,
            )
            sys.exit(1)


def handle_loop_stop(workspace_root: str, clear: bool) -> None:
    """Kill-switch: halt all autonomous loop stages immediately, or clear it."""
    from solomon_harness import loop_policy

    if clear:
        removed = loop_policy.clear_stop(workspace_root)
        print("Loop kill-switch cleared." if removed else "No kill-switch was engaged.")
    else:
        path = loop_policy.write_stop(workspace_root)
        print(
            "Loop HALTED. Every autonomous stage is blocked until you clear it:\n"
            "  solomon-harness loop-stop --clear\n"
            f"  ({path})"
        )


def handle_loop_policy(workspace_root: str) -> None:
    """Show the autonomy level, kill-switch state, denylist and per-stage gates."""
    from solomon_harness.loop_policy import LoopPolicy

    p = LoopPolicy.from_config(workspace_root)
    print(f"Autonomy level: {p.level}")
    print(f"Kill-switch:    {'ENGAGED' if p.is_halted() else 'clear'}")
    print(f"Checker split:  {'ok' if p.checker_split_ok() else 'not configured (set maker_model/checker_model)'}")
    print(f"Denylist ({len(p.denylist)}): {', '.join(p.denylist)}")
    print("Stage gates:")
    for stage in ["workflow", "loop", "idea", "issue", "bug", "refine", "start", "review", "release"]:
        d = p.decide_stage(stage)
        verdict = "allow" if d.allowed else "DENY "
        print(f"  {stage:<8} {verdict} {d.reason}")


def handle_notify(workspace_root: str, message: str, event: str) -> None:
    """Send one outbound status notification (console or webhook)."""
    from solomon_harness import notify

    if notify.send(workspace_root, event, message):
        print("Notification sent.")
    else:
        print("No notifier configured (set SOLOMON_NOTIFY_WEBHOOK or a notify.mode in .agent/config.json).")


def handle_loop_budget(workspace_root: str) -> None:
    """Show today's autonomous-loop cost spend versus the configured ceiling."""
    from solomon_harness import loop_budget
    from solomon_harness.loop_policy import LoopPolicy

    p = LoopPolicy.from_config(workspace_root)
    spend = loop_budget.daily_spend(workspace_root)
    ceiling = p.daily_cost_ceiling
    print(f"Daily spend: ${spend:.4f}")
    if ceiling:
        status = "OVER -> report-only" if loop_budget.over_ceiling(workspace_root, ceiling) else "within budget"
        print(f"Ceiling:     ${ceiling}  ({status})")
    else:
        print("Ceiling:     none configured (set loop.daily_cost_ceiling_usd)")
    print(f"Ledger:      {loop_budget.ledger_path(workspace_root)}")


def handle_loop_guard(workspace_root: str) -> None:
    """PreToolUse hook: block unsafe tool calls under the loop's guardrails.

    Blocks a `git push` / `gh pr merge` issued while another live driver holds the
    lock, and a file-write tool (Edit/Write/MultiEdit) that targets a denylisted
    path (so an autonomous run cannot edit `.agent/config.json` to widen itself).
    Reads the Claude Code hook payload from stdin. Exits 2 to block (the message is
    fed back to the model), 0 to allow. Fail-open: any error allows the tool,
    because the portable enforcement of record is the run_stage gate, not this hook.
    """
    import json as _json

    try:
        raw = sys.stdin.read()
        payload = _json.loads(raw) if raw.strip() else {}
    except Exception:
        sys.exit(0)

    try:
        from solomon_harness.loop_lock import LoopLock, guard_verdict
        from solomon_harness.loop_policy import LoopPolicy, denied_write_verdict

        lock = LoopLock(workspace_root, session_id=payload.get("session_id"))
        block, reason = guard_verdict(payload, lock)
        if not block:
            block, reason = denied_write_verdict(payload, LoopPolicy.from_config(workspace_root))
    except Exception:
        sys.exit(0)

    if block:
        print(reason, file=sys.stderr)
        sys.exit(2)
    sys.exit(0)


def handle_log(workspace_root: str, last: int) -> None:
    """Print the read-only loop activity feed over the project memory."""
    from solomon_harness import loop_log
    from solomon_harness.tools.database_client import DatabaseClient

    try:
        with DatabaseClient(harness_dir=workspace_root) as db:
            entries = loop_log.gather_feed(db, last=last)
    except Exception as e:
        print(f"Error: could not read loop activity: {e}", file=sys.stderr)
        sys.exit(1)
    for line in loop_log.format_feed(entries):
        print(line)


# Upper bound on the issues a single `gh issue list` returns. When the result hits
# this cap the listing may be truncated, so reconcile warns instead of silently
# missing closed issues beyond it.
_GH_ISSUE_LIMIT = 1000


def _fetch_gh_states(
    list_args: List[str],
    valid_states: Tuple[str, ...],
    kind_label: str,
    workspace_root: str,
) -> List[dict]:
    """Run a bulk ``gh <list_args> --state all`` query and return validated records.

    Returns validated number/state records.
    gh output is treated strictly as data across the trust boundary (STRIDE): the
    number is coerced to ``str(int(...))`` and the state must be one of the accepted
    GitHub literals, so a malformed record is skipped rather than trusted, and no
    field is interpolated into a query. Raises ``RuntimeError`` when gh is
    unavailable or its output cannot be parsed, so the caller reports instead of
    repairing nothing silently. This is the single fetch core shared by the issue
    and PR fetchers, which differ only in the subcommand and the accepted state set.
    """
    import json as _json
    import subprocess

    from solomon_harness.github import GH_TIMEOUT_SECONDS
    from solomon_harness.subprocess_env import clean_git_env

    try:
        proc = subprocess.run(
            ["gh", *list_args, "--state", "all", "--limit", str(_GH_ISSUE_LIMIT),
             "--json", "number,state"],
            cwd=workspace_root, capture_output=True, text=True, check=False,
            env=clean_git_env(), timeout=GH_TIMEOUT_SECONDS,
        )
    except FileNotFoundError as exc:
        raise RuntimeError(
            "gh CLI not found; install and authenticate the GitHub CLI."
        ) from exc
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(
            f"gh {kind_label} list timed out after {GH_TIMEOUT_SECONDS}s"
        ) from exc
    if proc.returncode != 0:
        raise RuntimeError(
            (proc.stderr or proc.stdout).strip() or f"gh {kind_label} list failed"
        )
    try:
        raw = _json.loads(proc.stdout or "[]")
    except _json.JSONDecodeError as exc:
        raise RuntimeError(f"could not parse gh JSON output: {exc}") from exc

    if isinstance(raw, list) and len(raw) >= _GH_ISSUE_LIMIT:
        print(
            f"warning: gh returned the {_GH_ISSUE_LIMIT}-record {kind_label} cap; the "
            "listing may be truncated, so reconcile could miss resolved parents "
            "beyond it.",
            file=sys.stderr,
        )

    states: List[dict] = []
    for item in raw if isinstance(raw, list) else []:
        if not isinstance(item, dict):
            continue
        raw_number = item.get("number")
        if raw_number is None:
            continue
        try:
            number = str(int(raw_number))
        except (TypeError, ValueError):
            continue
        state = str(item.get("state", "")).upper()
        if state not in valid_states:
            continue
        states.append({"number": number, "state": state})
    return states


def _fetch_gh_issue_states(workspace_root: str) -> List[dict]:
    """Read every issue's GitHub state via gh (``OPEN``/``CLOSED``), as data.

    Thin config over ``_fetch_gh_states``; the validation and STRIDE handling live
    in that shared core.
    """
    return _fetch_gh_states(["issue", "list"], ("OPEN", "CLOSED"), "issue", workspace_root)


def _canonical_board_statuses(board_items: object) -> Dict[str, Optional[str]]:
    """Index unambiguous issue statuses from the exact canonical board listing."""
    if not isinstance(board_items, list):
        return {}
    candidates: Dict[str, List[str]] = {}
    for board_item in board_items:
        if not isinstance(board_item, dict):
            continue
        content = board_item.get("content")
        status = board_item.get("status")
        if not isinstance(content, dict) or content.get("type") != "Issue":
            continue
        if not isinstance(status, str):
            continue
        raw_number = content.get("number")
        if isinstance(raw_number, bool) or not isinstance(raw_number, (int, str)):
            continue
        try:
            number = str(int(raw_number))
        except (TypeError, ValueError):
            continue
        candidates.setdefault(number, []).append(status)
    return {
        number: statuses[0] if len(statuses) == 1 else None
        for number, statuses in candidates.items()
    }


def _fetch_reconcile_issue_states(workspace_root: str) -> List[dict]:
    """Join GitHub issue state to the exact canonical Project card status."""
    from solomon_harness.claim import fetch_board_items

    issue_states = _fetch_gh_issue_states(workspace_root)
    board_items = fetch_board_items(workspace_root)
    if board_items is None:
        raise RuntimeError("could not read canonical board items")
    board_statuses = _canonical_board_statuses(board_items)
    return [
        {**entry, "board_status": board_statuses.get(str(entry["number"]))}
        for entry in issue_states
    ]


def _fetch_gh_pr_states(workspace_root: str) -> List[dict]:
    """Read every PR's GitHub state via gh (``OPEN``/``CLOSED``/``MERGED``), as data.

    The extra ``MERGED`` literal is why a PR parent needs its own fetch: a merged
    PR resolves its tracking children just as a closed issue does (#127). Thin
    config over ``_fetch_gh_states``.
    """
    return _fetch_gh_states(
        ["pr", "list"], ("OPEN", "CLOSED", "MERGED"), "pull request", workspace_root
    )


def _build_resolved_map(
    issue_states: List[dict], pr_states: List[dict]
) -> Dict[str, bool]:
    """Merge issue and PR states into a number-keyed resolved map (#127).

    Issues and PRs share one GitHub number sequence, so the map is keyed by number.
    A number is RESOLVED (True) when its issue state is ``CLOSED`` or its PR state
    is ``MERGED`` or ``CLOSED``; an ``OPEN`` issue or ``OPEN`` PR records the number
    as not-yet-resolved (False) without overriding a resolved signal from the other
    source, so the merge is an order-independent OR. A number absent from both is
    simply not a key, which the close pass treats exactly like an open parent.
    """
    resolved: Dict[str, bool] = {}
    for entry in issue_states:
        number = entry.get("number")
        if number is None:
            continue
        if entry.get("state") == "CLOSED":
            resolved[number] = True
        else:
            resolved.setdefault(number, False)
    for entry in pr_states:
        number = entry.get("number")
        if number is None:
            continue
        if entry.get("state") in ("CLOSED", "MERGED"):
            resolved[number] = True
        else:
            resolved.setdefault(number, False)
    return resolved


def reconcile_memory(
    db,
    gh_states: List[dict],
    dry_run: bool = False,
    set_issue_status_fn=None,
) -> dict:
    """Set each GitHub-CLOSED issue's non-terminal memory row to "closed", and
    move its board card to "Done".

    GitHub is the source of truth (ADR-0006): a memory row is repaired only when
    GitHub reports the issue CLOSED and the row exists and is not already
    terminal; GitHub-open rows are left untouched. The write is a read-modify-
    write through the unchanged 5-arg ``log_issue`` (UPSERT on github_id),
    preserving the title, type and milestone. Idempotent: a second run finds the
    rows terminal and writes nothing.

    The board-card move is deliberately decoupled from the memory-repair gate
    (#264, #280), but remains idempotent: it is attempted only for a
    GitHub-CLOSED entry whose canonical ``board_status`` is absent or differs
    from ``Done``. A live case showed memory already "closed" while the board
    card was still stuck in "Code Review", which the memory gate alone would
    never touch. ``set_issue_status_fn`` defaults to
    ``solomon_harness.github.set_issue_status`` (mirroring this codebase's
    ``claim_store``/``GitClaimStore`` default-construction convention); a caller
    may inject a fake to avoid a live gh call. A board-move failure is recorded
    per-issue in ``board_failures`` and never rolls back or blocks the memory
    repair for that same issue, which may already have landed independently.
    With ``dry_run`` no write and no board move is attempted: the stale memory
    ids are collected in ``would_repair`` and only actual board drift is listed
    in ``would_move_board`` (ADR-0034).

    Returns ``{"repaired", "would_repair", "scanned", "board_moved",
    "board_failures", "would_move_board"}``.
    """
    from solomon_harness.tools.database_client import is_terminal

    if set_issue_status_fn is None:
        from solomon_harness.github import set_issue_status as set_issue_status_fn

    would_repair: List[str] = []
    repaired = 0
    board_moved = 0
    board_failures: List[dict] = []
    would_move_board: List[str] = []
    for entry in gh_states:
        if entry.get("state") != "CLOSED":
            continue
        number = entry["number"]

        row = db.get_issue(number)
        if row is not None and not is_terminal(row.get("status")):
            would_repair.append(number)
            if not dry_run:
                db.log_issue(
                    number,
                    row.get("title"),
                    row.get("type_"),
                    "closed",
                    row.get("milestone_id"),
                )
                repaired += 1

        if entry.get("board_status") == "Done":
            continue

        if dry_run:
            would_move_board.append(number)
            continue

        move_result = set_issue_status_fn(int(number), "Done")
        if move_result.get("ok"):
            board_moved += 1
        else:
            board_failures.append(
                {"issue": number, "ok": False, "error": move_result.get("error")}
            )
    return {
        "repaired": repaired,
        "would_repair": would_repair,
        "scanned": len(gh_states),
        "board_moved": board_moved,
        "board_failures": board_failures,
        "would_move_board": would_move_board,
    }


def normalize_memory_statuses(db, dry_run: bool = False) -> dict:
    """Canonicalize any non-canonical status still stored on a non-terminal row.

    ``log_issue`` has normalized on write since ADR-0006, so this is a one-shot
    repair for rows written before that (or by a path that bypassed it): display
    names ("Code Review"), casing variants ("backlog") and legacy words ("review")
    that leave consumers unable to read the row's stage. Each differing row is
    read-modify-written through the unchanged ``log_issue`` UPSERT, preserving
    title/type/milestone/assignee -- only the status token changes.

    This is a deliberately narrow exception to ADR-0006 decision point 1, which
    rejected option 1c (a destructive bulk rewrite of stored rows): nothing is
    deleted, no field is lost, and no contract changes, so the "reversible,
    non-destructive migration" constraint still holds (ADR-0033).

    Terminal rows are out of scope by construction: the pass walks
    ``get_open_issues`` (the non-terminal predicate), and the legacy terminal
    literals "done"/"Done" are already excluded by it. Idempotent: a second run
    finds every row canonical and writes nothing. With ``dry_run`` the ids are
    collected and nothing is written.

    Returns ``{"normalized", "would_normalize", "scanned"}``.
    """
    from solomon_harness.tools.database_client import normalize_status

    would_normalize: List[str] = []
    normalized = 0
    scanned = 0
    for row in db.get_open_issues():
        scanned += 1
        current = row.get("status")
        canonical = normalize_status(current)
        if current == canonical:
            continue
        github_id = row.get("github_id")
        would_normalize.append(github_id)
        if dry_run:
            continue
        db.log_issue(
            github_id,
            row.get("title"),
            row.get("type_"),
            canonical,
            row.get("milestone_id"),
            row.get("assignee"),
        )
        normalized += 1
    return {
        "normalized": normalized,
        "would_normalize": would_normalize,
        "scanned": scanned,
    }


def reconcile_tracking_rows(db, resolved_map: Dict[str, bool], dry_run: bool = False) -> dict:
    """Set each tracking row whose parent number is RESOLVED to the terminal "done".

    Tracking rows are the non-numeric slug rows (``is_github_issue`` False) that
    carry RAID/follow-up items parented to a real GitHub issue or PR (#127). This
    pass walks the non-terminal rows, skips the numeric GitHub rows untouched,
    recovers each tracking row's parent number with ``recover_parent``, and -- when
    that number is RESOLVED in ``resolved_map`` (its issue is CLOSED or its PR is
    MERGED/CLOSED) -- read-modify-writes the row to "done" through the unchanged
    6-arg ``log_issue`` UPSERT, preserving title/type/milestone/assignee. The write
    normalizes "done" to the terminal "closed", so the row drops out of
    ``get_open_issues``; a second pass therefore closes nothing (idempotent). A row
    with an unresolved or absent parent is left open (never guessed); a row with no
    recoverable parent is counted and skipped. No row is ever deleted. With
    ``dry_run`` the would-close slugs are collected and nothing is written.

    Returns ``{"closed", "would_close", "skipped_no_parent", "scanned_tracking"}``.
    """
    from solomon_harness.tools.database_client import is_github_issue, recover_parent

    would_close: List[str] = []
    closed = 0
    skipped_no_parent = 0
    scanned_tracking = 0
    for row in db.get_open_issues():
        github_id = row.get("github_id")
        if is_github_issue(github_id):
            continue
        scanned_tracking += 1
        parent = recover_parent(github_id, row.get("title"))
        if parent is None:
            skipped_no_parent += 1
            print(
                f"warning: tracking row {github_id!r} has no recoverable parent "
                "number; left open.",
                file=sys.stderr,
            )
            continue
        if not resolved_map.get(parent):
            continue
        would_close.append(github_id)
        if dry_run:
            continue
        db.log_issue(
            github_id,
            row.get("title"),
            row.get("type_"),
            "done",
            row.get("milestone_id"),
            row.get("assignee"),
        )
        closed += 1
    return {
        "closed": closed,
        "would_close": would_close,
        "skipped_no_parent": skipped_no_parent,
        "scanned_tracking": scanned_tracking,
    }


def handle_reconcile(workspace_root: str, dry_run: bool) -> None:
    """Run reconciliation under the repository's single-driver mutation lock."""
    from solomon_harness.loop_lock import LoopLock, LoopLockHeld

    lock = LoopLock(workspace_root, stage="reconcile")
    try:
        lock.acquire()
    except LoopLockHeld as held:
        print(
            f"reconcile refused: another solomon driver holds the loop lock ({held}).",
            file=sys.stderr,
        )
        sys.exit(1)
    try:
        _handle_reconcile_locked(workspace_root, dry_run)
    finally:
        lock.release()


def _handle_reconcile_locked(workspace_root: str, dry_run: bool) -> None:
    """Reconcile the memory issue rows against GitHub (GitHub is the source of truth).

    Targets the shared SurrealDB only: on a SQLite-fallback backend it warns and
    skips the whole repair rather than half-repairing a per-worktree store
    (ADR-0006 / RAID R1). Run it from a fresh process so it never inherits the
    dead MCP write socket of bug #37.
    """
    from solomon_harness.tools.database_client import DatabaseClient

    with DatabaseClient(harness_dir=workspace_root) as db:
        if db.backend != "surrealdb":
            print(
                "reconcile skipped: memory is on the SQLite fallback, not the shared "
                "SurrealDB. Run it from a process that reaches the shared store so a "
                "per-worktree DB is never half-repaired.",
                file=sys.stderr,
            )
            return
        try:
            issue_states = _fetch_reconcile_issue_states(workspace_root)
            pr_states = _fetch_gh_pr_states(workspace_root)
        except RuntimeError as exc:
            print(f"reconcile failed: {exc}", file=sys.stderr)
            sys.exit(1)
        result = reconcile_memory(db, issue_states, dry_run=dry_run)
        resolved_map = _build_resolved_map(issue_states, pr_states)
        tracking = reconcile_tracking_rows(db, resolved_map, dry_run=dry_run)
        # Runs last: the two passes above may have just made rows terminal, and a
        # terminal row needs no status normalization (#173).
        statuses = normalize_memory_statuses(db, dry_run=dry_run)

    if dry_run:
        ids = ", ".join(f"#{n}" for n in result["would_repair"])
        suffix = f": {ids}" if ids else ""
        print(
            f"reconcile --dry-run: {len(result['would_repair'])} issue(s) would be "
            f"set to closed ({result['scanned']} GitHub issues scanned){suffix}"
        )
        board_ids = ", ".join(f"#{n}" for n in result["would_move_board"])
        board_suffix = f": {board_ids}" if board_ids else ""
        print(
            f"reconcile --dry-run: {len(result['would_move_board'])} board card(s) "
            f"would move to Done{board_suffix}"
        )
        slugs = ", ".join(tracking["would_close"])
        track_suffix = f": {slugs}" if slugs else ""
        print(
            f"reconcile --dry-run: {len(tracking['would_close'])} tracking row(s) "
            f"would be set to done ({tracking['scanned_tracking']} tracking rows "
            f"scanned){track_suffix}"
        )
        status_ids = ", ".join(f"#{n}" for n in statuses["would_normalize"])
        status_suffix = f": {status_ids}" if status_ids else ""
        print(
            f"reconcile --dry-run: {len(statuses['would_normalize'])} row(s) would "
            f"have their status normalized ({statuses['scanned']} non-terminal rows "
            f"scanned){status_suffix}"
        )
    else:
        print(
            f"reconcile: {result['repaired']} issue(s) set to closed "
            f"({result['scanned']} GitHub issues scanned)"
        )
        print(f"reconcile: {result['board_moved']} board card(s) moved to Done")
        for failure in result["board_failures"]:
            print(
                f"reconcile: board move failed for #{failure['issue']}: "
                f"{failure['error']}",
                file=sys.stderr,
            )
        print(
            f"reconcile: {tracking['closed']} tracking row(s) set to done "
            f"({tracking['scanned_tracking']} tracking rows scanned)"
        )
        print(
            f"reconcile: {statuses['normalized']} row(s) status-normalized "
            f"({statuses['scanned']} non-terminal rows scanned)"
        )


def build_parser() -> argparse.ArgumentParser:
    """Build the top-level parser and every subcommand.

    This is the single source of truth for the CLI surface: tooling and tests
    that need the live list of subcommands (e.g. a docs consistency check)
    should introspect the returned parser's subparsers action here rather than
    hand-maintaining a parallel list that can drift from this file.
    """
    parser = argparse.ArgumentParser(description="Solomon Harness Agent Command Line Interface")
    subparsers = parser.add_subparsers(dest="command", help="Available subcommands")

    subparsers.add_parser("db-init", help="Initialize the long-term database client and tables")
    subparsers.add_parser("eval", help="Run the agent evaluations test suite")
    run_parser = subparsers.add_parser("run", help="Simulate running a task")
    run_parser.add_argument("task", type=str, nargs="?", default=None, help="The task description to execute (optional)")

    # New subcommands for workspace management
    init_parser = subparsers.add_parser("init", help="Initialize workspace configuration and rules")
    init_parser.add_argument("--non-interactive", action="store_true", help="Run in non-interactive mode using default configurations")

    subparsers.add_parser(
        "compile",
        help="Compile agent harnesses and regenerate host-tool integrations",
    )
    subparsers.add_parser("index", help="Index project codebase into the database memory")
    subparsers.add_parser("wiki", help="Refresh the living code-overview wiki page from the index")

    mem_up = subparsers.add_parser("memory-up", help="Start the memory backend (docker compose) if it is not already running")
    mem_up.add_argument("--wait", type=int, default=25, help="Seconds to wait for the backend port after starting")
    subparsers.add_parser("memory-down", help="Stop the memory backend (docker compose down)")

    memory_parser = subparsers.add_parser(
        "memory", help="Memory store maintenance (reconcile the write-through mirror)"
    )
    memory_sub = memory_parser.add_subparsers(dest="memory_command", help="Memory subcommands")
    memory_sub.add_parser(
        "sync", help="Replay pending mirror records to SurrealDB and report the counts"
    )

    reconcile_parser = subparsers.add_parser(
        "reconcile",
        help=(
            "Under the single-driver lock, repair closed-issue memory/tracking rows, "
            "canonical board drift, and non-terminal status tokens. Run from a fresh "
            "process against the shared SurrealDB."
        ),
    )
    reconcile_parser.add_argument(
        "--dry-run", action="store_true", help="Report proposed repairs without writing"
    )

    ig_parser = subparsers.add_parser(
        "install-global",
        help="Install agents, /solomon commands, the session hook, and the shared memory home into ~/.claude and ~/.solomon-harness",
    )
    ig_parser.add_argument("--no-mcp", action="store_true", help="Skip MCP server registration with the host CLI")

    doctor_parser = subparsers.add_parser("doctor", help="Check (and install) prerequisites")
    doctor_parser.add_argument("--no-install", action="store_true", help="Only report; do not install")

    subparsers.add_parser("healthcheck", help="Report runtime readiness and pending init items (Docker, memory, board, global install)")

    subparsers.add_parser("git-repair", help="Repair local git config by unsetting stray core.worktree and setting core.bare to false")

    loop_lock_parser = subparsers.add_parser(
        "loop-lock", help="Inspect or clear the single-driver loop lock"
    )
    loop_lock_parser.add_argument(
        "action", choices=["status", "release"], nargs="?", default="status",
        help="status (default) shows the holder; release clears a stale or stuck lock",
    )

    claim_parser = subparsers.add_parser(
        "claim", help="Inspect, acquire, or release an issue claim/lease"
    )
    claim_parser.add_argument(
        "action", choices=["status", "acquire", "release"],
        help="status shows the holder; acquire claims the issue for this session "
        "(the /solomon-start interactive gate); release clears a claim",
    )
    claim_parser.add_argument(
        "issue", type=int,
        help="The issue number to inspect, acquire, or release",
    )
    claim_parser.add_argument(
        "--force", action="store_true",
        help="release only: clear the claim even if it is active and owned by "
        "another session (operator escape hatch for a stuck claim)",
    )

    log_parser = subparsers.add_parser(
        "log", help="Show the loop activity feed (loop runs, decisions, handoffs)"
    )
    log_parser.add_argument("--last", type=int, default=20, help="How many recent entries to show")

    subparsers.add_parser(
        "loop-guard",
        help="PreToolUse hook: block push/merge while another driver holds the loop lock (reads the hook payload on stdin)",
    )

    loop_stop_parser = subparsers.add_parser(
        "loop-stop", help="Kill-switch: halt all autonomous loop stages immediately (or --clear)"
    )
    loop_stop_parser.add_argument("--clear", action="store_true", help="Clear the kill-switch")

    subparsers.add_parser(
        "loop-policy",
        help="Show the autonomy level, kill-switch state, denylist and per-stage gates",
    )

    notify_parser = subparsers.add_parser(
        "notify", help="Send an outbound status notification (console or webhook)"
    )
    notify_parser.add_argument("message", type=str, help="The message to send")
    notify_parser.add_argument("--event", type=str, default="manual", help="Event label")

    subparsers.add_parser(
        "loop-budget", help="Show today's autonomous-loop cost spend versus the ceiling"
    )

    dev_parser = subparsers.add_parser(
        "dev",
        help=(
            "Run a delivery workflow headless (workflow, loop, idea, issue, bug, "
            "refine, start, review, release, reconcile)"
        ),
    )
    dev_parser.add_argument("stage", type=str, help="The workflow stage")
    dev_parser.add_argument(
        "dev_args", nargs=argparse.REMAINDER,
        help="Arguments passed to the workflow (loop accepts --concurrency N to run N iterations)",
    )

    release_parser = subparsers.add_parser(
        "release",
        help="Plan, prepare, check, or document a milestone-gated release (plan | prep [version] | check | verify-window | wiki-page [version])",
    )
    release_parser.add_argument(
        "release_args",
        nargs=argparse.REMAINDER,
        help="release subcommand: plan (read-only), prep [version] (open the prep PR), check (fail-closed gate), verify-window (recompute the release window against trunk HEAD pre-tag), wiki-page [version] (write the release wiki page)",
    )

    wt_parser = subparsers.add_parser(
        "worktree",
        help="Create or locate the isolated git worktree for a branch (used by /solomon-start)",
    )
    wt_parser.add_argument("branch", type=str, help="Branch name, e.g. feature/<slug>")
    wt_parser.add_argument(
        "--base", type=str, default="main", help="Base ref for a new branch (default: main)"
    )

    broker_parser = subparsers.add_parser(
        "broker",
        help="Capability broker (ADR-0008): route a demand or apply an approved acquisition",
    )
    broker_parser.add_argument(
        "broker_action", choices=["route", "apply"],
        help="route: build the verdict from a demand+match JSON file; apply: run an approved acquisition proposal",
    )
    broker_parser.add_argument(
        "--file", required=True, dest="broker_file",
        help="Path to the JSON payload (written by the host tool, never inlined in a shell string)",
    )

    skills_parser = subparsers.add_parser("skills", help="Manage agent skills")
    skills_parser.add_argument("skills_args", nargs=argparse.REMAINDER, help="Arguments passed to skills manager")

    agents_parser = subparsers.add_parser("agents", help="List and show agent definitions")
    agents_subparsers = agents_parser.add_subparsers(dest="agents_command", help="Agents subcommands")
    agents_subparsers.add_parser("list", help="List all available agents")
    agents_subparsers.add_parser("help", help="Display usage instructions")
    show_parser = agents_subparsers.add_parser("show", help="Show specific agent profile")
    show_parser.add_argument("agent_name", type=str, help="Agent name")
    
    scaffold_parser = agents_subparsers.add_parser("scaffold", help="Scaffold a new specialist agent")
    scaffold_parser.add_argument("agent_name", type=str, help="Agent name")
    scaffold_parser.add_argument("--description", type=str, required=True, help="Agent description")

    github_parser = subparsers.add_parser(
        "github",
        help="GitHub board and PR helpers (ensure-board, set-status, add-issue, merge, pr-create)",
    )
    github_parser.add_argument(
        "github_args",
        nargs=argparse.REMAINDER,
        help="Arguments passed to the github helper module",
    )

    return parser


def main(harness_dir: Optional[str] = None, argv: Optional[List[str]] = None) -> None:
    """Parser setup and command dispatching.

    Args:
        harness_dir: The agent directory the thin entrypoint is running from.
            Defaults to the current working directory when omitted.
        argv: Optional argument list (defaults to sys.argv[1:]).
    """
    import sys
    from solomon_harness.notify import log_progress
    cmd_args = argv if argv is not None else sys.argv[1:]
    log_progress(f"Executing: solomon-harness {' '.join(cmd_args)}")

    parser = build_parser()
    args = parser.parse_args(argv)

    if harness_dir is None:
        harness_dir = os.getcwd()

    # Determine workspace root
    ceilings = []
    if "GIT_CEILING_DIRECTORIES" in os.environ:
        ceilings = [
            os.path.abspath(p)
            for p in os.environ["GIT_CEILING_DIRECTORIES"].split(os.pathsep)
            if p
        ]

    project_root = harness_dir
    found_root = False
    while project_root and project_root != os.path.dirname(project_root):
        if os.path.abspath(project_root) in ceilings:
            break
        if os.path.exists(os.path.join(project_root, ".git")):
            found_root = True
            break
        if (
            os.path.exists(os.path.join(project_root, "agents"))
            and os.path.exists(os.path.join(project_root, "memory"))
        ):
            found_root = True
            break
        project_root = os.path.dirname(project_root)
    workspace_root = project_root if found_root else harness_dir

    if args.command == "db-init":
        handle_db_init(harness_dir)
    elif args.command == "eval":
        handle_eval(harness_dir)
    elif args.command == "run":
        handle_run(harness_dir, args.task)
    elif args.command == "init":
        from solomon_harness.bootstrap import bootstrap_project
        bootstrap_project(workspace_root, non_interactive=args.non_interactive)
    elif args.command == "doctor":
        from solomon_harness.prereqs import check_prerequisites
        sys.exit(0 if check_prerequisites(auto_install=not args.no_install) else 1)
    elif args.command == "healthcheck":
        from solomon_harness.healthcheck import format_report, run_checks
        checks = run_checks(workspace_root)
        print(format_report(checks))
        sys.exit(1 if any(c["status"] == "fail" for c in checks) else 0)
    elif args.command == "git-repair":
        from solomon_harness.worktree import repair_git_config
        repair_git_config(workspace_root)
        print("Git local configuration repaired successfully.")
        sys.exit(0)
    elif args.command == "loop-lock":
        handle_loop_lock(workspace_root, args.action)
    elif args.command == "claim":
        handle_claim(workspace_root, args.action, args.issue, force=args.force)
    elif args.command == "loop-guard":
        handle_loop_guard(workspace_root)
    elif args.command == "loop-stop":
        handle_loop_stop(workspace_root, args.clear)
    elif args.command == "loop-policy":
        handle_loop_policy(workspace_root)
    elif args.command == "notify":
        handle_notify(workspace_root, args.message, args.event)
    elif args.command == "loop-budget":
        handle_loop_budget(workspace_root)
    elif args.command == "log":
        handle_log(workspace_root, args.last)
    elif args.command == "reconcile":
        handle_reconcile(workspace_root, args.dry_run)
    elif args.command == "dev":
        from solomon_harness.workflows import run_stage
        sys.exit(run_stage(workspace_root, args.stage, args.dev_args))
    elif args.command == "release":
        from solomon_harness.release import run as release_run
        sys.exit(release_run(workspace_root, args.release_args))
    elif args.command == "worktree":
        from solomon_harness.worktree import cli_worktree
        sys.exit(cli_worktree(workspace_root, args.branch, base=args.base))
    elif args.command == "compile":
        from solomon_harness.bootstrap import scaffold_agents
        from solomon_harness.agent_selection import select_agents

        scaffold_agents(workspace_root)
        allowed_names = select_agents(workspace_root)
        # Keep the host-tool integrations in sync so they never drift from source.
        _generate_integrations(workspace_root, allowed_names=allowed_names)
    elif args.command == "index":
        from solomon_harness.bootstrap import index_codebase
        from solomon_harness.tools.database_client import DatabaseClient
        try:
            with DatabaseClient(harness_dir=workspace_root) as db:
                index_codebase(workspace_root, db)
        except Exception as e:
            print(f"Error: Codebase indexing failed: {e}", file=sys.stderr)
            sys.exit(1)
    elif args.command == "memory-up":
        from solomon_harness.memory import _describe, ensure_memory_up
        result = ensure_memory_up(workspace_root, wait_seconds=args.wait)
        print(_describe(result))
        # Never fail the session-start hook: a missing Docker daemon must not
        # block work, because the client falls back to SQLite.
    elif args.command == "memory-down":
        from solomon_harness.memory import _describe, stop_memory
        result = stop_memory(workspace_root)
        print(_describe(result))
        sys.exit(0 if result.get("ok") else 1)
    elif args.command == "memory":
        from solomon_harness.voice import say
        if args.memory_command == "sync":
            from solomon_harness.tools.database_client import DatabaseClient
            with DatabaseClient(harness_dir=workspace_root) as db:
                counts = db.reconcile()
            print(say(
                f"memory sync: {counts['synced']} reconciled, "
                f"{counts['remaining']} pending"
            ))
        else:
            _subparser(parser, "memory").print_help()
    elif args.command == "github":
        from solomon_harness.github import main as github_main
        sys.exit(github_main(args.github_args))
    elif args.command == "install-global":
        from solomon_harness.install_global import describe, install_global
        result = install_global(register_mcp=not args.no_mcp)
        print(describe(result))
    elif args.command == "wiki":
        from solomon_harness.bootstrap import (
            get_project_metadata,
            index_codebase,
            write_code_overview,
        )
        from solomon_harness.tools.database_client import DatabaseClient
        from solomon_harness.wiki_bootstrap import bootstrap_wiki

        # Initialize the GitHub wiki (or degrade) before refreshing the living
        # docs. The pure-CLI path injects no browser bootstrapper, so an
        # uninitialized wiki resolves to GUIDE (interactive) or the DEGRADE floor
        # (headless), never to AUTOMATE -- the host-driven browser adapter would be
        # injected here. On DEGRADE, exit 4 with the actionable message rather than
        # refresh docs that cannot be published; on NO-OP, fall through unchanged.
        _, git_remote, _ = get_project_metadata(workspace_root)
        outcome = bootstrap_wiki(
            git_remote,
            interactive=sys.stdin.isatty(),
            bootstrapper=None,
        )
        if not outcome.proceed:
            print(outcome.message, file=sys.stderr)
            sys.exit(outcome.exit_code)
        try:
            with DatabaseClient(harness_dir=workspace_root) as db:
                index_codebase(workspace_root, db)
                path = write_code_overview(workspace_root, db)
            print(f"Updated code-overview wiki page: {os.path.relpath(path, workspace_root)}")
        except Exception as e:
            print(f"Error: Failed to refresh the wiki: {e}", file=sys.stderr)
            sys.exit(1)
    elif args.command == "broker":
        from solomon_harness.broker_cli import run as broker_run
        sys.exit(broker_run(args.broker_action, args.broker_file, workspace_root))
    elif args.command == "skills":
        from solomon_harness.skills import main as skills_main
        sys.exit(skills_main(args.skills_args, start_dir=workspace_root))
    elif args.command == "agents":
        # The generated host-tool subagents live in .claude/agents/ (produced by
        # scripts/generate-integrations.py from the agents/ source of truth).
        agents_dir = os.path.join(workspace_root, ".claude", "agents")
        if args.agents_command == "list":
            if not os.path.isdir(agents_dir):
                print(
                    f"Error: Subagents directory '{agents_dir}' not found. "
                    "Run 'solomon-harness compile' or scripts/generate-integrations.py first.",
                    file=sys.stderr,
                )
                sys.exit(1)
            print("Available subagents:")
            found = False
            import glob
            for filepath in sorted(glob.glob(os.path.join(agents_dir, "*.md"))):
                found = True
                filename = os.path.basename(filepath)
                name = filename[:-3]
                print(f"  {name} - {_subagent_description(filepath)}")
            if not found:
                print(f"No subagents found in '{agents_dir}'.")
        elif args.agents_command == "show":
            if not args.agent_name:
                print("Error: Subcommand 'show' requires an agent name.", file=sys.stderr)
                sys.exit(1)
            agent_file = os.path.join(agents_dir, f"{args.agent_name}.md")
            if not os.path.isfile(agent_file):
                print(f"Error: Subagent '{args.agent_name}' does not exist.", file=sys.stderr)
                sys.exit(1)
            try:
                with open(agent_file, "r", encoding="utf-8") as f:
                    print(f.read())
            except Exception as e:
                print(f"Error reading subagent: {e}", file=sys.stderr)
                sys.exit(1)
        elif args.agents_command == "scaffold":
            if not args.agent_name:
                print("Error: Subcommand 'scaffold' requires an agent name.", file=sys.stderr)
                sys.exit(1)
            try:
                scaffold_new_agent(workspace_root, args.agent_name, args.description)
                print(f"Agent '{args.agent_name}' scaffolded and registered successfully.")
            except Exception as e:
                print(f"Error scaffolding agent: {e}", file=sys.stderr)
                sys.exit(1)
        elif args.agents_command == "help":
            print("Usage: solomon-harness agents [list|show <agent_name>|scaffold <agent_name> --description <desc>]")
            sys.exit(0)
        else:
            print("Usage: solomon-harness agents [list|show <agent_name>|scaffold <agent_name> --description <desc>]")
            sys.exit(1)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
