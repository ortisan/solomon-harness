"""CLI surface for the capability broker (ADR-0008): route verdicts and gated apply.

The workflow prompts never build inline Python over issue-derived text. They
write a JSON file (via the host Write tool, so untrusted text never touches a
shell string) and hand its path to these subcommands:

- ``broker route --file <json>``: the host LLM supplies its match judgment in
  the file; the deterministic core (``capability_router.route``) validates the
  matcher contract, enforces fail-closed on an empty catalog, and constructs
  the RouteVerdict/GapVerdict. Read-only.
- ``broker apply --file <json>``: validates every field against strict shapes
  before any curator call, and refuses outright outside an interactive,
  human-driven session — acquisition is permanently human-gated (issue #50
  AC2; the loop may surface a gap, never act on it).

Exit codes: 0 success, 2 bad input (malformed file or failed validation),
3 refused (fail-closed routing error or the human gate).
"""

import json
import os
import re
from dataclasses import asdict
from typing import Any, Dict, List, Optional

from solomon_harness.capability_router import (
    CatalogError,
    Match,
    MatcherContractError,
    route,
)

SNAKE_CASE = re.compile(r"^[a-z0-9_]+$")
ISSUE_ID = re.compile(r"^[0-9]+$")
MAX_TITLE = 200
MAX_DESCRIPTION = 2000
MAX_DUTIES = 12

EXIT_OK = 0
EXIT_BAD_INPUT = 2
EXIT_REFUSED = 3


def _load_json(path: str) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise ValueError("top-level JSON value must be an object")
    return data


def acquisition_gate(
    workspace_root: str, env: Optional[Dict[str, str]] = None
) -> Optional[str]:
    """Return a refusal reason when acquisition must not run, else None.

    Acquisition (adapt a skill, create an agent) mutates the fleet, so it is
    permanently human-gated: it never runs from a headless stage subprocess
    (``SOLOMON_SUBPROCESS`` is the harness's own marker for those), never
    under an automation autonomy level, and never past the kill-switch. This
    is the code-level gate; the prompt text merely explains it.
    """
    resolved = os.environ if env is None else env
    if resolved.get("SOLOMON_SUBPROCESS"):
        return (
            "refused: broker apply is human-gated and this is a headless stage "
            "subprocess; record the gap and let a human run the acquisition"
        )
    from solomon_harness.loop_policy import LoopPolicy

    policy = LoopPolicy.from_config(workspace_root, env=dict(resolved))
    if policy.is_halted():
        return "refused: loop kill-switch engaged"
    if policy.level != "human":
        return (
            f"refused: broker apply is human-gated; autonomy level is "
            f"'{policy.level}', not 'human'"
        )
    return None


def _match_from_payload(payload: Dict[str, Any]) -> Match:
    raw = payload.get("match")
    if not isinstance(raw, dict):
        raise ValueError("'match' must be an object with the matcher's judgment")
    alternatives = raw.get("alternatives") or []
    if not isinstance(alternatives, list) or not all(
        isinstance(a, str) for a in alternatives
    ):
        raise ValueError("'match.alternatives' must be a list of agent names")
    return Match(
        agent=raw.get("agent"),
        rationale=str(raw.get("rationale") or ""),
        alternatives=list(alternatives),
        missing_capability=raw.get("missing_capability"),
        nearest_agent=raw.get("nearest_agent"),
    )


def route_from_file(path: str, workspace_root: Optional[str] = None) -> int:
    """Build the verdict for the demand + match judgment in ``path``; print JSON."""
    try:
        payload = _load_json(path)
        demand = payload.get("demand")
        if not isinstance(demand, str) or not demand.strip():
            raise ValueError("'demand' must be a non-empty string")
        match = _match_from_payload(payload)
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        print(json.dumps({"error": str(exc)}))
        return EXIT_BAD_INPUT
    try:
        verdict = route(demand, lambda _d, _c: match, workspace_root)
    except (CatalogError, MatcherContractError, ValueError) as exc:
        # Fail closed: no verdict means no routing and no acquisition.
        print(json.dumps({"error": str(exc), "refused": True}))
        return EXIT_REFUSED
    print(json.dumps(asdict(verdict)))
    return EXIT_OK


def _validated_duties(raw: Any) -> List[str]:
    if not isinstance(raw, list) or not raw:
        raise ValueError("'duties' must be a non-empty list of strings")
    if len(raw) > MAX_DUTIES:
        raise ValueError(f"'duties' holds more than {MAX_DUTIES} entries")
    duties = []
    for item in raw:
        if not isinstance(item, str) or not item.strip():
            raise ValueError("every duty must be a non-empty string")
        duties.append(item.strip())
    return duties


def apply_from_file(
    path: str,
    workspace_root: Optional[str] = None,
    env: Optional[Dict[str, str]] = None,
) -> int:
    """Validate the proposal in ``path`` and run the curator broker for it."""
    root = workspace_root or os.getcwd()
    refusal = acquisition_gate(root, env=env)
    if refusal is not None:
        print(json.dumps({"error": refusal, "refused": True}))
        return EXIT_REFUSED
    try:
        payload = _load_json(path)
        kind = payload.get("kind")
        issue = payload.get("issue")
        if issue is not None and not ISSUE_ID.fullmatch(str(issue)):
            raise ValueError("'issue' must be a plain issue number")
        agent_name = payload.get("agent_name")
        if not isinstance(agent_name, str) or not SNAKE_CASE.fullmatch(agent_name):
            raise ValueError("'agent_name' must be snake_case")
        if kind == "adapt_skill":
            source_name = payload.get("source_name")
            skill_name = payload.get("skill_name")
            if not isinstance(source_name, str) or not source_name.strip():
                raise ValueError("'source_name' must be a non-empty string")
            if not isinstance(skill_name, str) or not SNAKE_CASE.fullmatch(
                str(skill_name).removesuffix(".md")
            ):
                raise ValueError("'skill_name' must be snake_case")
        elif kind == "create_agent":
            title = payload.get("title")
            description = payload.get("description")
            if not isinstance(title, str) or not 0 < len(title) <= MAX_TITLE:
                raise ValueError(f"'title' must be 1..{MAX_TITLE} characters")
            if (
                not isinstance(description, str)
                or not 0 < len(description) <= MAX_DESCRIPTION
            ):
                raise ValueError(f"'description' must be 1..{MAX_DESCRIPTION} characters")
            duties = _validated_duties(payload.get("duties"))
        else:
            raise ValueError("'kind' must be 'adapt_skill' or 'create_agent'")
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        print(json.dumps({"error": str(exc)}))
        return EXIT_BAD_INPUT

    from solomon_harness import curator

    issue_id = str(issue) if issue is not None else None
    if kind == "adapt_skill":
        pr_url = curator.broker_skill(
            root, source_name, skill_name, agent_name, issue_id=issue_id
        )
    else:
        pr_url = curator.broker_agent(
            root, agent_name, title, description, duties, issue_id=issue_id
        )
    print(json.dumps({"pr_url": pr_url, "kind": kind, "agent": agent_name}))
    return EXIT_OK


def run(action: str, file_path: str, workspace_root: Optional[str] = None) -> int:
    """Dispatch for the ``broker`` CLI subcommand."""
    if action == "route":
        return route_from_file(file_path, workspace_root)
    if action == "apply":
        return apply_from_file(file_path, workspace_root)
    print(json.dumps({"error": f"unknown broker action '{action}'"}))
    return EXIT_BAD_INPUT
