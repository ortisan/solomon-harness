"""Tests for the release mechanics (solomon_harness.release).

The release standard is milestone-gated SemVer on trunk (docs/release-policy.md):
the version is COMPUTED from Conventional Commits since the last tag, and a
fail-closed check asserts tag == pyproject.version == top CHANGELOG heading.
These tests pin the pure core: the version math, the commit classifier, the
parsers, and the consistency gate. The git/gh I/O is a thin shell over them.
"""

import os
import textwrap
from pathlib import Path

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


def test_render_changelog_section_keeps_breaking_of_nonbucketed_type():
    # A breaking `chore!` bumps the version, so it must still appear in the notes
    # rather than render an empty section.
    section = release.render_changelog_section(
        "1.0.0", "2026-06-28", ["chore!: drop legacy config layout"]
    )
    assert "### Changed" in section
    assert "BREAKING: drop legacy config layout" in section


# --- BREAKING is a footer, not prose (regression for the over-bump bug) -----

def test_breaking_prose_does_not_flag_breaking():
    msg = "fix: tweak\n\nThis is explicitly NOT a BREAKING CHANGE to the API."
    ctype, breaking = release.classify_commit(msg)
    assert ctype == "fix"
    assert breaking is False
    level, newv = release.compute_release(release.SemVer(1, 4, 2), [msg])
    assert (level, str(newv)) == ("patch", "1.4.3")


def test_real_breaking_footer_still_flags():
    msg = "feat: x\n\nBREAKING CHANGE: removed the old flag."
    _, breaking = release.classify_commit(msg)
    assert breaking is True


# --- File mutators (cmd_prep relies on these; previously untested) ----------

def test_set_pyproject_version_rewrites_only_the_version(tmp_path):
    p = tmp_path / "pyproject.toml"
    p.write_text(
        '[project]\nname = "x"\nversion = "0.3.1"\nrequires-python = ">=3.10"\n',
        encoding="utf-8",
    )
    release.set_pyproject_version(str(p), "0.4.0")
    text = p.read_text(encoding="utf-8")
    assert 'version = "0.4.0"' in text
    assert 'version = "0.3.1"' not in text
    assert 'name = "x"' in text  # nothing else disturbed


def test_prepend_changelog_section_inserts_above_first_heading(tmp_path):
    c = tmp_path / "CHANGELOG.md"
    c.write_text(
        "# Changelog\n\n## [0.3.1] - 2026-06-27\n\n### Fixed\n- old\n",
        encoding="utf-8",
    )
    release.prepend_changelog_section(
        str(c), "## [0.4.0] - 2026-06-28\n\n### Added\n- new\n"
    )
    version, date = release.read_changelog_top(str(c))
    assert (version, date) == ("0.4.0", "2026-06-28")
    # The prior entry is preserved below the new one.
    assert "## [0.3.1] - 2026-06-27" in c.read_text(encoding="utf-8")


def test_set_pyproject_version_rejects_a_symlinked_target(tmp_path):
    outside = tmp_path / "outside.toml"
    outside.write_text('[project]\nversion = "9.9.9"\n', encoding="utf-8")
    linked = tmp_path / "pyproject.toml"
    linked.symlink_to(outside)

    with pytest.raises(ValueError, match="symlink"):
        release.set_pyproject_version(str(linked), "1.0.0")

    assert 'version = "9.9.9"' in outside.read_text(encoding="utf-8")


def test_cmd_wiki_page_rejects_a_symlinked_output_directory(tmp_path, monkeypatch):
    outside = tmp_path / "outside"
    outside.mkdir()
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "wiki").symlink_to(outside, target_is_directory=True)
    monkeypatch.setattr(
        release,
        "_gather_release_context",
        lambda _root, _version: {"commits": [], "milestone": None, "issues": []},
    )

    assert release.cmd_wiki_page(str(tmp_path), version="1.0.0") == 1
    assert list(outside.iterdir()) == []


# --- run() dispatch ---------------------------------------------------------

def test_run_rejects_unknown_subcommand(capsys):
    assert release.run("/nonexistent", ["frobnicate"]) == 1


def test_run_with_no_args_prints_usage(capsys):
    assert release.run("/nonexistent", []) == 1
    assert "plan" in capsys.readouterr().err


