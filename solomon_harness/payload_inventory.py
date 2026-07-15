"""Positive source inventory for repository-local Solomon installations.

The wheel builder and project installer consume this module instead of walking
source trees broadly. A file enters the payload only through one of the
structural contracts below; local credentials, notes, caches, and other
unregistered files are invisible even when placed below an allowed directory.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Iterable


WORKFLOW_NAMES = (
    "bug",
    "idea",
    "issue",
    "loop",
    "refine",
    "release",
    "review",
    "scan-arch",
    "scan-dedup",
    "start",
    "workflow",
)

_CONVENTION_FILES = (
    "docs/loop-engineering.md",
    "docs/release-policy.md",
    "docs/solomon-workflow.md",
)
_SCAFFOLD_FILES = (
    "docs/adrs/0000-adr-template.md",
    "docs/adrs/README.md",
    "docs/specs/0000-spec-template.md",
    "docs/specs/README.md",
)
_GITHUB_FILES = (
    ".github/ISSUE_TEMPLATE/bug_report.md",
    ".github/ISSUE_TEMPLATE/config.yml",
    ".github/ISSUE_TEMPLATE/feature_conception.md",
    ".github/ISSUE_TEMPLATE/future_ideas.md",
    ".github/ISSUE_TEMPLATE/quant_model_hypothesis.md",
    ".github/PULL_REQUEST_TEMPLATE.md",
)
_SCRIPT_FILES = (
    "scripts/bootstrap-agent.sh",
    "scripts/check-adr-gate.py",
    "scripts/check-adr-unique.py",
    "scripts/check-skill-depth.py",
    "scripts/document-skills.py",
    "scripts/generate-integrations.py",
    "scripts/git-hooks/commit-msg",
    "scripts/git-hooks/pre-commit",
    "scripts/scrum-master.sh",
    "scripts/setup-git-hooks.sh",
    "scripts/spawn-agent.sh",
    "scripts/spec-lint.py",
    "scripts/test-git-hooks.sh",
    "scripts/test-spawn-agent.sh",
    "scripts/validate-agents.py",
    "scripts/validate-templates.py",
    "scripts/validate-workflows.py",
    "scripts/wiki-sync.sh",
)
_TEMPLATE_FILES = (
    "solomon_harness/templates/AGENTS.md.template",
    "solomon_harness/templates/CLAUDE.md.template",
    "solomon_harness/templates/KANBAN.md.template",
    "solomon_harness/templates/harness/.agent/config.json",
    "solomon_harness/templates/harness/main.py",
    "solomon_harness/templates/wiki/Business-Requirements.md.template",
    "solomon_harness/templates/wiki/Commands-Reference.md.template",
    "solomon_harness/templates/wiki/Design-System.md.template",
    "solomon_harness/templates/wiki/Features.md.template",
    "solomon_harness/templates/wiki/Home.md.template",
    "solomon_harness/templates/wiki/Quick-Start.md.template",
    "solomon_harness/templates/wiki/Release-Notes.md.template",
    "solomon_harness/templates/wiki/Release.md.template",
    "solomon_harness/templates/wiki/Technical-Documentation.md.template",
    "solomon_harness/templates/wiki/_Sidebar.md.template",
)
_LEGACY_PAYLOAD_PROOF_FILES = (
    "solomon_harness/legacy_payloads/v0.11.0.tsv",
    "solomon_harness/legacy_payloads/v0.11.0-main.tsv",
)
_PACKAGE_PYTHON_FILES = (
    "solomon_harness/__init__.py",
    "solomon_harness/__main__.py",
    "solomon_harness/adapter_ownership.py",
    "solomon_harness/agent_builder.py",
    "solomon_harness/agent_selection.py",
    "solomon_harness/bootstrap.py",
    "solomon_harness/broker_cli.py",
    "solomon_harness/capability_router.py",
    "solomon_harness/claim.py",
    "solomon_harness/cli.py",
    "solomon_harness/cockpit_read.py",
    "solomon_harness/curator.py",
    "solomon_harness/dates.py",
    "solomon_harness/digest.py",
    "solomon_harness/engine_adapters.py",
    "solomon_harness/evals.py",
    "solomon_harness/frontmatter.py",
    "solomon_harness/github.py",
    "solomon_harness/healthcheck.py",
    "solomon_harness/host_adapter_agy.py",
    "solomon_harness/host_adapter_claude.py",
    "solomon_harness/host_adapter_codex.py",
    "solomon_harness/host_adapter_common.py",
    "solomon_harness/host_adapter_contract.py",
    "solomon_harness/home.py",
    "solomon_harness/host_adapters.py",
    "solomon_harness/host_hooks.py",
    "solomon_harness/install_global.py",
    "solomon_harness/install_layout.py",
    "solomon_harness/install_lock.py",
    "solomon_harness/install_transaction.py",
    "solomon_harness/layout.py",
    "solomon_harness/loop_budget.py",
    "solomon_harness/loop_lock.py",
    "solomon_harness/loop_log.py",
    "solomon_harness/loop_policy.py",
    "solomon_harness/mcp_server.py",
    "solomon_harness/memory.py",
    "solomon_harness/memory_service.py",
    "solomon_harness/notify.py",
    "solomon_harness/payload_inventory.py",
    "solomon_harness/prereqs.py",
    "solomon_harness/release.py",
    "solomon_harness/review_roster.py",
    "solomon_harness/skills.py",
    "solomon_harness/subprocess_env.py",
    "solomon_harness/tools/__init__.py",
    "solomon_harness/tools/database_client.py",
    "solomon_harness/voice.py",
    "solomon_harness/wiki_bootstrap.py",
    "solomon_harness/workflows.py",
    "solomon_harness/worktree.py",
)
_ROOT_PAYLOAD_FILES = (
    "docker-compose.yml",
    "pyproject.toml",
    "skill-sources.json",
    "uv.lock",
)
_SDIST_METADATA_FILES = (
    "AGENTS.md",
    "AGY.md",
    "CHANGELOG.md",
    "CLAUDE.md",
    "MANIFEST.in",
    "README.md",
    "setup.py",
)
_AGENT_ENTRY = re.compile(r"^- `([a-z][a-z0-9_]*)` —", re.MULTILINE)
_SKILL_LINK = re.compile(r"\(skills/([a-zA-Z0-9_./-]+\.md)\)")


class PayloadInventoryError(RuntimeError):
    """Raised when a required or selected payload source is unsafe."""


def _safe_relative(relative: str | Path) -> Path:
    path = Path(relative)
    if path.is_absolute() or not path.parts or ".." in path.parts:
        raise PayloadInventoryError(f"invalid payload path: {relative}")
    return path


def _add_file(
    result: set[Path],
    root: Path,
    relative: str | Path,
    *,
    required: bool = True,
) -> None:
    path = _safe_relative(relative)
    source = root / path
    if source.is_symlink():
        raise PayloadInventoryError(f"symlinks are not allowed in the payload: {path}")
    cursor = source.parent
    while cursor != root:
        if cursor.is_symlink():
            raise PayloadInventoryError(f"symlinks are not allowed in the payload path: {path}")
        cursor = cursor.parent
    if not source.is_file():
        if required:
            raise PayloadInventoryError(f"required payload file is unavailable: {path}")
        return
    try:
        source.resolve().relative_to(root)
    except ValueError as exc:
        raise PayloadInventoryError(f"payload source escapes its root: {path}") from exc
    result.add(path)


def _agent_files(root: Path) -> set[Path]:
    result: set[Path] = set()
    rules = Path("agents/AGENTS.md")
    _add_file(result, root, rules)
    text = (root / rules).read_text(encoding="utf-8")
    roster = text.split("## The specialist agents", 1)[-1]
    names = tuple(dict.fromkeys(_AGENT_ENTRY.findall(roster)))
    if not names:
        raise PayloadInventoryError("the specialist roster is empty")

    for name in names:
        base = Path("agents") / name
        role = base / "agents" / f"{name}.md"
        for relative in (
            role,
            base / ".agent" / "config.json",
            base / "main.py",
            base / "persona.md",
        ):
            _add_file(result, root, relative)

        role_text = (root / role).read_text(encoding="utf-8")
        skills = tuple(dict.fromkeys(_SKILL_LINK.findall(role_text)))
        for skill in skills:
            skill_path = _safe_relative(skill)
            if len(skill_path.parts) != 1:
                raise PayloadInventoryError(
                    f"agent skill links must name one Markdown file: {role}: {skill}"
                )
            _add_file(result, root, base / "skills" / skill_path)
    return result


def workflow_files(source_root: str | Path) -> tuple[Path, ...]:
    """Return the complete canonical workflow set, or the legacy source fallback."""

    root = Path(source_root).resolve()
    canonical = Path("solomon_harness/catalog/workflows")
    fallback = Path(".claude/commands")
    base = canonical if (root / canonical).is_dir() else fallback
    result: set[Path] = set()
    for name in WORKFLOW_NAMES:
        _add_file(result, root, base / f"solomon-{name}.md")
    return tuple(sorted(result))


def claude_metadata_files(source_root: str | Path) -> tuple[Path, ...]:
    """Return the exact Claude bridge set used only as host metadata."""

    root = Path(source_root).resolve()
    source = Path(".claude/commands")
    packaged = Path("solomon_harness/host_metadata/claude/commands")
    base = source if (root / source).is_dir() else packaged
    result: set[Path] = set()
    for name in WORKFLOW_NAMES:
        _add_file(result, root, base / f"solomon-{name}.md")
    return tuple(sorted(result))


def package_python_files(source_root: str | Path) -> tuple[Path, ...]:
    """Return the explicit Python module inventory for the runtime package."""

    root = Path(source_root).resolve()
    result: set[Path] = set()
    for relative in _PACKAGE_PYTHON_FILES:
        _add_file(result, root, relative)
    return tuple(sorted(result))


def payload_files(source_root: str | Path) -> tuple[Path, ...]:
    """Return every repository-relative file allowed into the install payload."""

    root = Path(source_root).resolve()
    result = _agent_files(root)

    for relative in (
        *_CONVENTION_FILES,
        *_SCAFFOLD_FILES,
        *_GITHUB_FILES,
        *_SCRIPT_FILES,
        *_TEMPLATE_FILES,
        *_LEGACY_PAYLOAD_PROOF_FILES,
    ):
        _add_file(result, root, relative)
    for relative in _ROOT_PAYLOAD_FILES:
        _add_file(
            result,
            root,
            relative,
            required=relative in {"docker-compose.yml", "pyproject.toml"},
        )

    result.update(package_python_files(root))

    result.update(workflow_files(root))
    result.update(claude_metadata_files(root))
    return tuple(sorted(result))


def source_distribution_files(source_root: str | Path) -> tuple[Path, ...]:
    """Return the minimal positive inventory required to build the sdist/wheel."""

    root = Path(source_root).resolve()
    result = set(payload_files(root))
    for relative in _SDIST_METADATA_FILES:
        _add_file(result, root, relative)
    return tuple(sorted(result))


def files_below(files: Iterable[Path], directory: str | Path) -> tuple[Path, ...]:
    """Return inventory members below ``directory``, relative to that directory."""

    base = _safe_relative(directory)
    result: list[Path] = []
    for relative in files:
        try:
            result.append(relative.relative_to(base))
        except ValueError:
            continue
    return tuple(sorted(result))


__all__ = [
    "PayloadInventoryError",
    "WORKFLOW_NAMES",
    "claude_metadata_files",
    "files_below",
    "package_python_files",
    "payload_files",
    "source_distribution_files",
    "workflow_files",
]
