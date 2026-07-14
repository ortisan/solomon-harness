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
- ``release verify-window`` fail-closed gate run by CI's ``release`` job right
  before tagging: recomputes the commit window from the last tag to the
  just-pushed trunk HEAD and fails if it disagrees with what pyproject.toml /
  CHANGELOG.md already declare (catches a commit that landed on main after the
  prep PR opened but before it merged).
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from dataclasses import dataclass
from typing import List, Optional, Tuple

from solomon_harness.dates import today_iso

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


def read_changelog_section_lines(path: str, version: str) -> List[str]:
    """Return the non-blank lines of the ``[version]`` CHANGELOG section body.

    Used by :func:`verify_release_window` to compare what a release-prep PR
    already wrote against a freshly rendered section for a recomputed commit
    window. Blank lines are stripped so only the meaningful ``### Section`` /
    ``- item`` content is compared.
    """
    with open(path, "r", encoding="utf-8") as f:
        lines = f.read().splitlines()
    body: List[str] = []
    capturing = False
    for line in lines:
        heading = _CHANGELOG_HEADING_RE.match(line.strip())
        if heading:
            if capturing:
                break
            capturing = heading.group("v") == version
            continue
        if capturing and line.strip():
            body.append(line.strip())
    return body


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


def check_release_window(
    *,
    declared_version: str,
    recomputed_version: Optional[str],
    declared_body: List[str],
    recomputed_body: List[str],
) -> List[str]:
    """Return drift problems between a declared release and a fresh recompute.

    ``declared_version``/``declared_body`` are what a release-prep PR already
    wrote to ``pyproject.toml``/``CHANGELOG.md``; ``recomputed_version``/
    ``recomputed_body`` come from re-running the same commit-window
    computation (:func:`commits_since` + :func:`compute_release`) against the
    current trunk HEAD. A mismatch means a commit landed on main after the
    prep PR was opened but before it merged, so the window the PR was built
    from is stale -- even when the bump level (and so the version number)
    happens not to change, e.g. a ``fix`` landing after a ``feat`` already
    forced a minor bump. Better to abort the tag than publish it with a
    silently stale CHANGELOG.
    """
    problems: List[str] = []
    if recomputed_version != declared_version:
        problems.append(
            "recomputed release version from the current main history is "
            f"{recomputed_version!r}, but pyproject.toml/CHANGELOG.md already "
            f"declare {declared_version!r}. A commit likely landed on main "
            "after `release prep` ran; re-run it and re-open the prep PR."
        )
    if recomputed_body != declared_body:
        problems.append(
            "CHANGELOG.md's release section no longer matches the commits "
            "reachable from the current main history. A commit likely landed "
            "on main after `release prep` ran; re-run it and re-open the prep PR."
        )
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


def _change_buckets(commit_messages: List[str]) -> dict:
    """Group commit subjects into Keep a Changelog buckets keyed by type."""
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
    return buckets


def _bucket_lines(buckets: dict) -> List[str]:
    """Render the ``### Section`` blocks for non-empty buckets, in canonical order."""
    lines: List[str] = []
    for name in _SECTION_ORDER:
        if buckets[name]:
            lines.append(f"### {name}")
            lines.extend(buckets[name])
            lines.append("")
    return lines


def render_changelog_section(version: str, date: str, commit_messages: List[str]) -> str:
    """Render one Keep a Changelog section grouping commits by type."""
    lines = [f"## [{version}] - {date}", ""]
    lines.extend(_bucket_lines(_change_buckets(commit_messages)))
    return "\n".join(lines).rstrip() + "\n"


# --- Release wiki page rendering ------------------------------------------

# Shown when no milestone or delivered issues are recorded for a release, so the
# page still carries the section and prompts a human to fill the business case.
_BUSINESS_PLACEHOLDER = (
    "_No business context was recorded for this release. Document the problem "
    "this release solves and the value it delivers to stakeholders here._"
)


def _issue_number(issue: dict) -> str:
    """Normalise an issue's id to a ``#N`` reference for display."""
    raw = str(issue.get("github_id") or issue.get("number") or "").strip()
    return raw if raw.startswith("#") else f"#{raw}" if raw else "#?"


