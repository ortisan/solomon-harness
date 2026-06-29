"""Release mechanics for solomon-harness.

The release standard (docs/release-policy.md) is milestone-gated SemVer on trunk:
a tag plus a GitHub Release of the source tree, never per-PR. The version is
COMPUTED from Conventional Commits since the last tag, never hand-picked, and a
fail-closed check asserts ``tag == pyproject.version == top CHANGELOG heading``
before a ``chore/release-*`` prep PR can merge.

The module is pure stdlib (Karpathy simplicity): the version math, the commit
classifier, the parsers, and the consistency gate are pure functions; the git
and gh I/O is a thin shell over them so the core is unit-tested without a repo.

CLI surface (wired in ``cli.py``):

- ``release plan``  read-only; detect the bump and print the planned version and
  changelog section. Safe to run headless.
- ``release prep``  open the ephemeral ``chore/release-vX.Y.Z`` PR with the bump
  and changelog written. Stops there; the human merges it (the release gate).
- ``release check`` fail-closed gate: non-zero exit on any version drift.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from dataclasses import dataclass
from typing import List, Optional, Tuple

# Bump levels, ordered so ``max`` selects the strongest signal in a commit window.
_NONE, _PATCH, _MINOR, _MAJOR = 0, 1, 2, 3
_LEVEL_NAME = {_PATCH: "patch", _MINOR: "minor", _MAJOR: "major"}

# Conventional Commit types that map to a patch bump on their own. ``feat`` and a
# BREAKING CHANGE are handled separately (they bump minor/major). Every other
# type (chore, docs, ci, test, style, build) is non-releasable on its own.
_PATCH_TYPES = {"fix", "perf", "refactor", "revert"}

_HEADER_RE = re.compile(r"^(?P<type>[a-z]+)(?:\((?P<scope>[^)]*)\))?(?P<bang>!)?:\s*(?P<subject>.*)$")
# A breaking change is a Conventional Commits footer: the token at line start
# followed by a colon. Anchoring it this way means prose that merely mentions
# "BREAKING CHANGE" (e.g. "this is NOT a BREAKING CHANGE") does not over-bump.
_BREAKING_FOOTER_RE = re.compile(r"^BREAKING[ -]CHANGE:", re.MULTILINE)
_PYPROJECT_VERSION_RE = re.compile(r'^version\s*=\s*"(?P<v>[^"]+)"', re.MULTILINE)
_CHANGELOG_HEADING_RE = re.compile(
    r"^##\s*\[(?P<v>\d+\.\d+\.\d+)\]\s*(?:-\s*(?P<date>\d{4}-\d{2}-\d{2}))?"
)


# --- SemVer ---------------------------------------------------------------

@dataclass(frozen=True)
class SemVer:
    major: int
    minor: int
    patch: int

    @classmethod
    def parse(cls, text: str) -> "SemVer":
        m = re.fullmatch(r"v?(\d+)\.(\d+)\.(\d+)", text.strip())
        if not m:
            raise ValueError(f"not a SemVer string: {text!r}")
        return cls(int(m.group(1)), int(m.group(2)), int(m.group(3)))

    def __str__(self) -> str:
        return f"{self.major}.{self.minor}.{self.patch}"

    def bump(self, level: str) -> "SemVer":
        if level == "major":
            return SemVer(self.major + 1, 0, 0)
        if level == "minor":
            return SemVer(self.major, self.minor + 1, 0)
        if level == "patch":
            return SemVer(self.major, self.minor, self.patch + 1)
        raise ValueError(f"unknown bump level: {level!r}")


# --- Conventional commit classification -----------------------------------

def classify_commit(message: str) -> Tuple[Optional[str], bool]:
    """Return ``(type, is_breaking)`` for a commit message.

    The type comes from the first line's ``type(scope)!: subject`` header; a
    breaking change is flagged by the ``!`` marker or a ``BREAKING CHANGE`` /
    ``BREAKING-CHANGE`` token anywhere in the message.
    """
    text = message.strip()
    first_line = text.splitlines()[0] if text else ""
    m = _HEADER_RE.match(first_line)
    ctype = m.group("type") if m else None
    breaking = bool(m and m.group("bang")) or bool(_BREAKING_FOOTER_RE.search(message))
    return ctype, breaking


def _commit_level(message: str, pre_1_0: bool) -> int:
    ctype, breaking = classify_commit(message)
    if breaking:
        return _MINOR if pre_1_0 else _MAJOR
    if ctype == "feat":
        return _MINOR
    if ctype in _PATCH_TYPES:
        return _PATCH
    return _NONE


def compute_release(
    current: SemVer, commit_messages: List[str]
) -> Tuple[Optional[str], Optional[SemVer]]:
    """Compute the bump for a window of commits.

    Returns ``(level_name, new_version)`` where ``level_name`` is
    ``"major"``/``"minor"``/``"patch"``, or ``(None, None)`` when the window
    holds only non-releasable changes (chore/docs/ci/test/style/build) or is
    empty. Pre-1.0 a feat or a breaking change bumps minor; post-1.0 a breaking
    change bumps major.
    """
    level = max((_commit_level(m, current.major == 0) for m in commit_messages), default=_NONE)
    if level == _NONE:
        return None, None
    name = _LEVEL_NAME[level]
    return name, current.bump(name)


# --- pyproject / CHANGELOG parsing ----------------------------------------

def read_pyproject_version(path: str) -> str:
    with open(path, "r", encoding="utf-8") as f:
        m = _PYPROJECT_VERSION_RE.search(f.read())
    if not m:
        raise ValueError(f"no version found in {path}")
    return m.group("v")


def read_changelog_top(path: str) -> Tuple[Optional[str], Optional[str]]:
    """Return ``(version, date)`` of the topmost ``## [X.Y.Z] - DATE`` heading."""
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            m = _CHANGELOG_HEADING_RE.match(line.strip())
            if m:
                return m.group("v"), m.group("date")
    return None, None


