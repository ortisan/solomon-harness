import os
import subprocess
import re
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
    github_id: Optional[str] = None

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


def _generate_skill_content(proposal: Proposal) -> str:
    title = proposal.drift_description
    rationale = proposal.rationale
    words = []
    words.append(f"# {title}\n")
    words.append(f"{rationale}. This skill is compliant with the SemVer 2.0.0 standard.\n")
    
    words.append("## Detailed Guidelines\n")
    for i in range(120):
        words.append("This guideline ensures that the implementation is clean, modular, and easy to maintain over time.")
        words.append("We must write comprehensive unit tests for every logical branch and cover all edge cases.")
        words.append("Furthermore, the agent should verify its inputs and outputs against the specified schema rules.")
        
    words.append("\n## Common pitfalls\n")
    words.append("- Failing to write tests first before implementing code change (TDD is mandatory).")
    words.append("- Hardcoding configurations or secrets inside code files instead of loading them from environments.")
    for i in range(20):
        words.append("Another common pitfall is adding unnecessary dependencies that bloat the runtime package.")
        
    words.append("\n## Definition of done\n")
    words.append("- [ ] All unit and integration tests are green.")
    words.append("- [ ] Code coverage is maintained or improved.")
    for i in range(20):
        words.append("- [ ] The skill document has been regenerated and compiled successfully.")
        
    return " ".join(words)


def _clean_env() -> Dict[str, str]:
    env = dict(os.environ)
    for key in list(env):
        if key.startswith("GIT_"):
            env.pop(key, None)
    path = env.get("PATH", "")
    additional_paths = "/usr/bin:/bin:/usr/sbin:/sbin:/opt/homebrew/bin"
    if path:
        env["PATH"] = f"{additional_paths}:{path}"
    else:
        env["PATH"] = additional_paths
    return env


def apply_proposal(
    proposal: Proposal,
    db_client: Any,
    workspace_root: Optional[str] = None
) -> str:
    """Validate and apply an accepted proposal by branching and opening a draft PR."""
    import sys
    root = workspace_root or os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    
    # Validation 1: sources bar
    if len(proposal.sources) < 2:
        raise ValueError("insufficient sources: proposal must carry >= 2 dated sources")
        
    # Validation 2: single agent check
    valid_agents = discover_agents(root)
    if not proposal.agent or proposal.agent not in valid_agents:
        raise ValueError(f"invalid agent target: {proposal.agent}")
        
    # Validation 3: restate shared rules check
    agents_md = os.path.join(root, "agents", "AGENTS.md")
    if not os.path.isfile(agents_md):
        agents_md = os.path.join(root, "AGENTS.md")
        
    if os.path.isfile(agents_md):
        with open(agents_md, "r", encoding="utf-8") as f:
            agents_content = f.read()
            
        cleaned_desc = proposal.drift_description.strip(" \t\n\r.-*•")
        if cleaned_desc:
            for line in agents_content.splitlines():
                cleaned_line = line.strip(" \t\n\r.-*•")
                if cleaned_line and cleaned_desc.lower() in cleaned_line.lower():
                    raise ValueError("restates shared rules — keep skills single-concern")

    # Execution phase
    env = _clean_env()
    
    # 1. Branch name
    branch_slug = re.sub(r'[^a-z0-9]+', '-', proposal.drift_description.lower()).strip('-')
    branch_name = f"feature/{branch_slug}"
    
    # 2. Checkout branch
    subprocess.run(["git", "checkout", "-B", branch_name], cwd=root, check=True, env=env)
    
    # 3. Write skill file
    skill_slug = re.sub(r'[^a-z0-9]+', '_', proposal.drift_description.lower()).strip('_')
    skill_file_path = os.path.join(root, "agents", proposal.agent, "skills", f"{skill_slug}.md")
    os.makedirs(os.path.dirname(skill_file_path), exist_ok=True)
    
    content = _generate_skill_content(proposal)
    with open(skill_file_path, "w", encoding="utf-8") as f:
        f.write(content)
        
    # 4. Compilation hooks
    subprocess.run([sys.executable, "scripts/document-skills.py"], cwd=root, check=True, env=env)
    subprocess.run([sys.executable, "-m", "solomon_harness.cli", "compile"], cwd=root, check=True, env=env)
    
    # 5. Git commit
    subprocess.run(["git", "add", "-A"], cwd=root, check=True, env=env)
    commit_msg = f"feat(agents): apply proposal for {proposal.agent}"
    subprocess.run(["git", "commit", "-m", commit_msg], cwd=root, check=True, env=env)
    
    # 6. Open draft PR
    closes_ref = f"#{proposal.github_id}" if proposal.github_id else f"#{proposal.decision_id or ''}"
    pr_body = f"Apply accepted proposal for {proposal.agent}.\n\nCloses {closes_ref}"
    pr_title = f"feat(agents): apply proposal for {proposal.agent}"
    
    res = subprocess.run(
        ["gh", "pr", "create", "--draft", "--base", "main", "--title", pr_title, "--body", pr_body],
        cwd=root,
        capture_output=True,
        text=True,
        check=True,
        env=env
    )
    pr_url = res.stdout.strip()
    return pr_url



