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
        """List the open issues. Each row carries a derived ``is_github_issue`` flag: True for a numeric GitHub id, False for a RAID/follow-up tracking row."""
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
        session_id: str,
        agent_name: str,
        task: str,
        messages: List[Any],
        status: str = "active",
        issues: Optional[List[int]] = None,
    ) -> dict:
        """Persist a session (conversation state) for later resume. Status is active or done. Pass the GitHub issue numbers the session worked on as issues; each becomes a worked_on edge so resume is a graph query (ADR-0018)."""
        return service.save_session(
            session_id, agent_name, task, messages, status, issues
        )

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
        summary: str = "",
    ) -> dict:
        """Record a handoff between agents. The summary is a short "what this stage did" text persisted on the row so a resume survives worktree teardown."""
        return service.log_handoff(
            sender, recipient, contract_type, contract_path, status, summary
        )

    @server.tool()
    def update_handoff_status(handoff_id: str, status: str) -> dict:
        """Move a handoff along its lifecycle (open, accepted, done)."""
        return service.update_handoff_status(handoff_id, status)

    @server.tool()
    def get_latest_activity() -> dict:
        """Return the most recent session or handoff, for resume."""
        return service.get_latest_activity()

    @server.tool()
    def get_backend_status() -> dict:
        """Report which memory backend serves this session: surrealdb, or the sqlite fallback with the degradation reason."""
        return service.get_backend_status()

    @server.tool()
    def get_claim_holder(issue_number: int) -> dict:
        """Best-effort read of an issue's claim holder from the memory mirror (ADR-0027).

        Answers "who is working issue N" without a live git fetch. The mirror
        is queryability only -- the git claim ref stays the authority for any
        claim decision; use `solomon-harness claim status` for the
        authoritative read.
        """
        from solomon_harness import claim

        holder = claim.get_claim_holder(harness_dir, issue_number)
        return {"issue": issue_number, "holder": holder}

    @server.tool()
    def relate(
        edge: str, from_id: str, to_id: str, fields: Optional[dict] = None
    ) -> dict:
        """Create a graph edge from_id -[edge]-> to_id (SurrealDB-only)."""
        return service.relate(edge, from_id, to_id, **(fields or {}))

    @server.tool()
    def block_issue(
        blocker_github_id: str, blocked_github_id: str, reason: Optional[str] = None
    ) -> dict:
        """Record that one issue blocks another (SurrealDB-only)."""
        return service.block_issue(blocker_github_id, blocked_github_id, reason)

    @server.tool()
    def supersede_decision(
        new_decision_id: str, old_decision_id: str, reason: Optional[str] = None
    ) -> dict:
        """Record that a newer decision supersedes an older one (SurrealDB-only)."""
        return service.supersede_decision(new_decision_id, old_decision_id, reason)

    @server.tool()
    def assign_issue_to_milestone(milestone_id: str, github_id: str) -> dict:
        """Place an issue under a milestone (SurrealDB-only)."""
        return service.assign_issue_to_milestone(milestone_id, github_id)

    @server.tool()
    def link_session_handoff(session_id: str, handoff_id: str) -> dict:
        """Record that a session produced a handoff (SurrealDB-only)."""
        return service.link_session_handoff(session_id, handoff_id)

    @server.tool()
    def decision_addresses_issue(decision_id: str, github_id: str) -> dict:
        """Record that a decision addresses an issue (SurrealDB-only)."""
        return service.decision_addresses_issue(decision_id, github_id)

    @server.tool()
    def issues_blocking(github_id: str) -> dict:
        """List the issues that this issue blocks (SurrealDB-only)."""
        return service.issues_blocking(github_id)

    @server.tool()
    def issues_blocked_by(github_id: str) -> dict:
        """List the issues that block this issue (SurrealDB-only)."""
        return service.issues_blocked_by(github_id)

    @server.tool()
    def milestone_issues(milestone_id: str) -> dict:
        """List the issues contained by a milestone (SurrealDB-only)."""
        return service.milestone_issues(milestone_id)

    @server.tool()
    def supersedes_chain(decision_id: str) -> dict:
        """List the chain of decisions a decision supersedes, nearest first (SurrealDB-only)."""
        return service.supersedes_chain(decision_id)

    @server.tool()
    def record_metric(
        name: str,
        value: float,
        tags: Optional[dict] = None,
        at: Optional[str] = None,
    ) -> dict:
        """Append one timeseries metric point (works on both backends)."""
        return service.record_metric(name, value, tags, at)

    @server.tool()
    def query_metric(
        name: str,
        since: Optional[str] = None,
        until: Optional[str] = None,
        limit: int = 100,
    ) -> dict:
        """Return metric points for a name, most recent first (works on both backends)."""
        return service.query_metric(name, since, until, limit)

    @server.tool()
    def aggregate_metric(
        name: str, bucket: str = "day", agg: str = "count", since: Optional[str] = None
    ) -> dict:
        """Aggregate a metric into time buckets (SurrealDB-only)."""
        return service.aggregate_metric(name, bucket, agg, since)

    @server.tool()
    def loop_run_throughput(bucket: str = "day", since: Optional[str] = None) -> dict:
        """Loop-run counts per time bucket (SurrealDB-only)."""
        return service.loop_run_throughput(bucket, since)

    @server.tool()
    def loop_run_failure_rate(since: Optional[str] = None) -> dict:
        """Failure rate of loop runs as total, failures, and rate (SurrealDB-only)."""
        return service.loop_run_failure_rate(since)

    @server.tool()
    def semantic_search(
        query: str, k: int = 5, category: Optional[str] = None, ef: int = 64
    ) -> dict:
        """Return the k memory entries nearest to a query (SurrealDB-only)."""
        return service.semantic_search(query, k, category, ef)

    return server


def main() -> None:
    build_server().run()


if __name__ == "__main__":
    main()