# --- Fail-closed consistency gate -----------------------------------------

def check_release_consistency(
    *,
    version: str,
    pyproject_version: str,
    changelog_version: Optional[str],
    changelog_date: Optional[str],
    existing_tags: List[str],
) -> List[str]:
    """Return the list of consistency problems; empty means the tree is releasable.

    Enforces the single-source-of-truth invariant: the release ``version`` must
    equal both ``pyproject.version`` and the top CHANGELOG heading (which must
    carry a date), and its tag must not already exist.
    """
    problems: List[str] = []
    tag = f"v{version}"
    if pyproject_version != version:
        problems.append(
            f"pyproject.toml version {pyproject_version!r} does not match release version {version!r}"
        )
    if changelog_version != version:
        problems.append(
            f"CHANGELOG.md top entry {changelog_version!r} does not match release version {version!r}"
        )
    elif not changelog_date:
        problems.append(f"CHANGELOG.md top entry {version!r} has no date")
    if tag in existing_tags:
        problems.append(f"tag {tag} already exists; published tags are immutable")
    return problems


# --- Changelog section rendering ------------------------------------------

# Keep a Changelog buckets, keyed by the commit type that feeds them.
_SECTION_FOR_TYPE = {
    "feat": "Added",
    "fix": "Fixed",
    "perf": "Changed",
    "refactor": "Changed",
    "revert": "Changed",
}
_SECTION_ORDER = ["Added", "Changed", "Fixed"]


def _subject(message: str) -> str:
    first_line = message.strip().splitlines()[0] if message.strip() else ""
    m = _HEADER_RE.match(first_line)
    return m.group("subject").strip() if m else first_line.strip()


def render_changelog_section(version: str, date: str, commit_messages: List[str]) -> str:
    """Render one Keep a Changelog section grouping commits by type."""
    buckets: dict = {name: [] for name in _SECTION_ORDER}
    for msg in commit_messages:
        ctype, breaking = classify_commit(msg)
        section = _SECTION_FOR_TYPE.get(ctype or "")
        if not section:
            # A breaking change of an otherwise non-releasable type (e.g.
            # `chore!:`) still bumped the version, so it must appear in the
            # notes rather than render an empty section.
            if breaking:
                section = "Changed"
            else:
                continue
        prefix = "BREAKING: " if breaking else ""
        buckets[section].append(f"- {prefix}{_subject(msg)}")
    lines = [f"## [{version}] - {date}", ""]
    for name in _SECTION_ORDER:
        if buckets[name]:
            lines.append(f"### {name}")
            lines.extend(buckets[name])
            lines.append("")
    return "\n".join(lines).rstrip() + "\n"


