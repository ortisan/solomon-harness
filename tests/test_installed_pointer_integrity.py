"""Installed documentation and adapter pointers must resolve to real surfaces."""

from __future__ import annotations

from pathlib import Path

import pytest

from solomon_harness.install_layout import install_project
from solomon_harness.layout import HarnessPaths


SOURCE_ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.integration
def test_installed_specialist_and_config_pointers_preserve_their_namespaces(
    tmp_path: Path,
) -> None:
    install_project(tmp_path, source_root=SOURCE_ROOT)
    paths = HarnessPaths(tmp_path)
    names = tuple(
        sorted(
            directory.name
            for directory in paths.agents.iterdir()
            if (directory / "agents" / f"{directory.name}.md").is_file()
        )
    )

    assert names
    for name in names:
        canonical_profile = (
            paths.agents / name / "agents" / f"{name}.md"
        ).relative_to(tmp_path).as_posix()
        adapters = (
            paths.claude_agents / f"{name}.md",
            paths.agents_root / "agents" / name / "agent.md",
            paths.codex_agents / f"{name}.toml",
        )
        for adapter in adapters:
            assert adapter.is_file(), adapter.relative_to(tmp_path).as_posix()
            assert canonical_profile in adapter.read_text(encoding="utf-8")

    rules = paths.rules.read_text(encoding="utf-8")
    builder_role = (
        paths.agents / "agent_builder" / "agents" / "agent_builder.md"
    ).read_text(encoding="utf-8")
    builder_skill = (
        paths.agents / "agent_builder" / "skills" / "scope_and_mandate.md"
    ).read_text(encoding="utf-8")
    dba_skill = (
        paths.agents
        / "dba"
        / "skills"
        / "house_databases_surrealdb_and_sqlite.md"
    ).read_text(encoding="utf-8")

    assert "`.claude/agents/<name>.md`" in rules
    assert "`.agents/solomon/agents/<name>/agents/<name>.md`" in rules
    assert "`.agents/solomon/agents/<name>/agents/<name>.md`" in builder_role
    assert "`.claude/agents/<name>.md`" in builder_role
    assert "`.agents/solomon/agents/<name>/.agent/config.json`" in builder_skill
    assert "`.agents/solomon/config/project.json`" in dba_skill
    assert "`.agent/config.json`" in dba_skill

    installed_markdown = "\n".join(
        path.read_text(encoding="utf-8")
        for path in paths.solomon.rglob("*.md")
    )
    assert ".agents/solomon/.agents/solomon/" not in installed_markdown
    assert ".agents/solomon/agents/<name>.md" not in installed_markdown
    assert (
        ".agents/solomon/agents/<name>/.agents/solomon/config/project.json"
        not in installed_markdown
    )
