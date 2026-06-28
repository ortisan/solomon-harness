"""Prerequisite checks for the solomon-harness CLI.

`check_prerequisites` verifies the tools the harness needs and auto-installs the
ones that are safe to install without elevated privileges (uv). For the rest it
prints the exact per-platform install command, because installing them needs a
package manager or admin rights and is not safe to run blindly.
"""

import os
import shutil
import subprocess
import sys
from typing import Optional

_HINTS = {
    "gh": {
        "darwin": "brew install gh",
        "linux": "https://github.com/cli/cli#installation",
        "win32": "winget install --id GitHub.cli",
    },
    "docker": {"all": "https://docs.docker.com/get-docker/"},
    "python": {
        "darwin": "brew install python",
        "linux": "sudo apt-get install -y python3",
        "win32": "https://www.python.org/downloads/",
    },
    "host": {"all": "install Claude Code (https://claude.com/claude-code) or the Gemini CLI"},
}


def _hint(key: str) -> str:
    hints = _HINTS[key]
    return hints.get(sys.platform) or hints.get("all", "see the project README")


def command_exists(cmd: str) -> bool:
    return shutil.which(cmd) is not None


def python_ok() -> bool:
    return sys.version_info >= (3, 10)


def _uv_install_dirs():
    home = os.path.expanduser("~")
    return [os.path.join(home, ".local", "bin"), os.path.join(home, ".cargo", "bin")]


def install_uv() -> bool:
    """Install uv with the official user-local installer (no sudo)."""
    print("  Installing uv (user-local, no sudo)...")
    try:
        if sys.platform == "win32":
            subprocess.run(
                ["powershell", "-ExecutionPolicy", "ByPass", "-c",
                 "irm https://astral.sh/uv/install.ps1 | iex"],
                check=False,
            )
        else:
            subprocess.run(
                "curl -LsSf https://astral.sh/uv/install.sh | sh",
                shell=True, check=False,
            )
    except Exception as exc:  # pragma: no cover - environment dependent
        print(f"  Could not auto-install uv: {exc}")
    # Make a freshly installed uv visible to this process.
    for d in _uv_install_dirs():
        if os.path.isfile(os.path.join(d, "uv")) and d not in os.environ.get("PATH", ""):
            os.environ["PATH"] = d + os.pathsep + os.environ.get("PATH", "")
    return command_exists("uv")


def check_prerequisites(auto_install: bool = True, out=None) -> bool:
    """Report on prerequisites and install the safe ones. Returns True if all
    required tools are present."""
    log = (out or sys.stdout).write

    def line(text: str) -> None:
        log(text + "\n")

    line("Checking prerequisites...")
    missing_required = 0

    if python_ok():
        line("  ok  Python 3.10+")
    else:
        line(f"  --  Python 3.10+ (required)  ->  {_hint('python')}")
        missing_required += 1

    if command_exists("uv"):
        line("  ok  uv")
    elif auto_install and install_uv():
        line("  ok  uv (installed)")
    else:
        line("  --  uv (required)  ->  curl -LsSf https://astral.sh/uv/install.sh | sh")
        missing_required += 1

    if command_exists("git"):
        line("  ok  git")
    else:
        line("  --  git (required)  ->  install git for your platform")
        missing_required += 1

    if command_exists("gh"):
        line("  ok  GitHub CLI (gh)")
    else:
        line(f"  !   GitHub CLI (gh) - needed for the delivery workflows  ->  {_hint('gh')}")

    if command_exists("claude") or command_exists("gemini"):
        line("  ok  host tool (claude or gemini)")
    else:
        line(f"  !   host tool - {_hint('host')}")

    if command_exists("docker"):
        line("  ok  Docker (optional)")
    else:
        line(f"  !   Docker (optional; SQLite fallback works without it)  ->  {_hint('docker')}")

    if missing_required:
        line(f"\n  {missing_required} required prerequisite(s) still missing - install them and re-run.")
    else:
        line("\n  All required prerequisites are present.")
    return missing_required == 0


def main(argv: Optional[list] = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Check (and install) solomon-harness prerequisites.")
    parser.add_argument("--no-install", action="store_true", help="Only report; do not install anything")
    args = parser.parse_args(argv)
    ok = check_prerequisites(auto_install=not args.no_install)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