def _business_problem_lines(
    milestone: Optional[dict], issues: Optional[List[dict]]
) -> List[str]:
    """Render the Business Problem section body from the milestone and issues.

    The narrative is sourced from the milestone title and description (the
    richest business context the memory store holds); delivered issues are
    listed underneath so the page ties the value back to concrete work. When
    neither is available a clear placeholder is emitted instead of an empty
    section.
    """
    milestone = milestone or {}
    issues = issues or []
    title = str(milestone.get("title") or "").strip()
    description = str(milestone.get("description") or "").strip()

    lines: List[str] = []
    if title:
        lines.append(f"**Milestone:** {title}")
        lines.append("")
    if description:
        lines.append(description)
        lines.append("")
    if not title and not description:
        if issues:
            lines.append("This release delivers the work tracked by the issues below.")
        else:
            lines.append(_BUSINESS_PLACEHOLDER)
        lines.append("")
    if issues:
        lines.append("### Delivered work")
        for issue in issues:
            subject = str(issue.get("title") or "").strip()
            lines.append(f"- {_issue_number(issue)} {subject}".rstrip())
        lines.append("")
    return lines


def _technical_lines(
    commit_messages: Optional[List[str]],
    adrs: Optional[List[str]],
    code_areas: Optional[List[str]],
) -> List[str]:
    """Render the Technical section body: change breakdown, ADRs, code areas."""
    lines: List[str] = []
    bucket_lines = _bucket_lines(_change_buckets(commit_messages or []))
    if bucket_lines:
        lines.append("### Changes")
        lines.append("")
        lines.extend(bucket_lines)
    else:
        lines.append("_No Conventional Commit changes were recorded for this release._")
        lines.append("")
    if adrs:
        lines.append("### Architecture decisions")
        lines.extend(f"- {a}" for a in adrs)
        lines.append("")
    if code_areas:
        lines.append("### Code areas touched")
        lines.extend(f"- `{area}`" for area in code_areas)
        lines.append("")
    return lines


def render_release_wiki_page(
    version: str,
    *,
    date: Optional[str] = None,
    commit_messages: Optional[List[str]] = None,
    milestone: Optional[dict] = None,
    issues: Optional[List[dict]] = None,
    adrs: Optional[List[str]] = None,
    code_areas: Optional[List[str]] = None,
) -> str:
    """Render the Markdown wiki page documenting a single release.

    The page always carries two clearly headed sections so every release is
    documented on both axes:

    - ``## Business Problem`` — the problem the release solves and the value
      delivered, sourced from the milestone title/description and the delivered
      issue titles, with a placeholder when no such context is recorded.
    - ``## Technical`` — the Conventional Commit change breakdown (Added /
      Changed / Fixed), notable ADRs, and the code areas touched.
    """
    clean = str(version).lstrip("v")
    lines = [f"# Release v{clean}", ""]
    if date:
        lines.append(f"Released {date}.")
        lines.append("")
    lines.append("## Business Problem")
    lines.append("")
    lines.extend(_business_problem_lines(milestone, issues))
    lines.append("## Technical")
    lines.append("")
    lines.extend(_technical_lines(commit_messages, adrs, code_areas))
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
    """Compute the next release from the commits on trunk since the last tag.

    Raises ``ValueError`` with a clean, explanatory message (never a bare regex
    mismatch) when neither the last tag nor the current ``pyproject.toml``
    version is a parseable SemVer string — e.g. a prerelease-style current
    version (``0.1.0-rc.1``) before any tag exists. Callers that expose a
    CLI surface (``cmd_plan``, ``cmd_prep``) catch this and follow the same
    clean-stderr/return-1 pattern used elsewhere in this module.
    """
    pyproject = os.path.join(workspace_root, "pyproject.toml")
    current_version = read_pyproject_version(pyproject)
    tag = last_version_tag(workspace_root)
    try:
        base = SemVer.parse(tag) if tag else SemVer.parse(current_version)
    except ValueError as exc:
        raise ValueError(f"cannot compute the release base version: {exc}") from exc
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


