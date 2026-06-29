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
        if "adapt skill" in proposal.drift_description.lower():
            gh_cmd.extend(["--reviewer", "security"])
        
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


def _pinned_clone(source: dict, dest: str) -> None:
    import subprocess
    url = source.get("url")
    pin = source.get("pin") or source.get("commit")
    if not url:
        raise ValueError("Source has no URL")
    if not pin:
        raise ValueError("SHA-pin mandatory (HEAD == recorded SHA; reject unpinned default-branch clone)")
        
    os.makedirs(dest, exist_ok=True)
    subprocess.run(["git", "init", "-q", dest], check=True)
    subprocess.run(["git", "-C", dest, "remote", "add", "origin", url], check=True)
    subprocess.run(["git", "-C", dest, "fetch", "--depth", "1", "origin", pin], check=True, capture_output=True)
    subprocess.run(["git", "-C", dest, "checkout", "-q", pin], check=True, capture_output=True)
    
    proc = subprocess.run(["git", "-C", dest, "rev-parse", "HEAD"], check=True, capture_output=True, text=True)
    current_head = proc.stdout.strip()
    if current_head != pin:
        raise ValueError(f"HEAD mismatch: checked out {current_head}, expected {pin}")


def adapt_skill_content(text: str, name: str) -> str:
    import re
    # Remove emojis
    emoji_pattern = re.compile(
        r"[\U00010000-\U0010ffff\u2600-\u27bf\u200d\ufe0f]",
        flags=re.UNICODE
    )
    text = emoji_pattern.sub("", text)
    
    # Remove AI cliches
    cliches = {
        r"\bdelve\b": "examine",
        r"\bleverage\b": "use",
        r"\btestament to\b": "evidence of",
        r"\bfeel free to\b": "you may",
        r"\bdive into\b": "explore",
        r"\bin summary\b": "concluding",
        r"\bfurthermore\b": "also",
        r"\bmoreover\b": "additionally",
        r"\btapestry\b": "structure",
        r"\bdelving\b": "examining",
    }
    for pattern, repl in cliches.items():
        text = re.sub(pattern, repl, text, flags=re.IGNORECASE)
        
    lines = text.splitlines()
    title = name.replace("_", " ").replace("-", " ").title()
    has_title = False
    for line in lines[:5]:
        if line.strip().startswith("# "):
            has_title = True
            break
            
    if not has_title:
        text = f"# {title}\n\n" + text
        
    if "## Common pitfalls" not in text:
        text = text.rstrip() + "\n\n## Common pitfalls\n\n- Stray configuration and redundant abstractions.\n"
    if "## Definition of done" not in text:
        text = text.rstrip() + "\n\n## Definition of done\n\n- [ ] The skill conforms to the house style.\n"
        
    return text


