import os
from dataclasses import dataclass, field
from typing import List, Optional, Callable, Dict, Any, Tuple
from solomon_harness.agent_selection import discover_agents

@dataclass(frozen=True)
class DriftMatch:
    agent: str
    drift_description: str
    sources: List[str] = field(default_factory=list)
    rationale: str = ""

@dataclass
class Proposal:
    agent: str
    drift_description: str
    sources: Tuple[str, ...]
    rationale: str
    decision_id: Optional[str] = None

@dataclass
class SweepResult:
    proposals: List[Proposal]
    needs_evidence: List[Dict[str, Any]]

SweepAnalyzer = Callable[[str, str, str], Optional[DriftMatch]]

def sweep_fleet(
    baseline: str,
    analyzer: SweepAnalyzer,
    db_client: Any,
    workspace_root: Optional[str] = None
) -> SweepResult:
    """Sweep all agents in the fleet, identify drift against the baseline, and emit proposals."""
    root = workspace_root or os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    agent_names = discover_agents(root)
    
    proposals: List[Proposal] = []
    needs_evidence: List[Dict[str, Any]] = []
    
    for agent_name in sorted(agent_names):
        agent_dir = os.path.join(root, "agents", agent_name)
        
        # Read profile
        profile_path = os.path.join(agent_dir, "agents", f"{agent_name}.md")
        content_parts = []
        if os.path.isfile(profile_path):
            with open(profile_path, "r", encoding="utf-8") as f:
                content_parts.append(f.read())
                
        # Read persona
        persona_path = os.path.join(agent_dir, "persona.md")
        if os.path.isfile(persona_path):
            with open(persona_path, "r", encoding="utf-8") as f:
                content_parts.append(f.read())
                
        # Read skills
        skills_dir = os.path.join(agent_dir, "skills")
        if os.path.isdir(skills_dir):
            for skill_name in sorted(os.listdir(skills_dir)):
                skill_path = os.path.join(skills_dir, skill_name)
                if skill_name.endswith(".md") and os.path.isfile(skill_path):
                    with open(skill_path, "r", encoding="utf-8") as f:
                        content_parts.append(f.read())
                        
        agent_content = "\n\n".join(content_parts)
        
        match = analyzer(agent_name, agent_content, baseline)
        if match is not None:
            if len(match.sources) >= 2:
                # Log decision in project memory
                title = f"Propose gap for {agent_name}: {match.drift_description}"
                decision_id = db_client.log_decision(
                    title=title,
                    rationale=match.rationale,
                    outcome="Proposed gap issue creation",
                    author="practice_curator",
                    branch="",
                    commit_sha=""
                )
                proposal = Proposal(
                    agent=agent_name,
                    drift_description=match.drift_description,
                    sources=tuple(match.sources),
                    rationale=match.rationale,
                    decision_id=str(decision_id) if decision_id else None
                )
                proposals.append(proposal)
            else:
                needs_evidence.append({
                    "agent": agent_name,
                    "drift_description": match.drift_description,
                    "sources": match.sources,
                    "rationale": match.rationale
                })
                
    return SweepResult(proposals=proposals, needs_evidence=needs_evidence)
