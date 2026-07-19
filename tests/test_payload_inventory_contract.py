"""Security and completeness contracts for the positive payload inventory."""

from __future__ import annotations

from pathlib import Path

import pytest

from solomon_harness.payload_inventory import (
    PayloadInventoryError,
    WORKFLOW_NAMES,
    claude_metadata_files,
    files_below,
    package_python_files,
    payload_files,
    source_distribution_files,
    workflow_files,
)


SOURCE_ROOT = Path(__file__).resolve().parents[1]


def _write_workflows(root: Path, directory: str) -> tuple[Path, ...]:
    base = root / directory
    base.mkdir(parents=True)
    for name in WORKFLOW_NAMES:
        (base / f"solomon-{name}.md").write_text(f"# {name}\n", encoding="utf-8")
    return tuple(sorted(path.relative_to(root) for path in base.glob("*.md")))


@pytest.mark.unit
def test_repository_payload_and_sdist_are_positive_complete_inventories() -> None:
    package = package_python_files(SOURCE_ROOT)
    payload = payload_files(SOURCE_ROOT)
    distribution = source_distribution_files(SOURCE_ROOT)

    assert package
    assert set(package) <= set(payload) <= set(distribution)
    assert Path("solomon_harness/host_adapter_codex.py") in package
    assert Path("README.md") not in payload
    assert Path("README.md") in distribution
    assert all(path.is_file() for path in (SOURCE_ROOT / item for item in distribution))


@pytest.mark.unit
@pytest.mark.parametrize(
    ("catalog", "expected_count", "release_specific"),
    (
        (
            "v0.11.0.tsv",
            500,
            {"GEMINI.md", "README.md", "docs/solomon-workflow.md"},
        ),
        (
            "v0.11.0-main.tsv",
            537,
            {"AGY.md", ".github/copilot-instructions.md"},
        ),
    ),
)
def test_legacy_catalogs_cover_each_complete_pre_layout_install_profile(
    catalog: str,
    expected_count: int,
    release_specific: set[str],
) -> None:
    lines = (
        SOURCE_ROOT / "solomon_harness" / "legacy_payloads" / catalog
    ).read_text(encoding="utf-8").splitlines()
    entries = {line.split("\t", 2)[2] for line in lines[1:]}

    assert lines[0].startswith("solomon-harness-legacy-payload-v1\t")
    assert len(entries) == expected_count
    assert release_specific <= entries
    assert {
        ".mcp.json",
        ".claude/agents/qa.md",
        ".claude/settings.json",
        ".gemini/commands/solomon-start.toml",
        ".gemini/settings.json",
        "AGENTS.md",
        "CLAUDE.md",
        "pyproject.toml",
        "skill-sources.json",
        "uv.lock",
    } <= entries


@pytest.mark.unit
def test_workflow_inventory_prefers_canonical_catalog_and_legacy_metadata(tmp_path: Path) -> None:
    canonical = _write_workflows(tmp_path, "solomon_harness/catalog/workflows")
    legacy = _write_workflows(tmp_path, ".claude/commands")

    assert workflow_files(tmp_path) == canonical
    assert claude_metadata_files(tmp_path) == legacy


@pytest.mark.unit
def test_workflow_inventory_uses_packaged_metadata_fallbacks(tmp_path: Path) -> None:
    legacy_workflows = _write_workflows(tmp_path, ".claude/commands")
    assert workflow_files(tmp_path) == legacy_workflows

    for path in (tmp_path / ".claude" / "commands").glob("*.md"):
        path.unlink()
    (tmp_path / ".claude" / "commands").rmdir()
    (tmp_path / ".claude").rmdir()
    packaged = _write_workflows(tmp_path, "solomon_harness/host_metadata/claude/commands")

    assert claude_metadata_files(tmp_path) == packaged


@pytest.mark.unit
@pytest.mark.parametrize("directory", ["", "../escape", "/absolute"])
def test_files_below_rejects_unsafe_directory_boundaries(directory: str) -> None:
    with pytest.raises(PayloadInventoryError, match="invalid payload path"):
        files_below((), directory)


@pytest.mark.unit
def test_files_below_returns_only_descendants_relative_to_the_boundary() -> None:
    files = (
        Path("solomon_harness/cli.py"),
        Path("solomon_harness/tools/database_client.py"),
        Path("README.md"),
    )

    assert files_below(files, "solomon_harness") == (
        Path("cli.py"),
        Path("tools/database_client.py"),
    )


@pytest.mark.unit
def test_payload_rejects_an_empty_specialist_roster(tmp_path: Path) -> None:
    rules = tmp_path / "agents" / "AGENTS.md"
    rules.parent.mkdir(parents=True)
    rules.write_text("# No specialists\n", encoding="utf-8")

    with pytest.raises(PayloadInventoryError, match="roster is empty"):
        payload_files(tmp_path)


@pytest.mark.unit
def test_payload_rejects_nested_agent_skill_links(tmp_path: Path) -> None:
    rules = tmp_path / "agents" / "AGENTS.md"
    rules.parent.mkdir(parents=True)
    rules.write_text(
        "## The specialist agents\n\n- `qa` — validates changes.\n",
        encoding="utf-8",
    )
    base = tmp_path / "agents" / "qa"
    role = base / "agents" / "qa.md"
    role.parent.mkdir(parents=True)
    role.write_text("Use [nested](skills/nested/check.md).\n", encoding="utf-8")
    for relative in (".agent/config.json", "main.py", "persona.md"):
        path = base / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("{}\n", encoding="utf-8")

    with pytest.raises(PayloadInventoryError, match="one Markdown file"):
        payload_files(tmp_path)


@pytest.mark.unit
def test_workflow_inventory_rejects_missing_and_symlinked_sources(tmp_path: Path) -> None:
    with pytest.raises(PayloadInventoryError, match="required payload file"):
        workflow_files(tmp_path)

    commands = tmp_path / ".claude" / "commands"
    commands.mkdir(parents=True)
    outside = tmp_path / "outside.md"
    outside.write_text("# outside\n", encoding="utf-8")
    (commands / "solomon-bug.md").symlink_to(outside)

    with pytest.raises(PayloadInventoryError, match="symlinks are not allowed"):
        workflow_files(tmp_path)


@pytest.mark.unit
def test_workflow_inventory_rejects_a_symlinked_parent_directory(tmp_path: Path) -> None:
    root = tmp_path / "source"
    claude = root / ".claude"
    claude.mkdir(parents=True)
    outside = tmp_path / "outside-commands"
    _write_workflows(tmp_path, "outside-commands")
    (claude / "commands").symlink_to(outside, target_is_directory=True)

    with pytest.raises(PayloadInventoryError, match="payload path"):
        workflow_files(root)
