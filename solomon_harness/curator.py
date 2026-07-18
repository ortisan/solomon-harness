import os
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Callable, Dict, Any, Tuple
from solomon_harness.agent_selection import discover_agents
from solomon_harness.layout import (
    HarnessPaths,
    PathConfinementError,
    confined_path,
)

# The secure git-fetch and filesystem-confinement primitives live in the
# acquisition chokepoint (#108); the broker uses them but no longer owns them.
from solomon_harness.skill_acquisition import _pinned_clone, validate_and_install_skill

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


def _reconcile_host_adapters(root: str) -> Any:
    """Keep managed consumers transactional and source dogfood direct."""
    paths = HarnessPaths(root)
    if paths.manifest.is_file():
        from solomon_harness.install_layout import compile_project_adapters

        return compile_project_adapters(root)

    from solomon_harness.host_adapters import compile_adapters

    return compile_adapters(root)

def sweep_fleet(
    baseline: str,
    analyzer: SweepAnalyzer,
    db_client: Any,
    workspace_root: Optional[str] = None
) -> SweepResult:
    """Sweep all agents in the fleet, identify drift against the baseline, and emit proposals."""
    root = workspace_root or os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    paths = HarnessPaths(root)
    agents_dir = os.fspath(confined_path(paths.root, paths.resolve_agents()))
    agent_names = discover_agents(root)
    
    proposals: List[Proposal] = []
    needs_evidence: List[Dict[str, Any]] = []
    
    for agent_name in sorted(agent_names):
        agent_dir = os.path.join(agents_dir, agent_name)
        
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
    requested_root = workspace_root or os.path.dirname(
        os.path.dirname(os.path.abspath(__file__))
    )
    paths = HarnessPaths(requested_root)
    root = os.fspath(paths.root)
    agents_root = confined_path(paths.root, paths.resolve_agents())

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
    agents_md_path = os.fspath(confined_path(paths.root, paths.resolve_rules()))
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
        agent_dir = confined_path(paths.root, agents_root / proposal.agent)
        edit_callback(os.fspath(agent_dir))
        
        # document-skills.py
        doc_script = os.fspath(
            confined_path(
                paths.root,
                paths.resolve_scripts() / "document-skills.py",
            )
        )
        if os.path.isfile(doc_script):
            subprocess.run(  # noqa: S603 - current interpreter runs a confined repository script
                [sys.executable, doc_script],
                cwd=os.fspath(agents_root.parent),
                env=env,
                check=True,
            )
            
        # Reconcile Claude, AGY, and Codex. Installed consumers run through the
        # manifest transaction; the source checkout compiles dogfood directly.
        compile_result = _reconcile_host_adapters(root)
        if compile_result.conflicts:
            print(
                "Preserved conflicting host adapter files: "
                + ", ".join(compile_result.conflicts)
            )
        
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
        # Every brokered acquisition gets the security reviewer: an adapted
        # skill and a new agent's persona/duties both become trusted
        # instruction content for future sessions. Plain drift proposals
        # (no kind) keep the default reviewer set.
        if proposal.kind in (ADAPT_SKILL_KIND, "create_agent"):
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
            head_sha = ""
            try:
                head_sha = subprocess.run(
                    ["git", "rev-parse", "HEAD"], cwd=root, check=True,
                    capture_output=True, text=True,
                ).stdout.strip()
            except (subprocess.SubprocessError, OSError):
                pass
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
                    commit_sha=head_sha,
                )
                
                if proposal.decision_id:
                    date_str = datetime.date.today().isoformat()
                    contract_dir = os.fspath(
                        confined_path(paths.root, paths.handoffs)
                    )
                    os.makedirs(contract_dir, exist_ok=True)
                    contract_path = os.fspath(
                        confined_path(
                            paths.root,
                            os.path.join(
                                contract_dir,
                                f"issue-{proposal.decision_id}-start-to-review.md",
                            ),
                        )
                    )
                    
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
                        contract_path=os.path.relpath(contract_path, root).replace(
                            os.sep, "/"
                        ),
                        status="ready",
                        summary=f"Acquired capability: {proposal.drift_description}",
                    )
        except PathConfinementError:
            raise
        except Exception as db_exc:
            import logging
            logging.warning(f"Could not log broker decisions to database: {db_exc}")

        return pr_url
    except Exception:
        raise


def broker_skill(
    workspace_root: str,
    source_name: str,
    skill_name: str,
    agent_name: str,
    gh_runner: Optional[Callable[[List[str]], Any]] = None,
    issue_id: Optional[str] = None
) -> str:
    """Acquires a skill from an allowlisted external source, adapts it, and installs it via apply_proposal."""
    import re
    import tempfile
    from solomon_harness.skills import load_sources, discover_skill_files

    # issue_id reaches decision titles and the handoff filename; keep it a
    # plain issue number so malformed values never reach disk paths.
    if issue_id is not None and not re.fullmatch(r"[0-9]+", str(issue_id)):
        raise ValueError("issue_id must be a plain issue number")

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
    """Register a new agent directly in an installed consumer harness.

    Agent creation is a human-gated local extension operation. It writes to the
    canonical installed catalog and recompiles native host adapters without
    creating a branch, commit, or pull request. Source-checkout agent changes
    remain normal reviewed development work and are not accepted through this
    broker shortcut.
    """
    import re
    from solomon_harness.install_layout import register_agent_extension

    # Validate agent name strictly to prevent path traversal/confinement escape
    if not re.match(r"^[a-z0-9_]+$", agent_name):
        raise ValueError("Agent name must be alphanumeric and underscores only (snake_case)")

    # issue_id reaches decision titles and the handoff filename; keep it a
    # plain issue number so malformed values never reach disk paths.
    if issue_id is not None and not re.fullmatch(r"[0-9]+", str(issue_id)):
        raise ValueError("issue_id must be a plain issue number")

    from solomon_harness.agent_builder import build_agent

    def register(agent_path: Path) -> None:
        registration_root = agent_path.parents[3]
        build_agent(
            os.fspath(registration_root),
            agent_name,
            description,
            title=title,
            duties=duties,
            reconcile_adapters=False,
        )

    agent_path = register_agent_extension(workspace_root, agent_name, register)
    paths = HarnessPaths(workspace_root)

    # ``gh_runner`` remains in the signature for callers compiled against the
    # reviewed-PR implementation. It is intentionally never invoked here.
    _ = gh_runner
    try:
        from solomon_harness.tools.database_client import DatabaseClient

        with DatabaseClient(harness_dir=os.fspath(paths.root)) as db:
            issue_note = f" for #{issue_id}" if issue_id else ""
            db.log_decision(
                title=f"Capability broker: registered {agent_name}{issue_note}",
                rationale=f"Creating missing agent {agent_name} for capability",
                outcome=(
                    "Mode: direct_registration\n"
                    f"Agent path: {agent_path.relative_to(paths.root).as_posix()}"
                ),
                author="practice_curator",
                branch="",
                commit_sha="",
            )
    except Exception as db_exc:
        import logging

        logging.warning(f"Could not log agent registration to database: {db_exc}")

    return os.fspath(agent_path)
