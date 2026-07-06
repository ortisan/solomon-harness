import os
import shutil
from dataclasses import dataclass, field
from typing import List, Optional, Callable, Dict, Any, Tuple
from solomon_harness.agent_selection import discover_agents

# Proposal kind for a skill acquired through the external broker. Brokered
# proposals carry single-source provenance instead of the two-source evidence
# floor, so the kind is matched in several places; keep it a single constant.
ADAPT_SKILL_KIND = "adapt_skill"

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
    kind: Optional[str] = None

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
    import re
    root = workspace_root or os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    # Validation 1: provenance floor. Brokered adapt_skill proposals carry
    # genuine single-source provenance (<source>@<full-sha>) instead of the
    # two-source evidence floor; require that shape rather than exempting the
    # kind outright, so no caller can bypass evidence with an empty source set.
    if proposal.kind == ADAPT_SKILL_KIND:
        if len(proposal.sources) != 1 or not re.fullmatch(
            r"\S+@(?:[0-9a-f]{40}|[0-9a-f]{64})", proposal.sources[0]
        ):
            raise ValueError(
                "adapt_skill proposal requires one <source>@<full-sha> provenance entry"
            )
    elif len(proposal.sources) < 2:
        raise ValueError("evidence regressed")

    # Validation 2: target exactly one agent
    if proposal.kind == "create_agent":
        if not proposal.agent or os.sep in proposal.agent or "/" in proposal.agent or ".." in proposal.agent:
            raise ValueError("targets multiple or invalid agent")
    else:
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

    # slugify branch name
    slug = re.sub(r'[^a-zA-Z0-9\-]', '-', proposal.drift_description.lower())
    slug = re.sub(r'-+', '-', slug).strip('-')
    branch_name = f"feature/{slug}"
    
    actual_package_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    env = os.environ.copy()
    env["PYTHONPATH"] = f"{actual_package_root}{os.path.pathsep}{root}"
    
    # checkout branch idempotently: re-acquiring the same skill must not abort
    # on an existing branch (#105). Force-reset (-B) is forbidden because it
    # clobbers in-flight work, so detect the branch and reuse it instead.
    branch_exists = subprocess.run(
        ["git", "rev-parse", "--verify", "--quiet", f"refs/heads/{branch_name}"],
        cwd=root, env=env, capture_output=True,
    ).returncode == 0
    if branch_exists:
        subprocess.run(["git", "checkout", branch_name], cwd=root, env=env, check=True)
    else:
        subprocess.run(["git", "-C", root, "checkout", "-b", branch_name], cwd=root, env=env, check=True)
    
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
        
        # add and commit. On an idempotent re-run the reinstall produces no
        # diff, so skip the commit rather than fail on an empty commit.
        subprocess.run(["git", "add", "."], cwd=root, env=env, check=True)
        status = subprocess.run(
            ["git", "status", "--porcelain"], cwd=root, env=env, capture_output=True, text=True, check=True
        )
        if status.stdout.strip():
            commit_msg = f"feat(agents): apply proposal for {proposal.agent} closes #{proposal.decision_id or ''}"
            subprocess.run(["git", "commit", "-m", commit_msg], cwd=root, env=env, check=True)

        # gh pr create
        title = f"feat(agents): apply proposal for {proposal.agent}"
        body = f"Closes #{proposal.decision_id or ''}"
        gh_cmd = ["gh", "pr", "create", "--draft", "--base", "main", "--title", title, "--body", body]
        if proposal.kind == ADAPT_SKILL_KIND:
            gh_cmd.extend(["--reviewer", "security"])
        
        if gh_runner:
            res = gh_runner(gh_cmd)
            pr_url = res.stdout.strip() if hasattr(res, "stdout") and res.stdout else "https://github.com/mock/pr"
        elif os.environ.get("MOCK_GH") == "1":
            pr_url = f"https://github.com/ortisan/solomon-harness/pull/mock-{proposal.decision_id}"
        else:
            # Resolve gh from PATH instead of hardcoding one; a fixed
            # "/opt/homebrew/bin:/usr/bin:/bin" breaks Intel Mac Homebrew
            # (/usr/local/bin), most non-Debian Linux, and macOS GitHub Actions
            # runners, where gh lives elsewhere. Fail with a clear, actionable
            # error rather than letting subprocess raise a bare FileNotFoundError.
            gh_path = shutil.which("gh")
            if not gh_path:
                raise RuntimeError(
                    "gh CLI not found on PATH; install and authenticate the "
                    "GitHub CLI (https://cli.github.com) before applying a proposal."
                )
            gh_cmd[0] = gh_path
            gh_env = os.environ.copy()
            gh_env["PYTHONPATH"] = root
            try:
                res = subprocess.run(gh_cmd, cwd=root, capture_output=True, text=True, env=gh_env, check=True)
                pr_url = res.stdout.strip()
            except subprocess.CalledProcessError as e:
                if "already exists" in e.stderr or "already exists" in e.stdout:
                    view_cmd = ["gh", "pr", "view", branch_name, "--json", "url", "--template", "{{.url}}"]
                    view_res = subprocess.run(view_cmd, cwd=root, capture_output=True, text=True, env=gh_env)
                    if view_res.returncode == 0 and view_res.stdout.strip():
                        pr_url = view_res.stdout.strip()
                    else:
                        raise
                else:
                    raise
            
        try:
            from solomon_harness.tools.database_client import DatabaseClient
            import datetime
            with DatabaseClient(harness_dir=root) as db:
                title = f"ADR-Broker: Applied {proposal.kind} for {proposal.agent}"
                if proposal.decision_id:
                    title += f" for #{proposal.decision_id}"
                outcome = f"PR: {pr_url}\nBranch: {branch_name}"
                db.log_decision(
                    title=title,
                    rationale=proposal.rationale,
                    outcome=outcome,
                    author="practice_curator",
                    branch=branch_name,
                    commit_sha="",
                )
                
                if proposal.decision_id:
                    date_str = datetime.date.today().isoformat()
                    contract_dir = os.path.join(root, ".solomon", "handoffs")
                    os.makedirs(contract_dir, exist_ok=True)
                    contract_path = os.path.join(contract_dir, f"issue-{proposal.decision_id}-start-to-review.md")
                    
                    content = f"""# Handoff: start -> review · issue #{proposal.decision_id}
- Date: {date_str} · Author: practice_curator
- Issue: #{proposal.decision_id} · Branch: {branch_name} · PR: {pr_url}

## What this stage did
Acquired missing capability via capability broker: {proposal.drift_description}. Scaffolds and files created/updated, compiled, and draft PR opened.

## Artifacts (open only if needed)
- PR: {pr_url}
- Branch: {branch_name}

## Acceptance criteria status
Ready for review and verification.

## Input for the next stage (review)
Verify the newly created/adapted agent or skill on the PR branch.

## Open questions / risks
None.
"""
                    with open(contract_path, "w", encoding="utf-8") as f:
                        f.write(content)
                    
                    db.log_handoff(
                        sender="practice_curator",
                        recipient="qa",
                        contract_type="pull_request",
                        contract_path=f".solomon/handoffs/issue-{proposal.decision_id}-start-to-review.md",
                        status="ready",
                        summary=f"Acquired capability: {proposal.drift_description}",
                    )
        except Exception as db_exc:
            import logging
            logging.warning(f"Could not log broker decisions to database: {db_exc}")

        return pr_url
    except Exception:
        raise