# --- git / gh I/O (thin shell) --------------------------------------------

def _git(args: List[str], cwd: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=cwd, text=True, capture_output=True, check=True
    ).stdout


def list_tags(cwd: str) -> List[str]:
    out = _git(["tag", "-l"], cwd)
    return [t for t in out.splitlines() if t.strip()]


def last_version_tag(cwd: str) -> Optional[str]:
    """Return the highest ``vX.Y.Z`` tag, or None when the repo has none."""
    versions = []
    for tag in list_tags(cwd):
        try:
            versions.append((SemVer.parse(tag), tag))
        except ValueError:
            continue
    if not versions:
        return None
    versions.sort(key=lambda pair: (pair[0].major, pair[0].minor, pair[0].patch))
    return versions[-1][1]


def commits_since(tag: Optional[str], cwd: str, ref: str = "HEAD") -> List[str]:
    """Return commit messages reachable from ``ref`` but not from ``tag``."""
    rev = f"{tag}..{ref}" if tag else ref
    out = _git(["log", rev, "--first-parent", "-z", "--format=%B"], cwd)
    return [chunk.strip() for chunk in out.split("\x00") if chunk.strip()]


def trunk_ref(cwd: str) -> str:
    """Resolve the trunk ref to compute the release window against.

    The window is always ``<last-tag>..main`` per the policy, so a plan/prep run
    from a non-main checkout (a worktree or the loop) never bakes unmerged
    commits into the version. Prefer the local ``main``, fall back to
    ``origin/main``, and only as a last resort the current ``HEAD``.
    """
    for ref in ("main", "origin/main"):
        try:
            _git(["rev-parse", "--verify", "--quiet", f"{ref}^{{commit}}"], cwd)
            return ref
        except subprocess.CalledProcessError:
            continue
    return "HEAD"


def plan(workspace_root: str) -> dict:
    """Compute the next release from the commits on trunk since the last tag."""
    pyproject = os.path.join(workspace_root, "pyproject.toml")
    current_version = read_pyproject_version(pyproject)
    tag = last_version_tag(workspace_root)
    base = SemVer.parse(tag) if tag else SemVer.parse(current_version)
    ref = trunk_ref(workspace_root)
    commits = commits_since(tag, workspace_root, ref=ref)
    level, new_version = compute_release(base, commits)
    return {
        "last_tag": tag,
        "base": str(base),
        "trunk_ref": ref,
        "level": level,
        "next": str(new_version) if new_version else None,
        "commit_count": len(commits),
        "commits": commits,
    }


def set_pyproject_version(path: str, new_version: str) -> None:
    with open(path, "r", encoding="utf-8") as f:
        text = f.read()
    new_text, n = _PYPROJECT_VERSION_RE.subn(f'version = "{new_version}"', text, count=1)
    if n != 1:
        raise ValueError(f"could not rewrite version in {path}")
    with open(path, "w", encoding="utf-8") as f:
        f.write(new_text)


def prepend_changelog_section(path: str, section: str) -> None:
    """Insert ``section`` above the first existing version heading."""
    with open(path, "r", encoding="utf-8") as f:
        text = f.read()
    lines = text.splitlines(keepends=True)
    insert_at = len(lines)
    for i, line in enumerate(lines):
        if _CHANGELOG_HEADING_RE.match(line.strip()):
            insert_at = i
            break
    block = section.rstrip() + "\n\n"
    new_text = "".join(lines[:insert_at]) + block + "".join(lines[insert_at:])
    with open(path, "w", encoding="utf-8") as f:
        f.write(new_text)


# --- CLI handlers ---------------------------------------------------------

