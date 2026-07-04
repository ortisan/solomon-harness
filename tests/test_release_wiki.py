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


# --- _load_memory_context against a real DatabaseClient ---------------------
#
# By release time the delivered issues under a milestone are normally closed,
# not open. get_open_issues() only returns non-terminal rows by design, so
# filtering it by milestone_id silently drops every closed issue and the
# rendered "Delivered work" section comes out empty. These tests exercise a
# real (SQLite-fallback) DatabaseClient instead of a mock, so the regression
# cannot hide behind a monkeypatched context.

def test_load_memory_context_includes_closed_issues_under_milestone(tmp_path):
    from solomon_harness.tools.database_client import DatabaseClient

    workspace_root = str(tmp_path)
    db = DatabaseClient(harness_dir=workspace_root)
    try:
        milestone_id = db.create_milestone(
            "Release v0.7.0 readiness",
            "Ship the delivery pipeline.",
            "2026-07-01",
            "active",
        )
        db.log_issue("201", "reconcile issue status", "bug", "closed", milestone_id)
        db.log_issue("202", "cockpit foundation", "feature", "Done", milestone_id)
    finally:
        db.close()

    milestone, issues = release._load_memory_context(workspace_root, "0.7.0")

    assert milestone is not None
    assert milestone.get("title") == "Release v0.7.0 readiness"
    numbers = {str(i.get("github_id")) for i in issues}
    assert numbers == {"201", "202"}


def test_wiki_page_renders_closed_delivered_issues_from_real_db(tmp_path):
    """End-to-end: closed issues under the matching milestone must appear in
    the rendered Business Problem section, not just in the raw context."""
    from solomon_harness.tools.database_client import DatabaseClient

    workspace_root = str(tmp_path)
    db = DatabaseClient(harness_dir=workspace_root)
    try:
        milestone_id = db.create_milestone(
            "Release v0.7.0 readiness",
            "Ship the delivery pipeline.",
            "2026-07-01",
            "active",
        )
        db.log_issue("201", "reconcile issue status", "bug", "closed", milestone_id)
        db.log_issue("202", "cockpit foundation", "feature", "Done", milestone_id)
    finally:
        db.close()

    ctx = release._gather_release_context(workspace_root, "0.7.0")
    page = release.render_release_wiki_page(
        "0.7.0", milestone=ctx["milestone"], issues=ctx["issues"]
    )
    business = page.split("## Technical", 1)[0]
    assert "#201" in business and "reconcile issue status" in business
    assert "#202" in business and "cockpit foundation" in business


# --- milestone selection refuses an unrelated fallback -----------------------

def test_load_memory_context_refuses_unrelated_milestone_fallback(tmp_path, capsys):
    """When no milestone's title/description references the release version,
    the generator must not silently pick whichever milestone happens to be
    first -- it must leave the milestone unset and flag the mismatch."""
    from solomon_harness.tools.database_client import DatabaseClient

    workspace_root = str(tmp_path)
    db = DatabaseClient(harness_dir=workspace_root)
    try:
        db.create_milestone("Sprint 1", "goals", "2026-01-01", "closed")
    finally:
        db.close()

    milestone, issues = release._load_memory_context(workspace_root, "0.11.0")

    assert milestone is None
    assert issues == []
    assert "0.11.0" in capsys.readouterr().err


def test_wiki_page_placeholder_when_no_milestone_matches_version(tmp_path):
    """The rendered page must not attribute an unrelated milestone's title and
    description to the release being documented."""
    from solomon_harness.tools.database_client import DatabaseClient

    workspace_root = str(tmp_path)
    db = DatabaseClient(harness_dir=workspace_root)
    try:
        db.create_milestone("Sprint 1", "goals", "2026-01-01", "closed")
    finally:
        db.close()

    ctx = release._gather_release_context(workspace_root, "0.11.0")
    page = release.render_release_wiki_page(
        "0.11.0", milestone=ctx["milestone"], issues=ctx["issues"]
    )
    business = page.split("## Technical", 1)[0]
    assert "Sprint 1" not in business
    assert "No business context" in business