def verify_release_window(workspace_root: str) -> List[str]:
    """Recompute the release window against the current trunk HEAD.

    Run by CI's ``release`` job right before tagging (never during ``prep``,
    where the comparison would be trivially self-consistent): re-runs the same
    commit-window computation ``plan()`` uses -- :func:`commits_since` from the
    last tag, then :func:`compute_release` -- against whatever ``HEAD`` is
    checked out to (the just-pushed main tip, after the prep PR's squash
    merge) and compares it to what ``pyproject.toml``/``CHANGELOG.md`` already
    declare. A commit that landed on main after the prep PR opened but before
    it merged shows up here even when it does not change the bump level (a
    ``fix`` arriving after a ``feat`` already forced a minor bump, say),
    because the comparison also covers the rendered CHANGELOG body, not just
    the version number.

    Returns the list of drift problems; empty means the window is still
    accurate. When there is no prior tag (the very first release ever), there
    is no "since" boundary to recompute against, so this returns clean.
    """
    pyproject = os.path.join(workspace_root, "pyproject.toml")
    changelog = os.path.join(workspace_root, "CHANGELOG.md")
    declared_version = read_pyproject_version(pyproject)
    prior_tag = last_version_tag(workspace_root)
    if prior_tag is None:
        return []
    base = SemVer.parse(prior_tag)
    commits = commits_since(prior_tag, workspace_root, ref="HEAD")
    _, recomputed = compute_release(base, commits)
    recomputed_body = [line for line in _bucket_lines(_change_buckets(commits)) if line.strip()]
    declared_body = read_changelog_section_lines(changelog, declared_version)
    return check_release_window(
        declared_version=declared_version,
        recomputed_version=str(recomputed) if recomputed else None,
        declared_body=declared_body,
        recomputed_body=recomputed_body,
    )


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


# --- Release context gathering (for the wiki page) ------------------------

def _load_memory_context(
    workspace_root: str, version: str
) -> Tuple[Optional[dict], List[dict]]:
    """Best-effort pull of the milestone and delivered issues from project memory.

    Returns ``(milestone, issues)``. The milestone is matched against the
    release ``version`` by title/description; the issues are those attached to
    that milestone. When memory holds milestones but none references this
    version, no milestone is guessed -- the caller renders the documented
    placeholder instead of silently attributing an unrelated milestone's title
    and description to this release. Raises on any backend failure so the
    caller can degrade to a placeholder page.
    """
    from solomon_harness.tools.database_client import DatabaseClient

    db = DatabaseClient(harness_dir=workspace_root)
    milestones = db.list_milestones() or []
    milestone: Optional[dict] = None
    needle = str(version).lstrip("v")
    for ms in milestones:
        haystack = f"{ms.get('title', '')} {ms.get('description', '')}"
        if needle and needle in haystack:
            milestone = ms
            break
    if milestone is None and milestones:
        # A milestone exists in memory but none references this release's
        # version in its title or description. Picking the first one anyway
        # (most recent, but otherwise arbitrary) previously produced a wiki
        # page whose Business Problem section documented an unrelated
        # milestone -- refuse that guess and flag it instead.
        print(
            f"release wiki-page: no milestone references version {needle!r}; "
            "rendering the placeholder instead of guessing a milestone.",
            file=sys.stderr,
        )

    issues: List[dict] = []
    # An issue's milestone_id may hold the milestone's integer rowid (legacy
    # SQLite rows), its client-minted record id (F7, ADR-0016), or the
    # SurrealDB ``table:key`` spelling, so the join matches against every
    # spelling of this milestone's identity.
    milestone_keys = set()
    if milestone is not None:
        for key in (milestone.get("id"), milestone.get("record_id")):
            if key is not None:
                milestone_keys.add(str(key))
                milestone_keys.add(DatabaseClient._record_key(key, key))
    if milestone_keys:
        try:
            # list_issues() returns every status, unlike get_open_issues() which
            # is scoped to non-terminal rows by design (ADR-0006). By release
            # time the delivered issues under a milestone are normally closed,
            # so filtering the open-only set here would always render an empty
            # "Delivered work" section.
            issues = [
                i
                for i in (db.list_issues() or [])
                if str(i.get("milestone_id")) in milestone_keys
            ]
        except Exception:
            issues = []
    return milestone, issues


def _gather_release_context(workspace_root: str, version: str) -> dict:
    """Collect the data a release wiki page needs, degrading on any failure.

    Commits come from the trunk window via :func:`plan`; the milestone and
    delivered issues come from project memory. Either source can be missing
    (no git history, no memory backend) without blocking the page, which is the
    point of documenting a release: it must always produce a page.
    """
    try:
        commits = plan(workspace_root).get("commits", []) or []
    except Exception:
        commits = []
    try:
        milestone, issues = _load_memory_context(workspace_root, version)
    except Exception:
        milestone, issues = None, []
    return {"commits": commits, "milestone": milestone, "issues": issues}


# --- CLI handlers ---------------------------------------------------------

