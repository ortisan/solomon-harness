"""Tests for solomon_harness/spec_doc.py.

Pure generation helpers behind /solomon-issue's spec-per-issue step: slugify a
title into a safe filename fragment, split an issue body into its `## `
sections, and (later steps) render and write the seven-heading spec document.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

from solomon_harness import spec_doc

REPO_ROOT = Path(__file__).resolve().parent.parent
SPEC_LINT_SCRIPT = REPO_ROOT / "scripts" / "spec-lint.py"


def _load_spec_lint():
    spec = importlib.util.spec_from_file_location("spec_lint", SPEC_LINT_SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# --- slugify -----------------------------------------------------------------


def test_slugify_lowercases_and_dashes_punctuation():
    assert spec_doc.slugify("Fix bug: A/B!!") == "fix-bug-a-b"


def test_slugify_strips_unicode_diacritics():
    assert spec_doc.slugify("Ãccentuated") == "accentuated"


def test_slugify_strips_path_separator_like_sequences():
    assert spec_doc.slugify("../../etc") == "etc"
    assert spec_doc.slugify("a/b") == "a-b"


def test_slugify_all_symbol_title_falls_back_to_untitled():
    assert spec_doc.slugify("!!!???") == "untitled"


def test_slugify_never_yields_leading_or_trailing_dash():
    slug = spec_doc.slugify("-- weird -- title --")
    assert not slug.startswith("-")
    assert not slug.endswith("-")


# --- spec_filename -------------------------------------------------------------


def test_spec_filename_format():
    assert spec_doc.spec_filename(42, "Add Widget Support") == "42-add-widget-support.md"


def test_spec_filename_path_like_title_cannot_escape_docs_specs():
    name = spec_doc.spec_filename(7, "../../etc/passwd")
    assert "/" not in name
    assert ".." not in name


# --- parse_issue_sections ------------------------------------------------------


def test_parse_issue_sections_splits_on_h2_case_insensitively():
    body = (
        "## Problem statement\n\nSomething is wrong.\n\n"
        "## USER STORY\n\nAs a user, I want X.\n"
    )
    sections = spec_doc.parse_issue_sections(body)

    assert sections["problem statement"] == "Something is wrong."
    assert sections["user story"] == "As a user, I want X."


def test_parse_issue_sections_no_sections_returns_empty_dict():
    assert spec_doc.parse_issue_sections("Just a plain line, no headings.") == {}


def test_parse_issue_sections_ignores_leading_preamble():
    body = "Parent: #221 · Milestone: x\n\n## Problem statement\n\nBody.\n"
    sections = spec_doc.parse_issue_sections(body)

    assert sections["problem statement"] == "Body."
    assert len(sections) == 1


# --- cross-check: spec-lint.py's heading list cannot silently drift -----------


def test_section_headings_match_spec_lint():
    spec_lint = _load_spec_lint()
    assert spec_lint.SECTION_HEADINGS == spec_doc.SECTION_HEADINGS


# --- render_spec ---------------------------------------------------------------

FULL_ISSUE_BODY = """\
Parent: #221 · Milestone: spec-driven-docs · Estimate: 8 (L)

## Problem statement

An issue's intent lives only in its GitHub description today.

## User story

As a software_engineer picking up a Ready issue, I want a structured spec
document generated at creation time.

## Acceptance criteria

```gherkin
Scenario: A new issue generates a spec-driven document
  Given a harness-installed project
  When an author runs /solomon-issue
  Then a file exists at docs/specs/<N>-<slug>.md
```

## Scope

In scope:
- Author the house spec template.
- Wire /solomon-issue's step 5 to generate it.

Out of scope (and why):
- Backfilling historical issues — forward-looking only.
- Publishing specs to the wiki — separate follow-up.

## Definition of Ready

