"""Build the runtime package and its repository-install payload."""

from __future__ import annotations

import runpy
import shutil
from pathlib import Path


def _inventory_function(name: str):
    inventory = runpy.run_path(
        Path(__file__).resolve().parent / "solomon_harness" / "payload_inventory.py"
    )
    return inventory[name]


def _copy_file(project_root: Path, source: Path, destination: Path) -> None:
    relative = source.relative_to(project_root)
    if source.is_symlink():
        raise RuntimeError(f"Symlinks are not allowed in the packaged payload: {relative}")
    if not source.is_file():
        raise RuntimeError(f"Required payload file is unavailable: {relative}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)


def _payload_destination(relative: Path) -> Path:
    if relative.parts[:2] == (".claude", "commands"):
        return (
            Path("solomon_harness/host_metadata/claude/commands")
            / relative.relative_to(".claude/commands")
        )
    return relative


def build_payload(project_root: Path, destination: Path) -> None:
    """Copy the positive install allowlist into a package build directory."""

    project_root = project_root.resolve()
    if destination.exists():
        shutil.rmtree(destination)
    destination.mkdir(parents=True)
    payload_files = _inventory_function("payload_files")
    for relative in payload_files(project_root):
        _copy_file(
            project_root,
            project_root / relative,
            destination / _payload_destination(relative),
        )


def _setup() -> None:
    from setuptools import setup
    from setuptools.command.build_py import build_py
    from setuptools.command.sdist import sdist

    class BuildPyWithPayload(build_py):
        @staticmethod
        def _allowed_package_sources(project_root: Path) -> set[Path]:
            payload_files = _inventory_function("payload_files")
            return {
                (project_root / relative).resolve()
                for relative in payload_files(project_root)
                if relative.parts[0] == "solomon_harness"
            }

        def find_package_modules(self, package, package_dir):
            project_root = Path(__file__).resolve().parent
            allowed = self._allowed_package_sources(project_root)
            return [
                module
                for module in super().find_package_modules(package, package_dir)
                if Path(module[2]).resolve() in allowed
            ]

        def run(self) -> None:
            super().run()
            project_root = Path(__file__).resolve().parent
            destination = Path(self.build_lib) / "solomon_harness" / "_payload"
            build_payload(project_root, destination)

    class SdistWithInventory(sdist):
        def make_release_tree(self, base_dir, files) -> None:
            project_root = Path(__file__).resolve().parent
            source_distribution_files = _inventory_function("source_distribution_files")
            selected = [path.as_posix() for path in source_distribution_files(project_root)]
            super().make_release_tree(base_dir, selected)

    setup(cmdclass={"build_py": BuildPyWithPayload, "sdist": SdistWithInventory})


if __name__ == "__main__":
    _setup()