# --- git-backed helpers against a real temp repo ----------------------------

def _git(repo, *args):
    import subprocess
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    return subprocess.run(
        ["git", "-C", repo, *args], check=True, capture_output=True, text=True, env=env
    )


@pytest.fixture()
def repo(tmp_path):
    r = tmp_path / "proj"
    r.mkdir()
    _git(str(r), "init", "-q")
    _git(str(r), "config", "user.email", "t@example.com")
    _git(str(r), "config", "user.name", "Test")
    _git(str(r), "checkout", "-q", "-b", "main")
    (r / "pyproject.toml").write_text(
        '[project]\nname = "x"\nversion = "0.3.1"\n', encoding="utf-8"
    )
    (r / "CHANGELOG.md").write_text("# Changelog\n\n## [0.3.1] - 2026-06-27\n", encoding="utf-8")
    _git(str(r), "add", "-A")
    _git(str(r), "commit", "-q", "-m", "chore(release): v0.3.1")
    _git(str(r), "tag", "-a", "v0.3.1", "-m", "Release v0.3.1")
    return str(r)


def test_trunk_ref_prefers_main(repo):
    assert release.trunk_ref(repo) == "main"


def test_trunk_ref_falls_back_to_head_without_main(tmp_path):
    r = tmp_path / "p2"
    r.mkdir()
    _git(str(r), "init", "-q")
    _git(str(r), "config", "user.email", "t@e.com")
    _git(str(r), "config", "user.name", "T")
    _git(str(r), "checkout", "-q", "-b", "trunkless")
    (r / "f").write_text("x", encoding="utf-8")
    _git(str(r), "add", "-A")
    _git(str(r), "commit", "-q", "-m", "feat: seed")
    assert release.trunk_ref(str(r)) == "HEAD"


def test_plan_computes_window_from_main_not_a_side_branch(repo):
    # A feat lands on a side branch checked out as HEAD; the window must follow
    # main (where nothing new merged), so plan reports no release.
    _git(repo, "checkout", "-q", "-b", "feature/side")
    (Path(repo) / "x.py").write_text("y\n", encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "feat: side-only work not on main")
    info = release.plan(repo)
    assert info["trunk_ref"] == "main"
    assert info["next"] is None  # main has no new commits since v0.3.1


def test_plan_detects_feat_merged_to_main(repo):
    (Path(repo) / "y.py").write_text("z\n", encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "feat: real feature on main")
    info = release.plan(repo)
    assert (info["level"], info["next"]) == ("minor", "0.4.0")


def test_cmd_prep_returns_nonzero_when_nothing_to_release(repo, capsys):
    # No new commits since v0.3.1 -> nothing to prep, and no branch is created.
    assert release.cmd_prep(repo) == 1
    assert "Nothing to release" in capsys.readouterr().err
    branches = _git(repo, "branch", "--list", "chore/release-*").stdout.strip()
    assert branches == ""


def test_cmd_prep_rejects_a_malformed_explicit_version(repo, capsys):
    # Force a releasable window so the version check is what stops it.
    (Path(repo) / "z.py").write_text("1\n", encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "feat: something")
    assert release.cmd_prep(repo, version="not.a.version") == 1
    assert "not a SemVer" in capsys.readouterr().err


def test_cmd_prep_rejects_symlinked_release_inputs_before_branching(
    tmp_path, monkeypatch, capsys
):
    outside = tmp_path / "outside.toml"
    outside.write_text('[project]\nversion = "9.9.9"\n', encoding="utf-8")
    (tmp_path / "pyproject.toml").symlink_to(outside)
    (tmp_path / "CHANGELOG.md").write_text("# Changelog\n", encoding="utf-8")
    git_calls = []
    monkeypatch.setattr(release, "_git", lambda *args, **kwargs: git_calls.append(args))

    assert release.cmd_prep(str(tmp_path), version="1.0.0") == 1
    assert "symlink" in capsys.readouterr().err
    assert git_calls == []
    assert 'version = "9.9.9"' in outside.read_text(encoding="utf-8")