- INVEST met as a single vertical slice.
- Non-functional constraint: spec generation adds < 2s.
"""


def _rendered_sections(markdown: str) -> dict[str, str]:
    return spec_doc.parse_issue_sections(markdown)


def test_render_spec_maps_full_body_onto_all_seven_sections():
    rendered = spec_doc.render_spec(226, "Spec doc per issue", FULL_ISSUE_BODY)
    sections = _rendered_sections(rendered)

    assert sections["context"] == (
        "As a software_engineer picking up a Ready issue, I want a structured spec\n"
        "document generated at creation time."
    )
    assert sections["problem"] == "An issue's intent lives only in its GitHub description today."
    assert "Scenario: A new issue generates a spec-driven document" in sections["acceptance criteria"]
    assert sections["requirements"] == (
        "- Author the house spec template.\n- Wire /solomon-issue's step 5 to generate it."
    )
    assert sections["out of scope"] == (
        "- Backfilling historical issues — forward-looking only.\n"
        "- Publishing specs to the wiki — separate follow-up."
    )
    assert sections["design constraints"] == (
        "- INVEST met as a single vertical slice.\n"
        "- Non-functional constraint: spec generation adds < 2s."
    )


def test_render_spec_traceability_with_adr_ref():
    rendered = spec_doc.render_spec(
        226, "Spec doc per issue", FULL_ISSUE_BODY, adr_ref="ADR-0024: Spec-driven docs"
    )
    sections = _rendered_sections(rendered)

    assert sections["traceability"] == "Issue: #226\nADR-0024: Spec-driven docs"


def test_render_spec_traceability_without_adr_ref():
    rendered = spec_doc.render_spec(226, "Spec doc per issue", FULL_ISSUE_BODY, adr_ref=None)
    sections = _rendered_sections(rendered)

    assert sections["traceability"] == "Issue: #226\nNo related ADR"


# --- render_spec: minimal issue (TBD fallback) ----------------------------------

MINIMAL_ISSUE_BODY = "Just a one-line description, no ## sections at all.\n"


def test_render_spec_minimal_issue_fills_tbd_placeholder():
    rendered = spec_doc.render_spec(99, "Minimal issue", MINIMAL_ISSUE_BODY)
    sections = _rendered_sections(rendered)

    for heading in ("context", "problem", "requirements", "acceptance criteria",
                     "design constraints", "out of scope"):
        assert sections[heading] == "TBD (refine)", heading
    # Traceability is always synthesized, never a placeholder.
    assert sections["traceability"] == "Issue: #99\nNo related ADR"


# --- write_spec ------------------------------------------------------------------


def _seed_fake_repo(tmp_path: Path) -> Path:
    """Seed a tmp_path fake repo root with the real house template."""
    docs_specs = tmp_path / "docs" / "specs"
    docs_specs.mkdir(parents=True)
    template = REPO_ROOT / "docs" / "specs" / "0000-spec-template.md"
    (docs_specs / "0000-spec-template.md").write_text(
        template.read_text(encoding="utf-8"), encoding="utf-8"
    )
    return tmp_path


def _spec_lint(path: Path):
    import subprocess
    import sys

    return subprocess.run(
        [sys.executable, str(SPEC_LINT_SCRIPT), str(path)],
        capture_output=True,
        text=True,
    )


def test_write_spec_writes_a_lint_clean_file(tmp_path):
    root = _seed_fake_repo(tmp_path)

    path = spec_doc.write_spec(root, 226, "Spec doc per issue", FULL_ISSUE_BODY, adr_ref=None)

    assert path == root / "docs" / "specs" / "226-spec-doc-per-issue.md"
    assert path.is_file()

    result = _spec_lint(path)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "OK"


def test_write_spec_creates_docs_specs_if_missing(tmp_path):
    # No docs/specs directory pre-seeded at all this time.
    path = spec_doc.write_spec(tmp_path, 5, "Another one", MINIMAL_ISSUE_BODY)

    assert path.is_file()
    result = _spec_lint(path)
    assert result.returncode == 0, result.stderr


# --- generate CLI ----------------------------------------------------------------


def test_generate_cli_writes_spec_and_prints_uncommitted_note(tmp_path):
    import subprocess
    import sys

    body_file = tmp_path / "body.md"
    body_file.write_text(FULL_ISSUE_BODY, encoding="utf-8")

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "solomon_harness.spec_doc",
            "generate",
            "--issue",
            "226",
            "--title",
            "Spec doc per issue",
            "--body-file",
            str(body_file),
            "--root",
            str(tmp_path),
        ],
        capture_output=True,
        text=True,
        cwd=str(REPO_ROOT),
    )

    assert result.returncode == 0, result.stderr
    written = tmp_path / "docs" / "specs" / "226-spec-doc-per-issue.md"
    assert written.is_file()
    # Write-only: the CLI must never mention committing or pushing the spec.
    low = result.stdout.lower()
    assert "uncommitted" in low
    assert "commit" not in low.replace("uncommitted", "")
    assert "push" not in low
