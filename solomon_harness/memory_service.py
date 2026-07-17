"""Project-memory service.

A thin, JSON-serializable wrapper over DatabaseClient. The MCP server
(solomon_harness/mcp_server.py) registers these methods as tools so the host
tools (Claude Code, Codex, Gemini CLI, Copilot) can read and write the project
memory. The service is directly testable without the MCP SDK installed.
"""

import logging
import os
from typing import TYPE_CHECKING, Any, Dict, List, Optional

if TYPE_CHECKING:
    from solomon_harness.claim import ClaimStore

logger = logging.getLogger(__name__)


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
        self,
        harness_dir: Optional[str] = None,
        db_path: Optional[str] = None,
        claim_store: Optional["ClaimStore"] = None,
    ) -> None:
        from solomon_harness.tools.database_client import DatabaseClient

        resolved = harness_dir if harness_dir is not None else resolve_harness_dir()
        self.client = DatabaseClient(harness_dir=resolved, db_path=db_path)
        if claim_store is None:
            from solomon_harness.claim import GitClaimStore

            claim_store = GitClaimStore(resolved)
        self._claim_store: "ClaimStore" = claim_store

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

    def get_backend_status(self) -> Dict[str, Any]:
        """Which backend serves this session's memory, and why, when degraded."""
        return self.client.backend_status()

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
        issues = self.client.get_open_issues()
        try:
            # Numeric ids only; non-numeric rows (RAID/tracking items) are
            # never claimed and always kept.
            numeric_ids = []
            for issue in issues:
                try:
                    numeric_ids.append(int(str(issue.get("github_id"))))
                except (TypeError, ValueError):
                    continue
            # One shared claim filter -- the SAME port method
            # github.list_open_issues uses -- so the two scan read paths can
            # never diverge on how a claim is judged (a future filter fix
            # lands in exactly one place). Defaults to GitClaimStore, which
            # delegates to claim.filter_unclaimed; a caller can inject a
            # different ClaimStore via the constructor.
            unclaimed_ids = set(self._claim_store.filter_unclaimed(numeric_ids))

            def _keep(issue: Dict[str, Any]) -> bool:
                try:
                    return int(str(issue.get("github_id"))) in unclaimed_ids
                except (TypeError, ValueError):
                    return True  # non-numeric tracking rows are never claimed

            issues = [issue for issue in issues if _keep(issue)]
        except Exception as exc:  # noqa: BLE001 - degrade to unfiltered, but log (item 8)
            logger.warning(
                "claim-aware issue filtering degraded (%s); returning the "
                "unfiltered issue list.",
                exc,
            )
        return {"issues": issues}

    def get_issue(self, github_id: str) -> Dict[str, Any]:
        return {"issue": self.client.get_issue(github_id)}

    def create_milestone(
        self, title: str, description: str, due_date: str, state: str
    ) -> Dict[str, Any]:
        milestone_id = self.client.create_milestone(
            title=title, description=description, due_date=due_date, state=state
        )
        return {"milestone_id": milestone_id}

    def list_milestones(self) -> Dict[str, List[Dict[str, Any]]]:
        return {"milestones": self.client.list_milestones()}

    def ensure_milestone(
        self, title: str, description: str = "", due_date: str = ""
    ) -> Dict[str, Any]:
        milestone_id = self.client.ensure_milestone(
            title=title, description=description, due_date=due_date
        )
        return {"milestone_id": milestone_id}

    def close_milestone(self, title: str) -> Dict[str, Any]:
        milestone_id = self.client.close_milestone(title=title)
        return {"milestone_id": milestone_id, "state": "closed"}

    def save_release(
        self,
        version: str,
        tag: str = "",
        notes: str = "",
        issue_github_id: str = "",
        milestone_id: str = "",
        commit_sha: str = "",
    ) -> Dict[str, Any]:
        release_id = self.client.save_release(
            version=version,
            tag=tag or None,
            notes=notes or None,
            issue_github_id=issue_github_id or None,
            milestone_id=milestone_id or None,
            commit_sha=commit_sha or None,
        )
        return {"release_id": release_id}

    def get_release(self, release_id: str) -> Dict[str, Any]:
        return {"release": self.client.get_release(release_id)}

    def list_releases(self, limit: int = 20) -> Dict[str, List[Dict[str, Any]]]:
        return {"releases": self.client.list_releases(limit=limit)}

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
        self,
        session_id: str,
        agent_name: str,
        task: str,
        messages: List[Any],
        status: str = "active",
        issues: Optional[List[int]] = None,
    ) -> Dict[str, Any]:
        self.client.save_session(
            session_id, agent_name, task, messages, status=status, issues=issues
        )
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
        summary: str = "",
    ) -> Dict[str, Any]:
        handoff_id = self.client.log_handoff(
            sender, recipient, contract_type, contract_path, status, summary=summary
        )
        return {"handoff_id": handoff_id}

    def update_handoff_status(self, handoff_id: Any, status: str) -> Dict[str, Any]:
        result = self.client.update_handoff_status(handoff_id, status)
        return {"ok": result is not None, "handoff_id": result}

    def get_latest_activity(self) -> Dict[str, Any]:
        return {"activity": self.client.get_latest_activity()}

    # --- Graph (write) -------------------------------------------------------

    def relate(
        self, edge: str, from_id: str, to_id: str, **fields: Any
    ) -> Dict[str, Any]:
        edge_id = self.client.relate(edge, from_id, to_id, **fields)
        return {"edge_id": edge_id}

    def block_issue(
        self,
        blocker_github_id: str,
        blocked_github_id: str,
        reason: Optional[str] = None,
    ) -> Dict[str, Any]:
        edge_id = self.client.block_issue(blocker_github_id, blocked_github_id, reason)
        return {"edge_id": edge_id}

    def supersede_decision(
        self,
        new_decision_id: str,
        old_decision_id: str,
        reason: Optional[str] = None,
    ) -> Dict[str, Any]:
        edge_id = self.client.supersede_decision(
            new_decision_id, old_decision_id, reason
        )
        return {"edge_id": edge_id}

    def assign_issue_to_milestone(
        self, milestone_id: str, github_id: str
    ) -> Dict[str, Any]:
        edge_id = self.client.assign_issue_to_milestone(milestone_id, github_id)
        return {"edge_id": edge_id}

    def link_session_handoff(
        self, session_id: str, handoff_id: str
    ) -> Dict[str, Any]:
        edge_id = self.client.link_session_handoff(session_id, handoff_id)
        return {"edge_id": edge_id}

    def decision_addresses_issue(
        self, decision_id: str, github_id: str
    ) -> Dict[str, Any]:
        edge_id = self.client.decision_addresses_issue(decision_id, github_id)
        return {"edge_id": edge_id}

    # --- Graph (read) --------------------------------------------------------

    def issues_blocking(self, github_id: str) -> Dict[str, List[Dict[str, Any]]]:
        return {"issues": self.client.issues_blocking(github_id)}

    def issues_blocked_by(self, github_id: str) -> Dict[str, List[Dict[str, Any]]]:
        return {"issues": self.client.issues_blocked_by(github_id)}

    def milestone_issues(self, milestone_id: str) -> Dict[str, List[Dict[str, Any]]]:
        return {"issues": self.client.milestone_issues(milestone_id)}

    def supersedes_chain(self, decision_id: str) -> Dict[str, List[Dict[str, Any]]]:
        return {"decisions": self.client.supersedes_chain(decision_id)}

    # --- Timeseries ----------------------------------------------------------

    def record_metric(
        self,
        name: str,
        value: float,
        tags: Optional[Dict[str, Any]] = None,
        at: Optional[str] = None,
    ) -> Dict[str, Any]:
        metric_id = self.client.record_metric(name, value, tags=tags, at=at)
        return {"metric_id": metric_id}

    def query_metric(
        self,
        name: str,
        since: Optional[str] = None,
        until: Optional[str] = None,
        limit: int = 100,
    ) -> Dict[str, List[Dict[str, Any]]]:
        return {
            "results": self.client.query_metric(
                name, since=since, until=until, limit=limit
            )
        }

    def aggregate_metric(
        self,
        name: str,
        bucket: str = "day",
        agg: str = "count",
        since: Optional[str] = None,
    ) -> Dict[str, List[Dict[str, Any]]]:
        return {
            "buckets": self.client.aggregate_metric(
                name, bucket=bucket, agg=agg, since=since
            )
        }

    def loop_run_throughput(
        self, bucket: str = "day", since: Optional[str] = None
    ) -> Dict[str, List[Dict[str, Any]]]:
        return {
            "throughput": self.client.loop_run_throughput(bucket=bucket, since=since)
        }

    def loop_run_failure_rate(self, since: Optional[str] = None) -> Dict[str, Any]:
        return {"failure_rate": self.client.loop_run_failure_rate(since=since)}

    # --- Vector --------------------------------------------------------------

    def semantic_search(
        self, query: str, k: int = 5, category: Optional[str] = None, ef: int = 64
    ) -> Dict[str, List[Dict[str, Any]]]:
        return {
            "results": self.client.semantic_search(
                query, k=k, category=category, ef=ef
            )
        }
