"""Tests for the per-release wiki page generator (solomon_harness.release).

Requirement: every release must be documented in the wiki with a clearly headed
"Business Problem" section (the problem solved and the value delivered, sourced
from the milestone and delivered issues) and a "Technical" section (the commit
breakdown, notable ADRs, and code areas touched). These tests pin the pure
renderer and the headless ``wiki-page`` entry; the DB and git access are mocked
so the suite never touches a real repository or memory backend.
"""

import os

from solomon_harness import release


# --- render_release_wiki_page (pure) --------------------------------------

def _milestone():
    return {
        "title": "Memory source of truth",
        "description": (
            "Make SurrealDB the single source of truth for issue status so the "
            "resume pointer counts open work accurately."
        ),
        "state": "active",
    }


def _issues():
    return [
        {"github_id": "101", "title": "bug(memory): reconcile issue status"},
        {"github_id": "53", "title": "feat(ui): cockpit foundation"},
    ]


def _commits():
    return ["feat(ui): board view", "fix(memory): reconnect socket", "docs: tidy"]


def test_page_has_business_problem_and_technical_headings():
    page = release.render_release_wiki_page(
        "0.4.0",
        date="2026-06-29",
        commit_messages=_commits(),
        milestone=_milestone(),
        issues=_issues(),
    )
    assert "## Business Problem" in page
    assert "## Technical" in page


def test_page_includes_the_version_and_date():
    page = release.render_release_wiki_page(
        "0.4.0", date="2026-06-29", commit_messages=_commits()
    )
    assert "0.4.0" in page
    assert "2026-06-29" in page


def test_business_problem_uses_milestone_description_and_issue_titles():
    page = release.render_release_wiki_page(
        "0.4.0",
        commit_messages=_commits(),
        milestone=_milestone(),
        issues=_issues(),
    )
    business = page.split("## Technical", 1)[0]
    # The narrative is sourced from the milestone description.
    assert "single source of truth for issue status" in business
    # Delivered issues are listed by number and title in the business context.
    assert "#101" in business
    assert "reconcile issue status" in business
    assert "#53" in business


def test_business_problem_placeholder_when_no_context_available():
    page = release.render_release_wiki_page("0.5.0")
    assert "## Business Problem" in page
    assert "## Technical" in page
    business = page.split("## Technical", 1)[0]
    assert "No business context" in business


def test_technical_section_buckets_commits_by_type():
    page = release.render_release_wiki_page(
        "0.4.0", date="2026-06-29", commit_messages=_commits()
    )
    technical = page.split("## Technical", 1)[1]
    assert "### Added" in technical and "board view" in technical
    assert "### Fixed" in technical and "reconnect socket" in technical
    # A non-releasable docs commit is not bucketed.
    assert "tidy" not in technical


def test_technical_section_lists_adrs_and_code_areas_when_provided():
    page = release.render_release_wiki_page(
        "0.4.0",
        commit_messages=_commits(),
        adrs=["ADR-0006: Memory is the source of truth for issue status"],
        code_areas=["solomon_harness/memory_service.py", "solomon_harness/cli.py"],
    )
    technical = page.split("## Technical", 1)[1]
    assert "ADR-0006" in technical
    assert "solomon_harness/memory_service.py" in technical


# --- render_changelog_section is unchanged by the refactor -----------------

def test_changelog_section_still_renders_unchanged():
    section = release.render_changelog_section(
        "0.4.0", "2026-06-28", ["feat(ui): board view", "fix(memory): reconnect"]
    )
    assert section.startswith("## [0.4.0] - 2026-06-28")
    assert "### Added" in section and "board view" in section
    assert "### Fixed" in section and "reconnect" in section


# --- headless wiki-page entry (argparse) -----------------------------------

def test_wiki_page_command_writes_release_page(tmp_path, monkeypatch):
    def fake_ctx(root, version):
        return {
            "commits": ["feat(x): a thing", "fix(y): a bug"],
            "milestone": _milestone(),
            "issues": _issues(),
        }

    monkeypatch.setattr(release, "_gather_release_context", fake_ctx)
    rc = release.main(
        ["wiki-page", "--release", "v0.4.0", "--root", str(tmp_path), "--date", "2026-06-29"]
    )
    assert rc == 0
    path = tmp_path / "docs" / "wiki" / "Release-0.4.0.md"
    assert path.exists()
    text = path.read_text(encoding="utf-8")
    assert "## Business Problem" in text
    assert "## Technical" in text
    assert "0.4.0" in text
    assert "2026-06-29" in text
    # The leading v is stripped from the filename and the version reference.
    assert not (tmp_path / "docs" / "wiki" / "Release-v0.4.0.md").exists()


def test_wiki_page_command_defaults_version_to_planned_next(tmp_path, monkeypatch):
    monkeypatch.setattr(release, "plan", lambda root: {"next": "0.9.0", "commits": []})
    monkeypatch.setattr(
        release,
        "_gather_release_context",
        lambda root, version: {"commits": [], "milestone": None, "issues": []},
    )
    rc = release.main(["wiki-page", "--root", str(tmp_path), "--date", "2026-06-29"])
    assert rc == 0
    assert (tmp_path / "docs" / "wiki" / "Release-0.9.0.md").exists()


# --- _gather_release_context degrades when memory is unreachable ------------

def test_gather_release_context_degrades_without_memory(tmp_path, monkeypatch):
    monkeypatch.setattr(release, "plan", lambda root: {"commits": ["feat: a"]})

    def boom(root, version):
        raise RuntimeError("no memory backend reachable")

    monkeypatch.setattr(release, "_load_memory_context", boom)
    ctx = release._gather_release_context(str(tmp_path), "0.4.0")
    assert ctx["commits"] == ["feat: a"]
    assert ctx["milestone"] is None
    assert ctx["issues"] == []


def test_gather_release_context_degrades_without_git(tmp_path, monkeypatch):
    def git_boom(root):
        raise RuntimeError("not a git repo")

    monkeypatch.setattr(release, "plan", git_boom)
    monkeypatch.setattr(
        release, "_load_memory_context", lambda root, version: (None, [])
    )
    ctx = release._gather_release_context(str(tmp_path), "0.4.0")
    assert ctx["commits"] == []
    assert ctx["milestone"] is None
    assert ctx["issues"] == []


def test_module_is_runnable_as_main(tmp_path, monkeypatch):
    # The module exposes a callable entry so the page is writable headlessly via
    # `python -m solomon_harness.release wiki-page --release <version>`.
    assert callable(release.main)
    assert os.path.basename(release.__file__) == "release.py"
