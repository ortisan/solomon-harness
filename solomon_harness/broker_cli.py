"""CLI surface for the capability broker (ADR-0008/0035): route and gated apply.

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

Free-text fields (title, description, duties) are constrained to single lines
without backticks: they enter the new agent's persona and role files, which
future sessions read as trusted instructions, so structural characters are
rejected at this boundary.

Exit codes: 0 success, 2 bad input (malformed file or failed validation),
3 refused (fail-closed routing error or the human gate).
"""

import json
import os
import re
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, Optional, Tuple

from solomon_harness.capability_router import (
    CatalogError,
    Match,
    MatcherContractError,
    route,
)

SNAKE_CASE = re.compile(r"^[a-z0-9_]+$")
ISSUE_ID = re.compile(r"^[0-9]+$")
MAX_NAME = 64
MAX_TITLE = 200
MAX_DESCRIPTION = 2000
MAX_DUTY = 300
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


def _optional_str(raw: Dict[str, Any], key: str) -> Optional[str]:
    value = raw.get(key)
    if value is not None and not isinstance(value, str):
        raise ValueError(f"'match.{key}' must be a string or null")
    return value


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
        agent=_optional_str(raw, "agent"),
        rationale=str(raw.get("rationale") or ""),
        alternatives=list(alternatives),
        missing_capability=_optional_str(raw, "missing_capability"),
        nearest_agent=_optional_str(raw, "nearest_agent"),
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


def _single_line(payload: Dict[str, Any], key: str, max_len: int) -> str:
    """A bounded, single-line free-text field with no structural characters.

    Newlines and backticks are rejected (not stripped) because these values
    are spliced into agents/AGENTS.md and the persona/role files that future
    sessions read as trusted instructions — a multi-line value could inject
    new instruction sections into the trust root.
    """
    value = payload.get(key)
    if not isinstance(value, str) or not 0 < len(value) <= max_len:
        raise ValueError(f"'{key}' must be a string of 1..{max_len} characters")
    if any(ch in value for ch in ("\n", "\r", "`")):
        raise ValueError(f"'{key}' must be a single line without backticks")
    return " ".join(value.split())


def _snake_name(payload: Dict[str, Any], key: str) -> str:
    value = payload.get(key)
    if (
        not isinstance(value, str)
        or len(value) > MAX_NAME
        or not SNAKE_CASE.fullmatch(value)
    ):
        raise ValueError(f"'{key}' must be snake_case, at most {MAX_NAME} characters")
    return value


@dataclass(frozen=True)
class _ApplyAction:
    """A fully validated acquisition: every field typed and bounded."""

    kind: str
    agent_name: str
    issue_id: Optional[str]
    source_name: str = ""
    skill_name: str = ""
    title: str = ""
    description: str = ""
    duties: Tuple[str, ...] = field(default_factory=tuple)


def _validated_action(payload: Dict[str, Any]) -> _ApplyAction:
    issue = payload.get("issue")
    if issue is not None and not ISSUE_ID.fullmatch(str(issue)):
        raise ValueError("'issue' must be a plain issue number")
    issue_id = str(issue) if issue is not None else None
    agent_name = _snake_name(payload, "agent_name")
    kind = payload.get("kind")
    if kind == "adapt_skill":
        source_name = _single_line(payload, "source_name", MAX_NAME)
        raw_skill = payload.get("skill_name")
        if not isinstance(raw_skill, str):
            raise ValueError("'skill_name' must be a string")
        skill_name = raw_skill.removesuffix(".md")
        if len(skill_name) > MAX_NAME or not SNAKE_CASE.fullmatch(skill_name):
            raise ValueError(
                f"'skill_name' must be snake_case, at most {MAX_NAME} characters"
            )
        return _ApplyAction(
            kind, agent_name, issue_id,
            source_name=source_name, skill_name=skill_name,
        )
    if kind == "create_agent":
        title = _single_line(payload, "title", MAX_TITLE)
        description = _single_line(payload, "description", MAX_DESCRIPTION)
        raw_duties = payload.get("duties")
        if not isinstance(raw_duties, list) or not raw_duties:
            raise ValueError("'duties' must be a non-empty list of strings")
        if len(raw_duties) > MAX_DUTIES:
            raise ValueError(f"'duties' holds more than {MAX_DUTIES} entries")
        duties = tuple(
            _single_line({"duty": duty}, "duty", MAX_DUTY) for duty in raw_duties
        )
        return _ApplyAction(
            kind, agent_name, issue_id,
            title=title, description=description, duties=duties,
        )
    raise ValueError("'kind' must be 'adapt_skill' or 'create_agent'")


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
        action = _validated_action(_load_json(path))
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        print(json.dumps({"error": str(exc)}))
        return EXIT_BAD_INPUT

    from solomon_harness import curator

    result: Dict[str, Any]
    if action.kind == "adapt_skill":
        pr_url = curator.broker_skill(
            root, action.source_name, action.skill_name, action.agent_name,
            issue_id=action.issue_id,
        )
        result = {
            "pr_url": pr_url,
            "kind": action.kind,
            "agent": action.agent_name,
            "mode": "reviewed_pr",
        }
    else:
        agent_path = curator.broker_agent(
            root, action.agent_name, action.title, action.description,
            list(action.duties), issue_id=action.issue_id,
        )
        result = {
            "agent_path": agent_path,
            "kind": action.kind,
            "agent": action.agent_name,
            "mode": "direct_registration",
            "restart_required": True,
        }
    print(json.dumps(result))
    return EXIT_OK


def run(action: str, file_path: str, workspace_root: Optional[str] = None) -> int:
    """Dispatch for the ``broker`` CLI subcommand."""
    if action == "route":
        return route_from_file(file_path, workspace_root)
    if action == "apply":
        return apply_from_file(file_path, workspace_root)
    print(json.dumps({"error": f"unknown broker action '{action}'"}))
    return EXIT_BAD_INPUT
