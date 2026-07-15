"""Migration gates for the docs/adr -> docs/adrs rename (#221 S2a, #234).

Two invariants: the new tree holds the full, uniquely numbered record set and
the old tree is gone; and no file in the repository still references the old
path. "docs/adrs" contains "docs/adr" as a substring, so the dangling scan
matches the old form only when NOT followed by 's'.
"""

import re
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
ADRS = REPO / "docs" / "adrs"
OLD = REPO / "docs" / "adr"

# The record set at migration time; later ADRs may exist, never fewer.
MIN_RECORDS = 26

DANGLING = re.compile(r"docs/adr(?!s)")
SCAN_EXCLUDE_PARTS = {
    ".git",
    ".solomon",
    ".venv",
    "__pycache__",
    "build",
    "node_modules",
    "scratch",
}
SCAN_SUFFIXES = {".md", ".py", ".toml", ".ts", ".tsx", ".yml", ".yaml", ".json", ".sh"}


def test_adrs_tree_holds_the_full_record_set_and_old_tree_is_gone():
    assert ADRS.is_dir(), "docs/adrs must exist"
    assert not OLD.exists(), "docs/adr must no longer exist as a live tree"
    assert (ADRS / "0000-adr-template.md").is_file()
    assert (ADRS / "README.md").is_file()
    numbers = []
    for path in ADRS.glob("*.md"):
        if path.name in ("README.md", "0000-adr-template.md"):
            continue
        match = re.match(r"^(\d{4})-", path.name)
        assert match, f"unexpected filename in docs/adrs: {path.name}"
        numbers.append(match.group(1))
    assert len(numbers) >= MIN_RECORDS, (
        f"expected at least {MIN_RECORDS} records, found {len(numbers)}"
    )
    assert len(numbers) == len(set(numbers)), "duplicate ADR numbers after the move"


def test_no_reference_to_the_old_adr_path_remains():
    offenders = []
    for path in REPO.rglob("*"):
        if not path.is_file() or path.suffix not in SCAN_SUFFIXES:
            continue
        if SCAN_EXCLUDE_PARTS.intersection(path.parts):
            continue
        rel = path.relative_to(REPO)
        if (
            rel.parts[:2] == ("tests", "fixtures")
            and len(rel.parts) >= 3
            and rel.parts[2].startswith("legacy-")
        ):
            # Historical payloads are immutable upgrade inputs. Their legacy
            # paths prove migration compatibility and are not live references.
            continue
        # Legitimate mentions of the old form: this test file (it defines the
        # scan), PLAN.md (untracked per-branch state that may describe the
        # migration), and the migration ADR itself (it records the rename).
        if rel in (
            Path("tests") / "test_adr_migration.py",
            Path("PLAN.md"),
            Path("docs") / "adrs" / "0028-adrs-directory-and-spec-driven-convention.md",
            # The ADR gate names the old path to detect and reject it.
            Path("scripts") / "check-adr-gate.py",
            Path("tests") / "test_adr_gate.py",
        ):
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        for lineno, line in enumerate(text.splitlines(), start=1):
            if DANGLING.search(line):
                offenders.append(f"{rel}:{lineno}: {line.strip()[:100]}")
    assert not offenders, "dangling docs/adr references:\n" + "\n".join(offenders)