def test_cmd_audit_trigger_success(repo, capsys):
    from unittest.mock import patch, MagicMock
    import subprocess
    
    # Consumer installs keep the curator in the canonical host-neutral catalog.
    curator_dir = Path(repo) / ".agents" / "solomon" / "agents" / "practice_curator"
    curator_dir.mkdir(parents=True, exist_ok=True)
    
    with patch("subprocess.run") as mock_run:
        mock_proc = MagicMock(spec=subprocess.CompletedProcess)
        mock_proc.returncode = 0
        mock_run.return_value = mock_proc
        
        rc = release.cmd_audit_trigger(repo, version="1.0.0")
        
        assert rc == 0
        mock_run.assert_called_once()
        args, kwargs = mock_run.call_args
        assert "v1.0.0" in kwargs["input"]
        assert kwargs["cwd"] == str(Path(repo).resolve())
        assert args[0] == ["claude", "-p"]
        assert not any("dangerously" in token for token in args[0])
        assert "audit skipped" not in capsys.readouterr().out


def test_cmd_audit_trigger_degrade_safe_on_error(repo, capsys):
    from unittest.mock import patch
    
    curator_dir = Path(repo) / ".agents" / "solomon" / "agents" / "practice_curator"
    curator_dir.mkdir(parents=True, exist_ok=True)
    
    with patch("subprocess.run", side_effect=Exception("Sourcing tool is down")):
        rc = release.cmd_audit_trigger(repo, version="1.0.0")
        
        assert rc == 0
        out_err = capsys.readouterr()
        combined = out_err.out + out_err.err
        assert "audit skipped: sourcing unavailable" in combined


@pytest.mark.parametrize(
    ("engine", "prefix"),
    [
        ("claude", ["claude", "-p"]),
        ("agy", ["agy", "-p", "-"]),
        ("codex", ["codex", "exec", "--sandbox", "workspace-write"]),
    ],
)
def test_cmd_audit_trigger_uses_safe_common_engine_adapter(repo, engine, prefix):
    from unittest.mock import MagicMock, patch
    import subprocess

    curator_dir = Path(repo) / ".agents" / "solomon" / "agents" / "practice_curator"
    curator_dir.mkdir(parents=True, exist_ok=True)
    completed = MagicMock(spec=subprocess.CompletedProcess)
    completed.returncode = 0

    with (
        patch.dict(os.environ, {"SOLOMON_ENGINE": engine}),
        patch("subprocess.run", return_value=completed) as run,
    ):
        assert release.cmd_audit_trigger(repo, version="1.0.0") == 0

    command = run.call_args.args[0]
    assert command[: len(prefix)] == prefix
    assert not any("dangerously" in token for token in command)


# --- Merge-time release-window recompute (catches a prep PR going stale) ----

def _pyproject(repo):
    return str(Path(repo) / "pyproject.toml")


def _changelog(repo):
    return str(Path(repo) / "CHANGELOG.md")


def test_verify_release_window_catches_commit_landed_after_prep_opened(repo):
    # Prep time: main only has the feat that will drive the 0.4.0 minor bump.
    (Path(repo) / "y.py").write_text("z\n", encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "feat: real feature on main")
    info = release.plan(repo)
    assert (info["level"], info["next"]) == ("minor", "0.4.0")

    # The prep PR branches here and writes the 0.4.0 bump + changelog for
    # exactly this commit window (mirrors what cmd_prep does, without pushing).
    section = release.render_changelog_section("0.4.0", "2026-06-28", info["commits"])
    release.set_pyproject_version(_pyproject(repo), "0.4.0")
    release.prepend_changelog_section(_changelog(repo), section)
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "chore(release): v0.4.0")
    chore_sha = _git(repo, "rev-parse", "HEAD").stdout.strip()
    feat_sha = _git(repo, "rev-parse", "HEAD~1").stdout.strip()

    # ...but before that PR merges, an unrelated fix lands directly on main
    # ahead of it (a second PR that merges first). The bump level does not
    # change (feat already forces minor), so a version-only check would miss
    # this: the fix's changelog line is still silently dropped.
    _git(repo, "checkout", "-q", feat_sha)
    (Path(repo) / "urgent.py").write_text("1\n", encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "fix: urgent bug landed while the prep PR was open")

    # Replay the prep PR's chore commit on top, simulating the squash-merge
    # tip that the release job checks out as main HEAD. (git cherry-pick has
    # no -q/--quiet flag; redirect its stdout instead.)
    _git(repo, "cherry-pick", chore_sha)
    _git(repo, "checkout", "-q", "-B", "main")

    problems = release.verify_release_window(repo)
    assert problems, "expected the merge-time recompute to flag the dropped fix commit"
    assert any("CHANGELOG" in p or "changelog" in p for p in problems)