def cmd_plan(workspace_root: str) -> int:
    try:
        info = plan(workspace_root)
    except ValueError as exc:
        print(f"release plan: {exc}", file=sys.stderr)
        return 1
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


def cmd_verify_window(workspace_root: str) -> int:
    """Fail-closed gate for CI's ``release`` job: recompute the window pre-tag.

    Distinct from ``cmd_check``, which only asserts internal agreement
    (tag == pyproject.version == top CHANGELOG heading). This instead
    recomputes the commit window from the last tag to the current ``HEAD``
    and compares it to that declared version/changelog, so it catches a
    commit that landed on main after the release-prep PR opened but before it
    merged -- something an internal-agreement check cannot see.
    """
    try:
        problems = verify_release_window(workspace_root)
    except ValueError as exc:
        print(f"release verify-window: {exc}", file=sys.stderr)
        return 1
    if problems:
        print("release verify-window FAILED: the release window is stale.", file=sys.stderr)
        for p in problems:
            print(f"  - {p}", file=sys.stderr)
        return 1
    print("release verify-window OK: the release window still matches the current main history.")
    return 0


def cmd_prep(workspace_root: str, version: Optional[str] = None) -> int:
    """Open the ephemeral chore/release-vX.Y.Z prep PR. Never merges."""
    try:
        info = plan(workspace_root)
    except ValueError as exc:
        print(f"release prep: {exc}", file=sys.stderr)
        return 1
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


def cmd_wiki_page(
    workspace_root: str,
    version: Optional[str] = None,
    date: Optional[str] = None,
) -> int:
    """Write ``docs/wiki/Release-<version>.md`` with Business and Technical sections.

    The page always renders, even when no memory backend or git history is
    reachable: missing business context becomes a placeholder so a human can
    fill it in. The version defaults to the planned next release.
    """
    if not version:
        try:
            version = plan(workspace_root).get("next")
        except Exception:
            version = None
        if not version:
            try:
                version = read_pyproject_version(
                    os.path.join(workspace_root, "pyproject.toml")
                )
            except Exception:
                print(
                    "release wiki-page: could not determine a version; pass --release.",
                    file=sys.stderr,
                )
                return 1
    clean = str(version).lstrip("v")
    ctx = _gather_release_context(workspace_root, clean)
    page = render_release_wiki_page(
        clean,
        date=date or today_iso(),
        commit_messages=ctx["commits"],
        milestone=ctx["milestone"],
        issues=ctx["issues"],
    )
    wiki_dir = os.path.join(workspace_root, "docs", "wiki")
    os.makedirs(wiki_dir, exist_ok=True)
    path = os.path.join(wiki_dir, f"Release-{clean}.md")
    with open(path, "w", encoding="utf-8") as f:
        f.write(page)
    print(f"Wrote release wiki page: {os.path.relpath(path, workspace_root)}")
    return 0


def cmd_audit_trigger(workspace_root: str, version: Optional[str] = None) -> int:
    """Invokes Slice 1's audit on the delivered artifact and files the gap report.
    Degrade-safe: any failure logs 'audit skipped: sourcing unavailable' and exits 0.
    """
    try:
        if not version:
            pyproject = os.path.join(workspace_root, "pyproject.toml")
            if os.path.isfile(pyproject):
                version = read_pyproject_version(pyproject)
            else:
                version = "unknown"

        prompt = (
            f"You are the `practice_curator` agent. Perform Slice 1's audit on the delivered artifact for version v{version}.\n"
            f"Follow the instructions in your skill `auditing_delivered_work.md` exactly:\n"
            f"- Identify the competency domains touched by the changes in version v{version}.\n"
            f"- Quote the approaches taken and compare them against the best-practice approaches.\n"
            f"- Source the evidence with at least two dated, credible references using `sourcing_the_state_of_the_art.md`.\n"
            f"- File a gap report (or 'no gap found' status) by persisting the audit in project memory with `save_decision`.\n"
            f"Do not modify any code files."
        )

        engine = (os.environ.get("SOLOMON_ENGINE") or "claude").lower()
        if engine == "agy":
            exec_path = os.path.expanduser("~/.local/bin/agy")
            if not os.path.isfile(exec_path):
                exec_path = "agy"
            import uuid
            cmd = [exec_path, "-p", "-", "--conversation", str(uuid.uuid4()), "--dangerously-skip-permissions", "--print-timeout", "20m0s"]
        elif engine == "claude":
            cmd = [engine, "-p", "--permission-mode", "bypassPermissions", "--dangerously-skip-permissions"]
        else:
            cmd = [engine, "-p"]

        curator_dir = os.path.join(workspace_root, "agents", "practice_curator")
        if not os.path.isdir(curator_dir):
            print("audit skipped: curator agent directory not found")
            return 0

        env = os.environ.copy()
        env["PYTHONPATH"] = workspace_root

        proc = subprocess.run(
            cmd,
            input=prompt,
            text=True,
            cwd=curator_dir,
            env=env,
            capture_output=True,
            check=False,
            timeout=300,
        )
        
        if proc.returncode != 0:
            print("audit skipped: sourcing unavailable")
            return 0

        print("Autonomous audit trigger completed successfully.")
        return 0

    except Exception:
        print("audit skipped: sourcing unavailable")
        return 0