def _pinned_clone(source: dict, dest: str) -> None:
    import subprocess
    import re
    url = source.get("url")
    pin = source.get("pin") or source.get("commit")
    if not url:
        raise ValueError("Source has no URL")
    # Scheme allowlist blocks ext::/fd:: and other RCE transports.
    if not url.startswith(("https://", "ssh://", "git@", "file://")):
        raise ValueError("disallowed source URL scheme")
    if not pin:
        raise ValueError("SHA-pin mandatory (HEAD == recorded SHA; reject unpinned default-branch clone)")
    # A full hex SHA blocks --upload-pack= option injection and short/branch pins.
    if not re.fullmatch(r"[0-9a-f]{40}|[0-9a-f]{64}", pin):
        raise ValueError("pin must be a full commit SHA")

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


# Inert file types a packaged skill may contain. Anything else is treated as
# active content and quarantined: an allowlist fails closed, unlike a denylist
# that an attacker can sidestep with an unlisted extension.
_ALLOWED_SKILL_EXTS = {
    ".md", ".txt", ".json", ".yaml", ".yml", ".toml",
    ".rst", ".csv", ".png", ".jpg", ".jpeg", ".gif", ".svg",
}
_SCRIPT_DIRS = {"scripts", "bin", "hooks", ".githooks"}
_SKILL_SIZE_CAP = 256 * 1024


def _quarantine_skill(src_dir: str, workspace_root: str, name: str, reason: str) -> None:
    """Copy a rejected packaged skill to the quarantine area, then raise.

    The copy preserves symlinks (symlinks=True) so quarantining never
    dereferences a link out of the source tree.
    """
    import shutil
    quarantine_root = os.path.join(workspace_root, ".solomon", "quarantine")
    quarantine_path = os.path.join(quarantine_root, name)
    if os.path.isdir(quarantine_path):
        shutil.rmtree(quarantine_path)
    os.makedirs(quarantine_root, exist_ok=True)
    shutil.copytree(src_dir, quarantine_path, symlinks=True)
    raise ValueError(f"{reason}. Quarantined at: {quarantine_path}")


