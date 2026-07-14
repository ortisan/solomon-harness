"""Tests for scripts/spec-lint.py.

The validator checks that a spec document (``docs/specs/<N>-<slug>.md``) carries
all seven canonical headings, and that a directory of spec documents has
well-formed filenames. It mirrors ``scripts/check-adr-unique.py``'s shape: run
through a subprocess so the exit code and stderr are exercised exactly as CI
would see them.
"""

import subprocess
import sys
from pathlib import Path

from solomon_harness import spec_doc

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = REPO_ROOT / "scripts" / "spec-lint.py"
DOCS_SPECS = REPO_ROOT / "docs" / "specs"

# Not a copy: this is the same list object solomon_harness.spec_doc defines,
# so it cannot silently drift out of sync with the canonical source (a third
# hand-maintained copy previously lived here alongside spec_doc.py's own list
# and scripts/spec-lint.py's own list).
SECTION_HEADINGS = spec_doc.SECTION_HEADINGS


def test_section_headings_is_the_canonical_list_not_a_copy():
    assert SECTION_HEADINGS is spec_doc.SECTION_HEADINGS


def _write_spec(path: Path, omit: str | None = None) -> None:
    lines = ["# Spec: Title\n\n"]
    for heading in SECTION_HEADINGS:
        if heading == omit:
            continue
        lines.append(f"## {heading}\n\nBody text.\n\n")
    path.write_text("".join(lines), encoding="utf-8")


def _run(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        capture_output=True,
        text=True,
    )


def test_single_file_missing_section_fails(tmp_path):
    spec = tmp_path / "1-a-title.md"
    _write_spec(spec, omit="Design Constraints")

    result = _run(str(spec))

    assert result.returncode == 1
    assert (
        result.stderr.strip()
        == f'{spec.name}: missing required section "Design Constraints"'
    )


def test_single_file_all_sections_pass(tmp_path):
    spec = tmp_path / "1-a-title.md"
    _write_spec(spec)

    result = _run(str(spec))

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "OK"


def test_single_file_scrambled_order_fails(tmp_path):
    # Complete: every canonical heading is present, but Problem and Context
    # are swapped, so presence-only checking would wrongly pass this.
    scrambled = list(SECTION_HEADINGS)
    scrambled[0], scrambled[1] = scrambled[1], scrambled[0]

    spec = tmp_path / "1-a-title.md"
    lines = ["# Spec: Title\n\n"]
    for heading in scrambled:
        lines.append(f"## {heading}\n\nBody text.\n\n")
    spec.write_text("".join(lines), encoding="utf-8")

    result = _run(str(spec))

    assert result.returncode == 1
    assert "out of order" in result.stderr
    assert "Problem" in result.stderr


def test_single_file_duplicated_heading_fails(tmp_path):
    spec = tmp_path / "1-a-title.md"
    lines = ["# Spec: Title\n\n"]
    for heading in SECTION_HEADINGS:
        lines.append(f"## {heading}\n\nBody text.\n\n")
        if heading == "Problem":
            lines.append("## Problem\n\nDuplicated body.\n\n")
    spec.write_text("".join(lines), encoding="utf-8")

    result = _run(str(spec))

    assert result.returncode == 1
    assert 'duplicate section "Problem"' in result.stderr


def test_directory_malformed_filename_fails(tmp_path):
    (tmp_path / "sample-no-number.md").write_text("not a spec\n", encoding="utf-8")

    result = _run(str(tmp_path))

    assert result.returncode == 1
    assert (
        result.stderr.strip()
        == "sample-no-number.md: filename does not start with an issue number"
    )


def test_directory_excludes_template_and_readme(tmp_path):
    (tmp_path / "0000-spec-template.md").write_text("template\n", encoding="utf-8")
    (tmp_path / "README.md").write_text("readme\n", encoding="utf-8")

    result = _run(str(tmp_path))

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "OK"


def test_directory_valid_specs_pass(tmp_path):
    _write_spec(tmp_path / "1-a-title.md")
    _write_spec(tmp_path / "2-b-title.md")

    result = _run(str(tmp_path))

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "OK"


def test_nonexistent_path_fails_cleanly(tmp_path):
    missing = tmp_path / "does-not-exist"

    result = _run(str(missing))

    assert result.returncode == 2
    assert "not found" in result.stderr
    assert "Traceback" not in result.stderr


# --- House template and convention doc --------------------------------------


def test_template_and_readme_exist():
    assert (DOCS_SPECS / "0000-spec-template.md").is_file()
    assert (DOCS_SPECS / "README.md").is_file()


def test_template_front_matter_matches_generated_status_default():
    content = (DOCS_SPECS / "0000-spec-template.md").read_text(encoding="utf-8")
    assert "- Status: draft" in content
    assert "draft | refined | implemented" not in content


def test_template_has_headings_in_canonical_order():
    content = (DOCS_SPECS / "0000-spec-template.md").read_text(encoding="utf-8")
    positions = [content.index(f"## {heading}") for heading in SECTION_HEADINGS]
    assert positions == sorted(positions)


def test_template_context_guidance_does_not_contradict_the_user_story_mapping():
    # Context is mapped from the issue's "User story" section
    # (spec_doc._DIRECT_SECTION_MAP), but the template used to tell authors
    # "No solutioning yet" without ever mentioning that source, which reads
    # as a contradiction once you know where the content actually comes from.
    content = (DOCS_SPECS / "0000-spec-template.md").read_text(encoding="utf-8")
    context_section = content.split("## Context", 1)[1].split("## Problem", 1)[0]

    assert "No solutioning yet" not in context_section
    assert "user story" in context_section.lower()


def test_readme_documents_the_section_to_source_mapping():
    content = (DOCS_SPECS / "README.md").read_text(encoding="utf-8")

    assert "Where content comes from" in content
    mapping = {
        "Problem": "Problem statement",
        "Context": "User story",
        "Requirements": "in scope",
        "Out of Scope": "out of scope",
        "Design Constraints": "Definition of Ready",
        "Acceptance Criteria": "Acceptance criteria",
        "Traceability": "synthesized",
    }
    for heading, source in mapping.items():
        assert heading in content, heading
        assert source.lower() in content.lower(), source


def test_fresh_docs_specs_directory_passes_lint():
    # Only the template and the README live in docs/specs at this point (no
    # issue has generated a spec yet); the scan must still exit 0.
    result = _run(str(DOCS_SPECS))

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "OK"
