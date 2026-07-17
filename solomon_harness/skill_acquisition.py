"""The single guarded skill-acquisition chokepoint (#108, ADR-0003 decision 5).

Every external skill that lands in ``agents/<name>/skills/`` — whether pulled by
the capability broker or by the ``solomon-harness skills add`` CLI — passes
through this module: a SHA-pinned clone, a scan that rejects symlinks, scripts,
executables, oversized files, and disallowed types (quarantining the offender), a
realpath confinement check, and a single mechanical copy. There is no second,
weaker path. Its reason to change is skill-acquisition security, so it lives apart
from ``curator.py`` (benchmarking/proposals) and ``skills.py`` (discovery/CLI).
"""

import os
import re
import shutil
import subprocess
import tempfile


def _pinned_clone(source: dict, dest: str) -> None:
    """Clone ``source`` at its recorded full-SHA pin into ``dest``, fail-closed.

    An unpinned source, a non-full-SHA pin, a disallowed URL scheme, or a HEAD
    that does not equal the pin all raise before any content is trusted.
    """
    url = source.get("url")
    pin = source.get("pin") or source.get("commit")
    if not url:
        raise ValueError("Source has no URL")
    # Scheme allowlist blocks ext::/fd:: and other RCE transports.
    if not url.startswith(("https://", "ssh://", "git@", "file://")):
        raise ValueError("disallowed source URL scheme")
    if not pin:
        raise ValueError("SHA-pin mandatory (HEAD == recorded SHA; reject unpinned default-branch clone)")
    # A full hex SHA blocks --upload-pack= option injection and short/branch pins.
    if not re.fullmatch(r"[0-9a-f]{40}|[0-9a-f]{64}", pin):
        raise ValueError("pin must be a full commit SHA")

    os.makedirs(dest, exist_ok=True)
    subprocess.run(["git", "init", "-q", dest], check=True)
    subprocess.run(["git", "-C", dest, "remote", "add", "origin", url], check=True)
    subprocess.run(["git", "-C", dest, "fetch", "--depth", "1", "origin", pin], check=True, capture_output=True)
    subprocess.run(["git", "-C", dest, "checkout", "-q", pin], check=True, capture_output=True)

    proc = subprocess.run(["git", "-C", dest, "rev-parse", "HEAD"], check=True, capture_output=True, text=True)
    current_head = proc.stdout.strip()
    if current_head != pin:
        raise ValueError(f"HEAD mismatch: checked out {current_head}, expected {pin}")


def adapt_skill_content(text: str, name: str) -> str:
    """Strip emojis and AI cliches and ensure the house title/sections exist."""
    # Remove emojis
    emoji_pattern = re.compile(
        r"[\U00010000-\U0010ffff\u2600-\u27bf\u200d\ufe0f]",
        flags=re.UNICODE
    )
    text = emoji_pattern.sub("", text)

    # Remove AI cliches
    cliches = {
        r"\bdelve\b": "examine",
        r"\bleverage\b": "use",
        r"\btestament to\b": "evidence of",
        r"\bfeel free to\b": "you may",
        r"\bdive into\b": "explore",
        r"\bin summary\b": "concluding",
        r"\bfurthermore\b": "also",
        r"\bmoreover\b": "additionally",
        r"\btapestry\b": "structure",
        r"\bdelving\b": "examining",
    }
    for pattern, repl in cliches.items():
        text = re.sub(pattern, repl, text, flags=re.IGNORECASE)

    lines = text.splitlines()
    title = name.replace("_", " ").replace("-", " ").title()
    has_title = False
    for line in lines[:5]:
        if line.strip().startswith("# "):
            has_title = True
            break

    if not has_title:
        text = f"# {title}\n\n" + text

    if "## Common pitfalls" not in text:
        text = text.rstrip() + "\n\n## Common pitfalls\n\n- Stray configuration and redundant abstractions.\n"
    if "## Definition of done" not in text:
        text = text.rstrip() + "\n\n## Definition of done\n\n- [ ] The skill conforms to the house style.\n"

    return text


# Inert file types a packaged skill may contain. Anything else is treated as
# active content and quarantined: an allowlist fails closed, unlike a denylist
# that an attacker can sidestep with an unlisted extension.
_ALLOWED_SKILL_EXTS = {
    ".md", ".txt", ".json", ".yaml", ".yml", ".toml",
    ".rst", ".csv", ".png", ".jpg", ".jpeg", ".gif", ".svg",
}
_SCRIPT_DIRS = {"scripts", "bin", "hooks", ".githooks"}
_SKILL_SIZE_CAP = 256 * 1024


def _quarantine_skill(src_dir: str, workspace_root: str, name: str, reason: str) -> None:
    """Copy a rejected packaged skill to the quarantine area, then raise.

    The copy preserves symlinks (symlinks=True) so quarantining never
    dereferences a link out of the source tree.
    """
    quarantine_root = os.path.join(workspace_root, ".solomon", "quarantine")
    quarantine_path = os.path.join(quarantine_root, name)
    if os.path.isdir(quarantine_path):
        shutil.rmtree(quarantine_path)
    os.makedirs(quarantine_root, exist_ok=True)
    shutil.copytree(src_dir, quarantine_path, symlinks=True)
    raise ValueError(f"{reason}. Quarantined at: {quarantine_path}")