def validate_and_install_skill(src_path: str, agent_skills_dir: str, name: str, workspace_root: str) -> str:
    import shutil
    src_realpath = os.path.realpath(src_path)
    is_packaged = os.path.basename(src_path) == "SKILL.md"
    if is_packaged:
        target_path = os.path.join(agent_skills_dir, name)
    else:
        target_path = os.path.join(agent_skills_dir, f"{name}.md")
        
    target_realpath = os.path.realpath(target_path)
    agents_realpath = os.path.realpath(os.path.join(workspace_root, "agents"))
    if not target_realpath.startswith(agents_realpath):
        raise ValueError(f"Confinement violation: target path {target_realpath} is outside {agents_realpath}")
        
    if os.path.islink(src_path) or os.path.islink(target_path):
        raise ValueError("Symlinks are rejected")
        
    if is_packaged:
        src_dir = os.path.dirname(src_path)
        for root_dir, _, filenames in os.walk(src_dir):
            if os.path.islink(root_dir):
                raise ValueError("Symlinks are rejected")
            for filename in filenames:
                filepath = os.path.join(root_dir, filename)
                if os.path.islink(filepath):
                    raise ValueError("Symlinks are rejected")
                    
                size = os.path.getsize(filepath)
                if size > 256 * 1024:
                    raise ValueError(f"Skill file size exceeds the 256 KiB cap: {filepath}")
                    
                rel_to_src = os.path.relpath(filepath, src_dir)
                is_in_scripts = rel_to_src.startswith("scripts/") or "scripts" in rel_to_src.split(os.sep)
                has_script_ext = any(filename.endswith(ext) for ext in [".sh", ".py", ".js", ".pl", ".rb", ".php", ".bin", ".exe"])
                is_executable = (os.stat(filepath).st_mode & 0o111) != 0
                
                if is_in_scripts or has_script_ext or is_executable:
                    quarantine_root = os.path.join(workspace_root, ".solomon", "quarantine")
                    quarantine_path = os.path.join(quarantine_root, name)
                    if os.path.isdir(quarantine_path):
                        shutil.rmtree(quarantine_path)
                    os.makedirs(quarantine_root, exist_ok=True)
                    shutil.copytree(src_dir, quarantine_path)
                    raise ValueError(f"Security risk: skill contains scripts/executables. Quarantined at: {quarantine_path}")
    else:
        size = os.path.getsize(src_path)
        if size > 256 * 1024:
            raise ValueError(f"Skill file size exceeds the 256 KiB cap: {src_path}")
            
    os.makedirs(agent_skills_dir, exist_ok=True)
    if is_packaged:
        src_dir = os.path.dirname(src_path)
        if os.path.isdir(target_path):
            shutil.rmtree(target_path)
        os.makedirs(target_path, exist_ok=True)
        for item in os.listdir(src_dir):
            s_item = os.path.join(src_dir, item)
            t_item = os.path.join(target_path, item)
            if item != "SKILL.md":
                if os.path.isdir(s_item):
                    shutil.copytree(s_item, t_item)
                else:
                    shutil.copy2(s_item, t_item)
        with open(os.path.join(src_dir, "SKILL.md"), "r", encoding="utf-8") as f:
            content = f.read(256 * 1024)
        adapted = adapt_skill_content(content, name)
        with open(os.path.join(target_path, "SKILL.md"), "w", encoding="utf-8") as f:
            f.write(adapted)
        return target_path
    else:
        with open(src_path, "r", encoding="utf-8") as f:
            content = f.read(256 * 1024)
        adapted = adapt_skill_content(content, name)
        with open(target_path, "w", encoding="utf-8") as f:
            f.write(adapted)
        return target_path


def broker_skill(
    workspace_root: str,
    source_name: str,
    skill_name: str,
    agent_name: str,
    gh_runner: Optional[Callable[[List[str]], Any]] = None
) -> str:
    """Acquires a skill from an allowlisted external source, adapts it, and installs it via apply_proposal."""
    import tempfile
    from solomon_harness.skills import load_sources, discover_skill_files
    
    sources = load_sources(workspace_root)
    source = sources.get(source_name)
    if not source:
        raise ValueError(f"Source {source_name} is not in the allowlist")
        
    with tempfile.TemporaryDirectory() as tmp:
        _pinned_clone(source, tmp)
        
        skills = discover_skill_files(tmp)
        if skill_name not in skills:
            raise ValueError(f"Skill {skill_name} not found in source {source_name}")
            
        src_path = skills[skill_name]
        
        def edit_callback(agent_dir: str) -> None:
            agent_skills_dir = os.path.join(agent_dir, "skills")
            validate_and_install_skill(src_path, agent_skills_dir, skill_name, workspace_root)
            
        proposal = Proposal(
            agent=agent_name,
            drift_description=f"Adapt skill {skill_name} from {source_name}",
            sources=(source_name, "baseline"),
            rationale=f"Acquiring missing capability '{skill_name}' via broker",
            decision_id=None
        )
        return apply_proposal(proposal, edit_callback, workspace_root, gh_runner)

