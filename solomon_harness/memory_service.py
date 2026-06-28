"""Project-memory service.

A thin, JSON-serializable wrapper over DatabaseClient. The MCP server
(solomon_harness/mcp_server.py) registers these methods as tools so the host
tools (Claude Code, Codex, Gemini CLI, Copilot) can read and write the project
memory. The service is directly testable without the MCP SDK installed.
"""

import os
from typing import Any, Dict, List, Optional


def resolve_harness_dir(start: Optional[str] = None) -> str:
    """Walks up from start (or cwd) to the directory containing the solomon_harness
    package, so the memory store is the project-root one regardless of cwd."""
    current = os.path.abspath(start or os.getcwd())
    while current and current != os.path.dirname(current):
        if os.path.isdir(os.path.join(current, "solomon_harness")):
            return current
        current = os.path.dirname(current)
    return os.path.abspath(start or os.getcwd())


class MemoryService:
    """Reads and writes the project memory. Holds one DatabaseClient for its
    lifetime; each method returns a plain dict."""

    def __init__(
        self, harness_dir: Optional[str] = None, db_path: Optional[str] = None
    ) -> None:
        from solomon_harness.tools.database_client import DatabaseClient

        resolved = harness_dir if harness_dir is not None else resolve_harness_dir()
        self.client = DatabaseClient(harness_dir=resolved, db_path=db_path)

    def close(self) -> None:
        self.client.close()

    def save_decision(
        self,
        title: str,
        rationale: str,
        outcome: str,
        author: str,
        branch: str = "main",
        commit_sha: str = "",
    ) -> Dict[str, Any]:
        decision_id = self.client.log_decision(
            title=title,
            rationale=rationale,
            outcome=outcome,
            author=author,
            branch=branch,
            commit_sha=commit_sha,
        )
        return {"decision_id": decision_id}

    def get_decision(self, decision_id: Any) -> Dict[str, Any]:
        return {"decision": self.client.get_decision(decision_id)}

    def save_memory(self, key: str, value: str, category: str) -> Dict[str, Any]:
        self.client.save_memory(key, value, category)
        return {"ok": True, "key": key}

    def get_memory(self, key: str) -> Dict[str, Any]:
        return {"value": self.client.get_memory(key)}

    def log_issue(
        self,
        github_id: str,
        title: str,
        type_: str,
        status: str,
        milestone_id: Optional[Any] = None,
    ) -> Dict[str, Any]:
        self.client.log_issue(github_id, title, type_, status, milestone_id)
        return {"ok": True, "github_id": github_id}

    def get_open_issues(self) -> Dict[str, List[Dict[str, Any]]]:
        return {"issues": self.client.get_open_issues()}

    def get_issue(self, github_id: str) -> Dict[str, Any]:
        return {"issue": self.client.get_issue(github_id)}

    def create_milestone(
        self, title: str, description: str, due_date: str, state: str
    ) -> Dict[str, Any]:
        milestone_id = self.client.create_milestone(
            title=title, description=description, due_date=due_date, state=state
        )
        return {"milestone_id": milestone_id}

    def save_backtest(
        self,
        strategy_name: str,
        sharpe_ratio: float,
        max_drawdown: float,
        profit_factor: float,
        parameters: str,
        dataset: str,
        commit_sha: str = "",
    ) -> Dict[str, Any]:
        backtest_id = self.client.save_backtest(
            strategy_name=strategy_name,
            sharpe_ratio=sharpe_ratio,
            max_drawdown=max_drawdown,
            profit_factor=profit_factor,
            parameters=parameters,
            dataset=dataset,
            commit_sha=commit_sha,
        )
        return {"backtest_id": backtest_id}

    def save_session(
        self, session_id: str, agent_name: str, task: str, messages: List[Any]
    ) -> Dict[str, Any]:
        self.client.save_session(session_id, agent_name, task, messages)
        return {"ok": True, "session_id": session_id}

    def get_session(self, session_id: str) -> Dict[str, Any]:
        return {"session": self.client.get_session(session_id)}

    def log_handoff(
        self,
        sender: str,
        recipient: str,
        contract_type: str,
        contract_path: str,
        status: str,
    ) -> Dict[str, Any]:
        handoff_id = self.client.log_handoff(
            sender, recipient, contract_type, contract_path, status
        )
        return {"handoff_id": handoff_id}

    def get_latest_activity(self) -> Dict[str, Any]:
        return {"activity": self.client.get_latest_activity()}
