"""Tests for the release mechanics (solomon_harness.release).

The release standard is milestone-gated SemVer on trunk (docs/release-policy.md):
the version is COMPUTED from Conventional Commits since the last tag, and a
fail-closed check asserts tag == pyproject.version == top CHANGELOG heading.
These tests pin the pure core: the version math, the commit classifier, the
parsers, and the consistency gate. The git/gh I/O is a thin shell over them.
"""

import textwrap

import pytest

from solomon_harness import release


# --- SemVer ---------------------------------------------------------------

def test_semver_parse_accepts_plain_and_v_prefixed():
    assert release.SemVer.parse("1.2.3") == release.SemVer(1, 2, 3)
    assert release.SemVer.parse("v0.3.1") == release.SemVer(0, 3, 1)


def test_semver_parse_rejects_garbage():
    with pytest.raises(ValueError):
        release.SemVer.parse("1.2")
    with pytest.raises(ValueError):
        release.SemVer.parse("nope")


def test_semver_str_roundtrip():
    assert str(release.SemVer.parse("10.4.2")) == "10.4.2"


def test_semver_bump_resets_lower_components():
    v = release.SemVer(0, 3, 1)
    assert str(v.bump("patch")) == "0.3.2"
    assert str(v.bump("minor")) == "0.4.0"
    assert str(v.bump("major")) == "1.0.0"


# --- Conventional commit classification -----------------------------------

@pytest.mark.parametrize(
    "message,expected_type,expected_breaking",
    [
        ("feat: add thing", "feat", False),
        ("feat(release): add plan command", "feat", False),
        ("fix(auth): reject empty token", "fix", False),
        ("chore(deps): bump ruff", "chore", False),
        ("docs: explain policy", "docs", False),
        ("refactor(core): extract helper", "refactor", False),
        ("perf: cache lookups", "perf", False),
        ("not a conventional commit", None, False),
        ("feat!: drop legacy flag", "feat", True),
        ("feat(api)!: rename endpoint", "feat", True),
    ],
)
def test_classify_commit_header(message, expected_type, expected_breaking):
    ctype, breaking = release.classify_commit(message)
    assert ctype == expected_type
    assert breaking is expected_breaking


def test_classify_commit_detects_breaking_change_footer():
    msg = textwrap.dedent(
        """\
        refactor(api): rename statement endpoint

        Body explaining the move.

        BREAKING CHANGE: GET /statement is removed.

        Refs #311
        """
    )
    ctype, breaking = release.classify_commit(msg)
    assert ctype == "refactor"
    assert breaking is True


def test_classify_commit_detects_hyphenated_breaking_change_token():
    ctype, breaking = release.classify_commit("fix: x\n\nBREAKING-CHANGE: gone")
    assert breaking is True


# --- Bump computation -----------------------------------------------------

def test_compute_release_feat_is_minor_pre_1_0():
    level, newv = release.compute_release(release.SemVer(0, 3, 1), ["feat: add x"])
    assert level == "minor"
    assert str(newv) == "0.4.0"


def test_compute_release_fix_is_patch():
    level, newv = release.compute_release(release.SemVer(0, 3, 1), ["fix: y"])
    assert level == "patch"
    assert str(newv) == "0.3.2"


def test_compute_release_breaking_is_minor_pre_1_0_major_post_1_0():
    pre_level, pre_v = release.compute_release(
        release.SemVer(0, 3, 1), ["feat!: break it"]
    )
    assert (pre_level, str(pre_v)) == ("minor", "0.4.0")

    post_level, post_v = release.compute_release(
        release.SemVer(1, 4, 2), ["feat!: break it"]
    )
    assert (post_level, str(post_v)) == ("major", "2.0.0")


def test_compute_release_highest_level_wins():
    level, newv = release.compute_release(
        release.SemVer(0, 3, 1), ["fix: a", "feat: b", "chore: c"]
    )
    assert level == "minor"
    assert str(newv) == "0.4.0"


def test_compute_release_nonreleasable_window_returns_none():
    level, newv = release.compute_release(
        release.SemVer(0, 3, 1), ["chore: a", "docs: b", "ci: c", "test: d"]
    )
    assert level is None
    assert newv is None


def test_compute_release_empty_window_returns_none():
    level, newv = release.compute_release(release.SemVer(0, 3, 1), [])
    assert level is None
    assert newv is None


# --- pyproject / CHANGELOG parsing ----------------------------------------

def test_read_pyproject_version(tmp_path):
    p = tmp_path / "pyproject.toml"
    p.write_text('[project]\nname = "x"\nversion = "0.3.1"\n', encoding="utf-8")
    assert release.read_pyproject_version(str(p)) == "0.3.1"


def test_read_changelog_top_returns_version_and_date(tmp_path):
    c = tmp_path / "CHANGELOG.md"
    c.write_text(
        "# Changelog\n\n## [0.4.0] - 2026-06-28\n\n### Added\n- thing\n\n## [0.3.1] - 2026-06-27\n",
        encoding="utf-8",
    )
    version, date = release.read_changelog_top(str(c))
    assert version == "0.4.0"
    assert date == "2026-06-28"


def test_read_changelog_top_handles_missing_date(tmp_path):
    c = tmp_path / "CHANGELOG.md"
    c.write_text("# Changelog\n\n## [0.4.0]\n\n- thing\n", encoding="utf-8")
    version, date = release.read_changelog_top(str(c))
    assert version == "0.4.0"
    assert date is None


# --- Fail-closed consistency gate -----------------------------------------

def _consistent_kwargs():
    return dict(
        version="0.4.0",
        pyproject_version="0.4.0",
        changelog_version="0.4.0",
        changelog_date="2026-06-28",
        existing_tags=["v0.3.1", "v0.3.0"],
    )


def test_check_consistency_passes_when_everything_agrees():
    assert release.check_release_consistency(**_consistent_kwargs()) == []


def test_check_consistency_flags_pyproject_mismatch():
    kw = _consistent_kwargs()
    kw["pyproject_version"] = "0.3.1"
    problems = release.check_release_consistency(**kw)
    assert any("pyproject" in p for p in problems)


def test_check_consistency_flags_changelog_mismatch():
    kw = _consistent_kwargs()
    kw["changelog_version"] = "0.3.1"
    problems = release.check_release_consistency(**kw)
    assert any("CHANGELOG" in p or "changelog" in p for p in problems)


def test_check_consistency_flags_missing_changelog_date():
    kw = _consistent_kwargs()
    kw["changelog_date"] = None
    problems = release.check_release_consistency(**kw)
    assert any("date" in p for p in problems)


def test_check_consistency_flags_existing_tag():
    kw = _consistent_kwargs()
    kw["existing_tags"] = ["v0.4.0", "v0.3.1"]
    problems = release.check_release_consistency(**kw)
    assert any("v0.4.0" in p and "exist" in p for p in problems)


# --- Changelog section rendering ------------------------------------------

def test_render_changelog_section_groups_by_type():
    section = release.render_changelog_section(
        "0.4.0",
        "2026-06-28",
        ["feat(ui): board view", "fix(memory): reconnect", "docs: tidy"],
    )
    assert "## [0.4.0] - 2026-06-28" in section
    assert "### Added" in section and "board view" in section
    assert "### Fixed" in section and "reconnect" in section