def cmd_plan(workspace_root: str) -> int:
    info = plan(workspace_root)
    base = info["base"]
    tag = info["last_tag"] or "(no tag)"
    if not info["next"]:
        print(
            f"No releasable change since {tag} "
            f"({info['commit_count']} commit(s), all non-releasable). No tag would be cut."
        )
        return 0
    print(f"Planned release: {info['level']} bump {base} -> {info['next']}  (since {tag})")
    print()
    print(render_changelog_section(info["next"], "YYYY-MM-DD", info["commits"]))
    return 0


def cmd_check(workspace_root: str) -> int:
    pyproject = os.path.join(workspace_root, "pyproject.toml")
    changelog = os.path.join(workspace_root, "CHANGELOG.md")
    version = read_pyproject_version(pyproject)
    changelog_version, changelog_date = read_changelog_top(changelog)
    problems = check_release_consistency(
        version=version,
        pyproject_version=version,
        changelog_version=changelog_version,
        changelog_date=changelog_date,
        existing_tags=list_tags(workspace_root),
    )
    if problems:
        print(f"release check FAILED for v{version}:", file=sys.stderr)
        for p in problems:
            print(f"  - {p}", file=sys.stderr)
        return 1
    print(f"release check OK: v{version} is consistent (pyproject == CHANGELOG, tag not yet cut).")
    return 0


def cmd_prep(workspace_root: str, version: Optional[str] = None) -> int:
    """Open the ephemeral chore/release-vX.Y.Z prep PR. Never merges."""
    info = plan(workspace_root)
    new_version = version or info["next"]
    if not new_version:
        print("Nothing to release: no releasable commits since the last tag.", file=sys.stderr)
        return 1
    try:
        SemVer.parse(new_version)  # reject a malformed explicit version before branching
    except ValueError as exc:
        print(f"release prep: {exc}", file=sys.stderr)
        return 1
    branch = f"chore/release-v{new_version}"
    pyproject = os.path.join(workspace_root, "pyproject.toml")
    changelog = os.path.join(workspace_root, "CHANGELOG.md")
    # The date is stamped by the caller's environment at prep time.
    today = subprocess.run(
        ["date", "+%Y-%m-%d"], text=True, capture_output=True, check=True
    ).stdout.strip()
    section = render_changelog_section(new_version, today, info["commits"])
    try:
        _git(["switch", "-c", branch, "main"], workspace_root)
        set_pyproject_version(pyproject, new_version)
        prepend_changelog_section(changelog, section)
        _git(["add", "pyproject.toml", "CHANGELOG.md"], workspace_root)
        _git(["commit", "-m", f"chore(release): v{new_version}"], workspace_root)
        _git(["push", "-u", "origin", branch], workspace_root)
    except subprocess.CalledProcessError as exc:
        print(f"release prep failed: {exc.stderr or exc}", file=sys.stderr)
        return 1
    body = (
        f"Release v{new_version} prep. The version bump and CHANGELOG were written by "
        f"`solomon-harness release prep`; merging this PR is the human release gate, after "
        f"which CI tags and publishes. See docs/release-policy.md.\n"
    )
    proc = subprocess.run(
        ["gh", "pr", "create", "--base", "main", "--head", branch,
         "--title", f"chore(release): v{new_version}", "--body", body],
        cwd=workspace_root, text=True, capture_output=True, check=False,
    )
    print(proc.stdout or proc.stderr)
    return proc.returncode


def run(workspace_root: str, args: List[str]) -> int:
    """Dispatch ``release <plan|prep|check>``."""
    if not args:
        print("Usage: solomon-harness release <plan|prep|check> [version]", file=sys.stderr)
        return 1
    sub, rest = args[0], args[1:]
    if sub == "plan":
        return cmd_plan(workspace_root)
    if sub == "check":
        return cmd_check(workspace_root)
    if sub == "prep":
        return cmd_prep(workspace_root, rest[0] if rest else None)
    print(f"Unknown release subcommand {sub!r}. Use plan, prep, or check.", file=sys.stderr)
    return 1
