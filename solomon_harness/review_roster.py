"""Select conditional review lenses from a PR's changed paths.

The Review stage always runs the three mandatory gates (qa, security,
software_architect). This module adds up to ``CONDITIONAL_LENS_CAP`` domain
specialists chosen deterministically from the paths the PR touches, so a UI
change gets frontend eyes and a schema change gets the dba without inflating
every review. Pure and gh-free by design: the command file pipes
``gh pr diff <n> --name-only`` in, and tests exercise the mapping directly.

CLI:
    python -m solomon_harness.review_roster path [path ...]
    gh pr diff 42 --name-only | python -m solomon_harness.review_roster
"""

import sys
from typing import Callable, Iterable, List, Optional, Tuple

MANDATORY_LENSES = ("qa", "security", "software_architect")

# Two extra lenses keep a review bounded: beyond the three mandatory gates,
# five parallel reviewers stop adding signal and start adding latency.
CONDITIONAL_LENS_CAP = 2

_CREDENTIAL_MARKERS = ("auth", "token", "credential", "secret")
_INSTRUMENTATION_MARKERS = ("telemetry", "metrics", "tracing")


def _basename(path: str) -> str:
    return path.rsplit("/", 1)[-1]


def _is_credential(path: str) -> bool:
    name = _basename(path).lower()
    return any(marker in name for marker in _CREDENTIAL_MARKERS)


def _is_database(path: str) -> bool:
    return (
        "database_client" in path
        or path.endswith(".surql")
        or "/migrations/" in path
    )


def _is_deploy(path: str) -> bool:
    name = _basename(path)
    return (
        path.startswith(".github/workflows/")
        or path.startswith("scripts/git-hooks/")
        or name.startswith("docker-compose")
        or name.startswith("Dockerfile")
    )


def _is_loop_mechanics(path: str) -> bool:
    # The run-log (loop_log.py) is loop mechanics, not observability: the
    # loop_ prefix deliberately outranks the instrumentation rule below.
    return _basename(path).startswith("loop_") or path.endswith(
        "solomon_harness/workflows.py"
    )


def _is_ui(path: str) -> bool:
    return path.startswith("ui/")


def _is_instrumentation(path: str) -> bool:
    name = _basename(path).lower()
    return name == "healthcheck.py" or any(
        marker in name for marker in _INSTRUMENTATION_MARKERS
    )


def _is_agent_content(path: str) -> bool:
    return path.startswith("agents/") and (
        "/skills/" in path or path.endswith("persona.md")
    )


def _is_docs(path: str) -> bool:
    return path.startswith("docs/") and path.endswith(".md")


# Priority order: the riskiest, most specific domain first, so the cap keeps
# the lenses with the most to say about the change. Every lens here must be a
# deployable agent (agents/<name>/agents/<name>.md) — the roster-match rule of
# ADR-0019, guarded by a fitness test. ux_designer joins for ui/ surface paths
# once its agent definition lands (feature/ux-designer-agent).
_RULES: Tuple[Tuple[Callable[[str], bool], str], ...] = (
    (_is_credential, "auth_engineer"),
    (_is_database, "dba"),
    (_is_deploy, "sre"),
    (_is_loop_mechanics, "loop_engineer"),
    (_is_ui, "frontend"),
    (_is_instrumentation, "observability"),
    (_is_agent_content, "practice_curator"),
    (_is_docs, "documenter"),
)


def select_lenses(
    paths: Iterable[str], cap: int = CONDITIONAL_LENS_CAP
) -> List[str]:
    """Return the conditional domain lenses for the changed paths.

    Deterministic, deduplicated, priority-ordered, and capped; never returns a
    mandatory gate. An empty result means the review runs with exactly the
    three mandatory gates.
    """
    path_list = list(paths)
    selected = [
        lens
        for matches, lens in _RULES
        if lens not in MANDATORY_LENSES and any(matches(p) for p in path_list)
    ]
    return selected[:cap]


def main(argv: Optional[List[str]] = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    paths = args or [line.strip() for line in sys.stdin if line.strip()]
    for lens in select_lenses(paths):
        print(lens)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
