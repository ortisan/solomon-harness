from typing import List, Optional

def build_agent(
    workspace_root: str,
    name: str,
    description: str,
    title: Optional[str] = None,
    duties: Optional[List[str]] = None,
) -> None:
    """Delegated scaffolding logic for creating a new agent."""
    from solomon_harness.bootstrap import scaffold_new_agent
    scaffold_new_agent(
        workspace_root,
        name,
        description,
        title=title,
        duties=duties,
    )
