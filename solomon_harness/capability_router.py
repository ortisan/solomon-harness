"""Route a free-text demand to the best-fit existing agent, or report a capability gap.

Slice A of the practice_curator capability-broker (ADR-0008). This module is READ-ONLY:
it loads the agent catalog and constructs a verdict; it never writes anything, opens no
network socket, and instantiates no model. The demand->agent match is supplied by an
injected matcher port (the host LLM in production, a deterministic stub in tests), so the
core stays deterministic and unit-testable.

The verdict is either a RouteVerdict (an existing agent serves the demand) or a
GapVerdict naming the missing capability and the suggested next action (adapt a skill into
the nearest agent, or create a new agent). The gap verdict pre-wires the acquisition
slices (#47 adapt, #48/#49 create).
"""

import os
from dataclasses import dataclass, field
from typing import Callable, List, Optional, Tuple, Union

from solomon_harness.agent_selection import discover_agents
from solomon_harness.layout import HarnessPaths, find_workspace_root

ADAPT_SKILL = "adapt_skill"
CREATE_AGENT = "create_agent"


class CatalogError(Exception):
    """The agent catalog could not be read or is empty; routing fails closed."""


class MatcherContractError(Exception):
    """The matcher returned an invalid response (e.g. an agent name not in the catalog)."""



@dataclass(frozen=True)
class Agent:
    """One catalog entry: an agent name and its one-line role description."""

    name: str
    description: str


@dataclass(frozen=True)
class Match:
    """What an injected matcher returns; the core turns it into a verdict.

    ``agent`` set -> a route. ``agent`` None -> a gap: ``nearest_agent`` set means the
    demand maps to an existing agent that only lacks a skill (adapt); ``nearest_agent``
    None means no agent fits (create).
    """

    agent: Optional[str] = None
    rationale: str = ""
    alternatives: List[str] = field(default_factory=list)
    missing_capability: Optional[str] = None
    nearest_agent: Optional[str] = None


@dataclass(frozen=True)
class RouteVerdict:
    agent: str
    rationale: str
    alternatives: Tuple[str, ...] = ()
    kind: str = "route"


@dataclass(frozen=True)
class GapVerdict:
    missing_capability: str
    suggested_action: str
    rationale: str
    nearest_agent: Optional[str] = None
    kind: str = "gap"


Verdict = Union[RouteVerdict, GapVerdict]
# The injected match port: given a demand and the read-only catalog, return a Match.
# The host LLM provides this in production; tests pass a deterministic stub.
Matcher = Callable[[str, List[Agent]], Match]


def _default_workspace_root() -> str:
    return os.fspath(find_workspace_root(__file__))


def _role_description(role_path: str) -> str:
    """First non-heading, non-empty line of a role file (its advertised summary)."""
    try:
        if os.path.getsize(role_path) > 1024 * 1024:
            return ""
        with open(role_path, "r", encoding="utf-8") as f:
            in_skipped_line = False
            while True:
                line = f.readline(8192)
                if not line:
                    break
                is_continuation = in_skipped_line
                if line.endswith("\n"):
                    in_skipped_line = False
                else:
                    in_skipped_line = True
                if is_continuation:
                    continue
                stripped = line.strip()
                if stripped and not stripped.startswith("#"):
                    return stripped
                if stripped.startswith("#"):
                    in_skipped_line = not line.endswith("\n")
    except OSError:
        return ""
    return ""



def load_catalog(workspace_root: Optional[str] = None) -> List[Agent]:
    """Load the agent catalog read-only: every agent with a role file, sorted by name.

    Raises CatalogError when the agents directory is missing or holds no discoverable
    agent, so the caller fails closed instead of routing against an empty catalog.
    """
    root = workspace_root or _default_workspace_root()
    real_root = os.path.realpath(root)
    agents_dir = os.path.realpath(HarnessPaths(real_root).resolve_agents())
    names = discover_agents(real_root)
    if not names:
        raise CatalogError(f"no agents discovered under {agents_dir}")
    catalog = []
    for name in sorted(names):
        role = os.path.join(agents_dir, name, "agents", f"{name}.md")
        real_role = os.path.realpath(role)
        if not real_role.startswith(agents_dir + os.sep):
            raise CatalogError(f"path confinement violation: {role} resolves outside {agents_dir}")
        curr = role
        while curr and curr != agents_dir and curr != os.path.dirname(curr):
            if os.path.islink(curr):
                raise CatalogError(f"symlink rejected: {curr}")
            curr = os.path.dirname(curr)
        catalog.append(Agent(name=name, description=_role_description(real_role)))
    return catalog



def route(demand: str, matcher: Matcher, workspace_root: Optional[str] = None) -> Verdict:
    """Resolve ``demand`` against the catalog into a RouteVerdict or a GapVerdict.

    ``matcher(demand, catalog) -> Match`` is the only match path (host LLM in production,
    a stub in tests); this function performs no network or model call and writes nothing.
    Deterministic given a fixed matcher and catalog. Fails closed (CatalogError) on an
    unreadable or empty catalog.
    """
    if not demand or not str(demand).strip():
        raise ValueError("demand must be a non-empty string")
    catalog = load_catalog(workspace_root)
    names = {a.name for a in catalog}

    match = matcher(demand, catalog)

    if match.agent is not None:
        if match.agent not in names:
            raise MatcherContractError(
                f"matcher returned agent '{match.agent}' that is not in the catalog"
            )
        lines = (match.rationale or "").strip().splitlines()
        rationale = lines[0] if lines else ""
        alternatives = tuple(a for a in match.alternatives if a in names and a != match.agent)
        return RouteVerdict(agent=match.agent, rationale=rationale, alternatives=alternatives)

    # Gap: a missing capability must be named so the acquisition slices can act.
    if not match.missing_capability:
        raise ValueError("a gap match must name the missing_capability")
    nearest = match.nearest_agent if match.nearest_agent in names else None
    suggested = ADAPT_SKILL if nearest else CREATE_AGENT
    return GapVerdict(
        missing_capability=match.missing_capability,
        suggested_action=suggested,
        rationale=(match.rationale or "").strip(),
        nearest_agent=nearest,
    )
