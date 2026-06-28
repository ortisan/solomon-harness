"""MCP server exposing the project memory.

Gives the host tools (Claude Code, Codex, Gemini CLI, Copilot) tools to read and
write decisions, memory, issues, milestones, backtests, sessions and handoffs,
all backed by solomon_harness/tools/database_client.py.

Run:  python -m solomon_harness.mcp_server
Requires the `mcp` package (declared in pyproject; install with `uv sync`). The
mcp SDK is imported lazily, so this module imports cleanly without it.
"""

import os
from typing import Any, List, Optional

from solomon_harness.memory_service import MemoryService, resolve_harness_dir


def build_server() -> Any:
    """Builds a FastMCP server with the memory tools registered."""
    from mcp.server.fastmcp import FastMCP

    harness_dir = os.environ.get("SOLOMON_HARNESS_DIR") or resolve_harness_dir()
    service = MemoryService(harness_dir=harness_dir)
    server = FastMCP("solomon-memory")

    @server.tool()
    def save_decision(
        title: str,
        rationale: str,
        outcome: str,
        author: str,
        branch: str = "main",
        commit_sha: str = "",
    ) -> dict:
        """Record a decision (an ADR-style entry) in the project memory."""
        return service.save_decision(title, rationale, outcome, author, branch, commit_sha)

    @server.tool()
    def get_decision(decision_id: str) -> dict:
        """Fetch a decision by id."""
        return service.get_decision(decision_id)

    @server.tool()
    def save_memory(key: str, value: str, category: str) -> dict:
        """Store a memory value under a key and category."""
        return service.save_memory(key, value, category)

    @server.tool()
    def get_memory(key: str) -> dict:
        """Fetch a memory value by key."""
        return service.get_memory(key)

    @server.tool()
    def log_issue(
        github_id: str,
        title: str,
        type_: str,
        status: str,
        milestone_id: Optional[str] = None,
    ) -> dict:
        """Create or update an issue (status open or closed)."""
        return service.log_issue(github_id, title, type_, status, milestone_id)

    @server.tool()
    def get_open_issues() -> dict:
        """List the open issues."""
        return service.get_open_issues()

    @server.tool()
    def get_issue(github_id: str) -> dict:
        """Fetch one issue by its github id."""
        return service.get_issue(github_id)

    @server.tool()
    def create_milestone(
        title: str, description: str, due_date: str, state: str
    ) -> dict:
        """Create a milestone."""
        return service.create_milestone(title, description, due_date, state)

    @server.tool()
    def list_milestones() -> dict:
        """List project milestones, most recent first."""
        return service.list_milestones()

    @server.tool()
    def save_release(
        version: str,
        tag: str = "",
        notes: str = "",
        issue_github_id: str = "",
        milestone_id: str = "",
        commit_sha: str = "",
    ) -> dict:
        """Record a delivered release (version, tag, notes, the closed issue and milestone)."""
        return service.save_release(
            version, tag, notes, issue_github_id, milestone_id, commit_sha
        )

    @server.tool()
    def get_release(release_id: str) -> dict:
        """Get a delivered release by id."""
        return service.get_release(release_id)

    @server.tool()
    def list_releases(limit: int = 20) -> dict:
        """List delivered releases, most recent first."""
        return service.list_releases(limit)

    @server.tool()
    def save_backtest(
        strategy_name: str,
        sharpe_ratio: float,
        max_drawdown: float,
        profit_factor: float,
        parameters: str,
        dataset: str,
        commit_sha: str = "",
    ) -> dict:
        """Record a backtest run and its metrics."""
        return service.save_backtest(
            strategy_name,
            sharpe_ratio,
            max_drawdown,
            profit_factor,
            parameters,
            dataset,
            commit_sha,
        )

    @server.tool()
    def save_session(
        session_id: str, agent_name: str, task: str, messages: List[Any]
    ) -> dict:
        """Persist a session (conversation state) for later resume."""
        return service.save_session(session_id, agent_name, task, messages)

    @server.tool()
    def get_session(session_id: str) -> dict:
        """Fetch a session by id."""
        return service.get_session(session_id)

    @server.tool()
    def log_handoff(
        sender: str,
        recipient: str,
        contract_type: str,
        contract_path: str,
        status: str,
    ) -> dict:
        """Record a handoff between agents."""
        return service.log_handoff(sender, recipient, contract_type, contract_path, status)

    @server.tool()
    def get_latest_activity() -> dict:
        """Return the most recent session or handoff, for resume."""
        return service.get_latest_activity()

    return server


def main() -> None:
    build_server().run()


if __name__ == "__main__":
    main()
