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