def _scan_packaged_skill(current_dir: str, src_dir: str, in_script_dir: bool, name: str, workspace_root: str) -> None:
    """Recursively validate a packaged skill tree before it is copied.

    Uses os.scandir, not os.walk: os.walk does not descend symlinked
    directories, so files behind one are never scanned yet are still copied by
    shutil.copytree, which dereferences them. This visits every entry at every
    depth and rejects any symlink (file or directory) before it can be
    followed, so the scan and the copy traverse the identical tree. Files are
    held to the inert-type allowlist, the executable bit, the script-directory
    denylist, and the size cap.
    """
    with os.scandir(current_dir) as entries:
        for entry in sorted(entries, key=lambda e: e.name):
            if entry.is_symlink():
                raise ValueError("Symlinks are rejected")
            if entry.is_dir(follow_symlinks=False):
                child_in_script_dir = in_script_dir or entry.name in _SCRIPT_DIRS
                _scan_packaged_skill(entry.path, src_dir, child_in_script_dir, name, workspace_root)
                continue
            stat = entry.stat(follow_symlinks=False)
            if stat.st_size > _SKILL_SIZE_CAP:
                raise ValueError(f"Skill file size exceeds the 256 KiB cap: {entry.path}")
            if in_script_dir or (stat.st_mode & 0o111) != 0:
                _quarantine_skill(src_dir, workspace_root, name, "Security risk: skill contains scripts/executables")
            if os.path.splitext(entry.name)[1].lower() not in _ALLOWED_SKILL_EXTS:
                _quarantine_skill(
                    src_dir, workspace_root, name,
                    f"Security risk: skill contains a disallowed file type: {entry.name}",
                )


def install_skill(src_path: str, agent_skills_dir: str, name: str) -> str:
    """The single mechanical copy of a discovered skill into an agent's dir.

    A standalone ``<name>.md`` is copied to ``<agent_skills_dir>/<name>.md``. A
    packaged ``SKILL.md`` is treated as a folder skill: its whole parent directory
    is copied to ``<agent_skills_dir>/<name>/`` so sibling assets are preserved.
    Returns the path that was written. This performs no validation on its own; the
    guarded entry point is :func:`validate_and_install_skill`, which scans first.
    """
    os.makedirs(agent_skills_dir, exist_ok=True)
    if os.path.basename(src_path) == "SKILL.md":
        target_dir = os.path.join(agent_skills_dir, name)
        if os.path.isdir(target_dir):
            shutil.rmtree(target_dir)
        shutil.copytree(os.path.dirname(src_path), target_dir)
        return target_dir
    target = os.path.join(agent_skills_dir, f"{name}.md")
    shutil.copy2(src_path, target)
    return target


def validate_and_install_skill(src_path: str, agent_skills_dir: str, name: str, workspace_root: str) -> str:
    """Validate a discovered skill, then copy it and adapt its content in place.

    The scan/confinement checks run BEFORE any copy, so a malicious skill is
    quarantined and never lands in the agents tree. The mechanical copy is
    delegated to the single :func:`install_skill`; the installed Markdown is then
    rewritten through :func:`adapt_skill_content`.
    """
    # Reject a name that could escape the skills directory before it is joined
    # into any path.
    if os.path.isabs(name) or os.sep in name or "/" in name or ".." in name:
        raise ValueError("invalid skill name")

    is_packaged = os.path.basename(src_path) == "SKILL.md"
    if is_packaged:
        target_path = os.path.join(agent_skills_dir, name)
    else:
        target_path = os.path.join(agent_skills_dir, f"{name}.md")

    target_realpath = os.path.realpath(target_path)
    agents_realpath = os.path.realpath(os.path.join(workspace_root, "agents"))
    if target_realpath != agents_realpath and not target_realpath.startswith(agents_realpath + os.sep):
        raise ValueError(f"Confinement violation: target path {target_realpath} is outside {agents_realpath}")

    if os.path.islink(src_path) or os.path.islink(target_path):
        raise ValueError("Symlinks are rejected")

    if is_packaged:
        src_dir = os.path.dirname(src_path)
        _scan_packaged_skill(src_dir, src_dir, False, name, workspace_root)
    else:
        size = os.path.getsize(src_path)
        if size > _SKILL_SIZE_CAP:
            raise ValueError(f"Skill file size exceeds the 256 KiB cap: {src_path}")

    # A single mechanical copy, then adapt the installed Markdown in place.
    written = install_skill(src_path, agent_skills_dir, name)
    md_path = os.path.join(written, "SKILL.md") if is_packaged else written
    with open(md_path, "r", encoding="utf-8") as f:
        content = f.read(_SKILL_SIZE_CAP)
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(adapt_skill_content(content, name))
    return written


def acquire_skill(
    workspace_root: str,
    source: dict,
    skill_name: str,
    agent_skills_dir: str,
) -> str:
    """Fetch and install a skill through the one guarded path.

    Pinned clone into a throwaway directory, discover the named skill, then
    validate/scan/confine and install it. Both the ``skills add`` CLI and (via
    :func:`_pinned_clone` + :func:`validate_and_install_skill`) the broker use
    this same path; there is no unpinned or unscanned alternative.
    """
    from solomon_harness.skills import discover_skill_files

    with tempfile.TemporaryDirectory() as tmp:
        _pinned_clone(source, tmp)
        skills = discover_skill_files(tmp)
        if skill_name not in skills:
            raise ValueError(f"skill '{skill_name}' not found in the source")
        return validate_and_install_skill(
            skills[skill_name], agent_skills_dir, skill_name, workspace_root
        )
