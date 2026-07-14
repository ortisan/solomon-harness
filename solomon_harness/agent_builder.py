from typing import List, Optional


def _single_line(value: str, field: str) -> str:
    """Collapse whitespace to one line. The scaffolded files (the AGENTS.md
    roster entry, persona, role profile) are read as trusted instruction
    content by every future session, so a multi-line value could inject new
    instruction sections into the trust root. Defense in depth behind the
    broker CLI's own rejection of structural characters."""
    text = " ".join(str(value).split())
    if not text:
        raise ValueError(f"{field} must not be empty")
    return text


def build_agent(
    workspace_root: str,
    name: str,
    description: str,
    title: Optional[str] = None,
    duties: Optional[List[str]] = None,
) -> None:
    """Delegated scaffolding logic for creating a new agent."""
    from solomon_harness.bootstrap import scaffold_new_agent

    description = _single_line(description, "description")
    if title is not None:
        title = _single_line(title, "title")
    if duties is not None:
        duties = [_single_line(duty, "duty") for duty in duties]
    scaffold_new_agent(
        workspace_root,
        name,
        description,
        title=title,
        duties=duties,
    )