def run(workspace_root: str, args: List[str]) -> int:
    """Dispatch ``release <plan|prep|check|verify-window|wiki-page|audit-trigger>``."""
    if not args:
        print(
            "Usage: solomon-harness release <plan|prep|check|verify-window|wiki-page|audit-trigger> [version]",
            file=sys.stderr,
        )
        return 1
    sub, rest = args[0], args[1:]
    if sub == "plan":
        return cmd_plan(workspace_root)
    if sub == "check":
        return cmd_check(workspace_root)
    if sub == "verify-window":
        return cmd_verify_window(workspace_root)
    if sub == "prep":
        return cmd_prep(workspace_root, rest[0] if rest else None)
    if sub == "wiki-page":
        return cmd_wiki_page(workspace_root, rest[0] if rest else None)
    if sub == "audit-trigger":
        return cmd_audit_trigger(workspace_root, rest[0] if rest else None)
    print(
        f"Unknown release subcommand {sub!r}. Use plan, prep, check, verify-window, wiki-page, or audit-trigger.",
        file=sys.stderr,
    )
    return 1


def main(argv: Optional[List[str]] = None) -> int:
    """Headless entry: ``python -m solomon_harness.release <command> [options]``.

    Mirrors the ``cli.py`` ``release`` dispatch but is independently runnable so
    a release wiki page can be generated without the full harness CLI:
    ``python -m solomon_harness.release wiki-page --release <version>``.
    """
    import argparse

    argv = list(sys.argv[1:] if argv is None else argv)
    parser = argparse.ArgumentParser(
        prog="python -m solomon_harness.release",
        description="Release mechanics: plan, prep, check, and document releases.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    def _with_root(p):
        # A workspace-root override shared by every subcommand; defaults to cwd.
        p.add_argument(
            "--root",
            dest="root",
            default=None,
            help="Workspace root (defaults to the current directory).",
        )
        return p

    wp = _with_root(
        sub.add_parser(
            "wiki-page",
            help="Write docs/wiki/Release-<version>.md with Business Problem and Technical sections",
        )
    )
    wp.add_argument(
        "--release",
        dest="release",
        default=None,
        help="Release version (e.g. 0.4.0). Defaults to the planned next version.",
    )
    wp.add_argument(
        "--date", dest="date", default=None, help="Release date (YYYY-MM-DD). Defaults to today."
    )

    _with_root(sub.add_parser("plan"))
    _with_root(sub.add_parser("check"))
    _with_root(
        sub.add_parser(
            "verify-window",
            help=(
                "Recompute the release window against the current trunk HEAD and fail if it "
                "drifted from pyproject.toml/CHANGELOG.md (run by CI right before tagging)"
            ),
        )
    )
    prep = _with_root(sub.add_parser("prep"))
    prep.add_argument("version", nargs="?", default=None)
    audit_trig = _with_root(sub.add_parser("audit-trigger"))
    audit_trig.add_argument("version", nargs="?", default=None)

    args = parser.parse_args(argv)
    root = getattr(args, "root", None) or os.getcwd()
    if args.command == "wiki-page":
        return cmd_wiki_page(root, version=args.release, date=args.date)
    if args.command == "plan":
        return cmd_plan(root)
    if args.command == "check":
        return cmd_check(root)
    if args.command == "verify-window":
        return cmd_verify_window(root)
    if args.command == "prep":
        return cmd_prep(root, args.version)
    if args.command == "audit-trigger":
        return cmd_audit_trigger(root, args.version)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