def _scan_packaged_skill(current_dir: str, src_dir: str, in_script_dir: bool, name: str, workspace_root: str) -> None:
    """Recursively validate a packaged skill tree before it is copied.

    Uses os.scandir, not os.walk: os.walk does not descend symlinked
    directories, so files behind one are never scanned yet are still copied by
    shutil.copytree, which dereferences them. This visits every entry at every
    depth and rejects any symlink (file or directory) before it can be
    followed, so the scan and the copy traverse the identical tree. Files are
    held to the inert-type allowlist, the executable bit, the script-directory
    denylist, and the size cap.
    """
    with os.scandir(current_dir) as entries:
        for entry in sorted(entries, key=lambda e: e.name):
            if entry.is_symlink():
                raise ValueError("Symlinks are rejected")
            if entry.is_dir(follow_symlinks=False):
                child_in_script_dir = in_script_dir or entry.name in _SCRIPT_DIRS
                _scan_packaged_skill(entry.path, src_dir, child_in_script_dir, name, workspace_root)
                continue
            stat = entry.stat(follow_symlinks=False)
            if stat.st_size > _SKILL_SIZE_CAP:
                raise ValueError(f"Skill file size exceeds the 256 KiB cap: {entry.path}")
            if in_script_dir or (stat.st_mode & 0o111) != 0:
                _quarantine_skill(src_dir, workspace_root, name, "Security risk: skill contains scripts/executables")
            if os.path.splitext(entry.name)[1].lower() not in _ALLOWED_SKILL_EXTS:
                _quarantine_skill(
                    src_dir, workspace_root, name,
                    f"Security risk: skill contains a disallowed file type: {entry.name}",
                )


def validate_and_install_skill(src_path: str, agent_skills_dir: str, name: str, workspace_root: str) -> str:
    import shutil
    # Reject a name that could escape the skills directory before it is joined
    # into any path.
    if os.path.isabs(name) or os.sep in name or "/" in name or ".." in name:
        raise ValueError("invalid skill name")

    is_packaged = os.path.basename(src_path) == "SKILL.md"
    if is_packaged:
        target_path = os.path.join(agent_skills_dir, name)
    else:
        target_path = os.path.join(agent_skills_dir, f"{name}.md")

    target_realpath = os.path.realpath(target_path)
    agents_realpath = os.path.realpath(os.path.join(workspace_root, "agents"))
    if target_realpath != agents_realpath and not target_realpath.startswith(agents_realpath + os.sep):
        raise ValueError(f"Confinement violation: target path {target_realpath} is outside {agents_realpath}")

    if os.path.islink(src_path) or os.path.islink(target_path):
        raise ValueError("Symlinks are rejected")

    if is_packaged:
        src_dir = os.path.dirname(src_path)
        _scan_packaged_skill(src_dir, src_dir, False, name, workspace_root)
    else:
        size = os.path.getsize(src_path)
        if size > _SKILL_SIZE_CAP:
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
    gh_runner: Optional[Callable[[List[str]], Any]] = None,
    issue_id: Optional[str] = None
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
            sources=(f"{source_name}@{source.get('pin')}",),
            rationale=f"Acquiring missing capability '{skill_name}' via broker",
            decision_id=issue_id,
            kind=ADAPT_SKILL_KIND,
        )
        return apply_proposal(proposal, edit_callback, workspace_root, gh_runner)


def broker_agent(
    workspace_root: str,
    agent_name: str,
    title: str,
    description: str,
    duties: List[str],
    gh_runner: Optional[Callable[[List[str]], Any]] = None,
    issue_id: Optional[str] = None
) -> str:
    """Acquires a new agent by scaffolding its directories, files, and default skill,

    registering it, compiling the integrations, and opening a draft PR via apply_proposal.
    """
    import os
    import re
    from solomon_harness.bootstrap import scaffold_new_agent

    # Validate agent name strictly to prevent path traversal/confinement escape
    if not re.match(r"^[a-z0-9_]+$", agent_name):
        raise ValueError("Agent name must be alphanumeric and underscores only (snake_case)")

    def edit_callback(agent_dir: str) -> None:
        # Confinement check
        target_realpath = os.path.realpath(agent_dir)
        agents_realpath = os.path.realpath(os.path.join(workspace_root, "agents"))
        if target_realpath != agents_realpath and not target_realpath.startswith(agents_realpath + os.sep):
            raise ValueError(f"Confinement violation: target path {target_realpath} is outside {agents_realpath}")

        # Delegate directly to scaffold_new_agent
        scaffold_new_agent(
            workspace_root,
            agent_name,
            description,
            title=title,
            duties=duties,
        )

    proposal = Proposal(
        agent=agent_name,
        drift_description=f"Create agent {agent_name}",
        sources=(f"demand@{agent_name}", f"template@{agent_name}"),
        rationale=f"Creating missing agent {agent_name} for capability",
        decision_id=issue_id,
        kind="create_agent",
    )
    return apply_proposal(proposal, edit_callback, workspace_root, gh_runner)