def test_verify_release_window_passes_when_nothing_landed_after_prep(repo):
    (Path(repo) / "y.py").write_text("z\n", encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "feat: real feature on main")
    info = release.plan(repo)
    section = release.render_changelog_section("0.4.0", "2026-06-28", info["commits"])
    release.set_pyproject_version(_pyproject(repo), "0.4.0")
    release.prepend_changelog_section(_changelog(repo), section)
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "chore(release): v0.4.0")

    assert release.verify_release_window(repo) == []


def test_verify_release_window_returns_clean_when_no_prior_tag(tmp_path):
    r = tmp_path / "first_release"
    r.mkdir()
    _git(str(r), "init", "-q")
    _git(str(r), "config", "user.email", "t@example.com")
    _git(str(r), "config", "user.name", "Test")
    _git(str(r), "checkout", "-q", "-b", "main")
    (r / "pyproject.toml").write_text('[project]\nname = "x"\nversion = "0.1.0"\n', encoding="utf-8")
    (r / "CHANGELOG.md").write_text("# Changelog\n\n## [0.1.0] - 2026-06-28\n", encoding="utf-8")
    _git(str(r), "add", "-A")
    _git(str(r), "commit", "-q", "-m", "chore(release): v0.1.0")

    assert release.verify_release_window(str(r)) == []


def test_cmd_verify_window_reports_ok_and_dispatches_via_run(repo, capsys):
    (Path(repo) / "y.py").write_text("z\n", encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "feat: real feature on main")
    info = release.plan(repo)
    section = release.render_changelog_section("0.4.0", "2026-06-28", info["commits"])
    release.set_pyproject_version(_pyproject(repo), "0.4.0")
    release.prepend_changelog_section(_changelog(repo), section)
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "chore(release): v0.4.0")

    assert release.run(repo, ["verify-window"]) == 0
    assert "OK" in capsys.readouterr().out


# --- SemVer.parse guard in plan() (prerelease current version, no tags) -----

def test_cmd_plan_returns_clean_error_for_prerelease_version_without_tags(tmp_path, capsys):
    r = tmp_path / "prerelease_proj"
    r.mkdir()
    _git(str(r), "init", "-q")
    _git(str(r), "config", "user.email", "t@example.com")
    _git(str(r), "config", "user.name", "Test")
    _git(str(r), "checkout", "-q", "-b", "main")
    (r / "pyproject.toml").write_text(
        '[project]\nname = "x"\nversion = "0.1.0-rc.1"\n', encoding="utf-8"
    )
    _git(str(r), "add", "-A")
    _git(str(r), "commit", "-q", "-m", "chore: seed")

    assert release.cmd_plan(str(r)) == 1
    err = capsys.readouterr().err
    assert "release plan" in err
    assert "0.1.0-rc.1" in err


def test_prep_pr_body_carries_the_canonical_adr_skip_line():
    """The ADR gate (#235) validates every PR body, release preps included:
    the hardcoded body must satisfy scripts/check-adr-gate.py."""
    import importlib.util
    import inspect

    from solomon_harness import release

    source = inspect.getsource(release.cmd_prep)
    assert "ADR: not warranted" in source

    spec = importlib.util.spec_from_file_location(
        "check_adr_gate",
        os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                     "scripts", "check-adr-gate.py"),
    )
    gate = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(gate)
    body = (
        "Release v9.9.9 prep. The version bump and CHANGELOG were written by "
        "`solomon-harness release prep`; merging this PR is the human release gate.\n\n"
        "ADR: not warranted — release prep carries only the mechanical version "
        "bump and CHANGELOG section; decisions live with the merged issues.\n"
    )
    assert gate.check_body(body) == []
