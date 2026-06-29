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


def apply_proposal(
    proposal: Proposal,
    edit_callback: Callable[[str], None],
    workspace_root: Optional[str] = None,
    gh_runner: Optional[Callable[[List[str]], Any]] = None
) -> str:
    """Apply an accepted proposal to an agent by branching, editing, compiling, committing, and opening a draft PR."""
    root = workspace_root or os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    
    # Validation 1: sources >= 2
    if len(proposal.sources) < 2:
        raise ValueError("evidence regressed")
        
    # Validation 2: target exactly one agent
    agent_names = discover_agents(root)
    if not proposal.agent or proposal.agent not in agent_names:
        raise ValueError("targets multiple or invalid agent")
        
    # Validation 3: rule duplicate detection
    agents_md_path = os.path.join(root, "agents", "AGENTS.md")
    if os.path.isfile(agents_md_path):
        with open(agents_md_path, "r", encoding="utf-8") as f:
            agents_rules = f.read().lower()
        for line in agents_rules.splitlines():
            line_clean = line.strip().lstrip("-*#").rstrip(".:!").strip()
            if len(line_clean) > 20 and line_clean in proposal.drift_description.lower():
                raise ValueError("restates shared rules — keep skills single-concern")
                
    # Run git and process commands
    import sys
    import subprocess
    import re
    
    # slugify branch name
    slug = re.sub(r'[^a-zA-Z0-9\-]', '-', proposal.drift_description.lower())
    slug = re.sub(r'-+', '-', slug).strip('-')
    branch_name = f"feature/{slug}"
    
    actual_package_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    env = os.environ.copy()
    env["PYTHONPATH"] = f"{actual_package_root}{os.path.pathsep}{root}"
    
    # checkout branch
    subprocess.run(["git", "checkout", "-b", branch_name], cwd=root, env=env, check=True)
    
    try:
        # edit agent files
        agent_dir = os.path.join(root, "agents", proposal.agent)
        edit_callback(agent_dir)
        
        # document-skills.py
        doc_script = os.path.join(root, "scripts", "document-skills.py")
        if os.path.isfile(doc_script):
            subprocess.run([sys.executable, doc_script], cwd=root, env=env, check=True)
            
        # solomon compile
        subprocess.run([sys.executable, "-m", "solomon_harness.cli", "compile"], cwd=root, env=env, check=True)
        
        # add and commit
        subprocess.run(["git", "add", "."], cwd=root, env=env, check=True)
        commit_msg = f"feat(agents): apply proposal for {proposal.agent} closes #{proposal.decision_id or ''}"
        subprocess.run(["git", "commit", "-m", commit_msg], cwd=root, env=env, check=True)
        
        # gh pr create
        title = f"feat(agents): apply proposal for {proposal.agent}"
        body = f"Closes #{proposal.decision_id or ''}"
        gh_cmd = ["gh", "pr", "create", "--draft", "--base", "main", "--title", title, "--body", body]
        
        if gh_runner:
            res = gh_runner(gh_cmd)
            pr_url = res.stdout.strip() if hasattr(res, "stdout") and res.stdout else "https://github.com/mock/pr"
        elif os.environ.get("MOCK_GH") == "1":
            pr_url = f"https://github.com/ortisan/solomon-harness/pull/mock-{proposal.decision_id}"
        else:
            # Clean environment for gh command
            gh_env = os.environ.copy()
            gh_env["PATH"] = "/opt/homebrew/bin:/usr/bin:/bin"
            gh_env["PYTHONPATH"] = root
            res = subprocess.run(gh_cmd, cwd=root, capture_output=True, text=True, env=gh_env, check=True)
            pr_url = res.stdout.strip()
            
        return pr_url
    except Exception:
        raise

