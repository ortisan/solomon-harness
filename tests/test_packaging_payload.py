import json
import os
import shutil
import subprocess
import sys
import tarfile
import tempfile
import tomllib
import unittest
import zipfile
from pathlib import Path


SOURCE_ROOT = Path(__file__).resolve().parents[1]
PAYLOAD_PREFIX = "solomon_harness/_payload/"
SOURCE_DIRECTORIES = (".claude", ".github", "agents", "docs", "scripts", "solomon_harness")
SOURCE_FILES = (
    "AGENTS.md",
    "AGY.md",
    "CHANGELOG.md",
    "CLAUDE.md",
    "docker-compose.yml",
    "MANIFEST.in",
    "README.md",
    "pyproject.toml",
    "setup.py",
    "skill-sources.json",
    "uv.lock",
)


def _distribution_names(path: Path) -> set[str]:
    if path.suffix == ".whl":
        with zipfile.ZipFile(path) as archive:
            return set(archive.namelist())
    with tarfile.open(path, "r:gz") as archive:
        names = archive.getnames()
    prefix = names[0].split("/", 1)[0] + "/"
    return {name.removeprefix(prefix) for name in names}


def _payload_names(names: set[str]) -> set[str]:
    return {name.removeprefix(PAYLOAD_PREFIX) for name in names if name.startswith(PAYLOAD_PREFIX)}


def _copy_distribution_source(destination: Path) -> None:
    for name in SOURCE_DIRECTORIES:
        shutil.copytree(SOURCE_ROOT / name, destination / name)
    for name in SOURCE_FILES:
        shutil.copy2(SOURCE_ROOT / name, destination / name)


class PackagingPayloadTest(unittest.TestCase):
    def test_pyproject_enables_packages_and_both_console_entrypoints(self) -> None:
        with (SOURCE_ROOT / "pyproject.toml").open("rb") as stream:
            project = tomllib.load(stream)

        self.assertEqual(project["build-system"]["build-backend"], "setuptools.build_meta")
        self.assertNotEqual(project.get("tool", {}).get("uv", {}).get("package"), False)
        self.assertEqual(
            project["project"]["scripts"]["solomon-harness-mcp"],
            "solomon_harness.mcp_server:main",
        )

    def test_sdist_and_wheel_contain_the_allowlisted_payload_only(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            source = base / "source"
            source.mkdir()
            _copy_distribution_source(source)
            local_files = (
                source / "agents" / "qa" / "credentials.json",
                source / "agents" / "qa" / "skills" / "private_notes.md",
                source / "scripts" / "local-debug.sh",
                source / "solomon_harness" / "credentials.json",
                source / "solomon_harness" / "local-notes.md",
                source / "solomon_harness" / "debug_secret.py",
                source / "solomon_harness" / "templates" / "local-secret.template",
                source / "solomon_harness" / "templates" / "local-secret.json",
                source / "solomon_harness" / "catalog" / "workflows" / "solomon-private.md",
            )
            for path in local_files:
                path.write_text("DO-NOT-PACKAGE\n", encoding="utf-8")

            output = base / "dist"
            completed = subprocess.run(
                [
                    "uv",
                    "build",
                    "--out-dir",
                    str(output),
                    "--no-create-gitignore",
                    str(source),
                ],
                cwd=source,
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)

            wheels = list(output.glob("*.whl"))
            sdists = list(output.glob("*.tar.gz"))
            self.assertEqual(len(wheels), 1)
            self.assertEqual(len(sdists), 1)

            wheel_names = _distribution_names(wheels[0])
            sdist_names = _distribution_names(sdists[0])
            payload = _payload_names(wheel_names)

            required = {
                "agents/AGENTS.md",
                "scripts/generate-integrations.py",
                "solomon_harness/cli.py",
                "solomon_harness/legacy_payloads/v0.11.0.tsv",
                "solomon_harness/legacy_payloads/v0.11.0-main.tsv",
                "solomon_harness/templates/AGENTS.md.template",
                "docs/solomon-workflow.md",
                "docs/release-policy.md",
                "docs/loop-engineering.md",
                "docs/adrs/0000-adr-template.md",
                "docs/adrs/README.md",
                "docs/specs/0000-spec-template.md",
                "docs/specs/README.md",
                ".github/PULL_REQUEST_TEMPLATE.md",
                ".github/ISSUE_TEMPLATE/config.yml",
                "docker-compose.yml",
                "pyproject.toml",
                "uv.lock",
                "skill-sources.json",
            }
            self.assertTrue(required <= payload, sorted(required - payload))
            self.assertIn("solomon_harness/templates/AGENTS.md.template", wheel_names)
            runtime_package_data = {
                name
                for name in payload
                if name.startswith(
                    (
                        "solomon_harness/catalog/workflows/",
                        "solomon_harness/legacy_payloads/",
                        "solomon_harness/templates/",
                    )
                )
            }
            self.assertTrue(
                runtime_package_data <= wheel_names,
                sorted(runtime_package_data - wheel_names),
            )
            self.assertIn("agents/AGENTS.md", sdist_names)
            self.assertIn(".claude/commands/solomon-workflow.md", sdist_names)
            self.assertFalse(any(name.startswith(".claude/") for name in payload))
            self.assertIn(
                "solomon_harness/host_metadata/claude/commands/solomon-workflow.md",
                payload,
            )

            local_relatives = {path.relative_to(source).as_posix() for path in local_files}
            self.assertTrue(local_relatives.isdisjoint(payload))
            self.assertTrue(local_relatives.isdisjoint(wheel_names))
            self.assertTrue(local_relatives.isdisjoint(sdist_names))

            workflows = {
                name
                for name in payload
                if (
                    name.startswith("solomon_harness/catalog/workflows/solomon-")
                    or name.startswith(".claude/commands/solomon-")
                )
                and name.endswith(".md")
            }
            specialists = {
                name.split("/", 2)[1]
                for name in payload
                if name.startswith("agents/") and name.endswith("/persona.md")
            }
            self.assertEqual(len(workflows), 11)
            self.assertEqual(len(specialists), 29)
            self.assertEqual(
                {Path(name).parts[0] for name in payload},
                {
                    ".github",
                    "agents",
                    "docker-compose.yml",
                    "docs",
                    "pyproject.toml",
                    "scripts",
                    "skill-sources.json",
                    "solomon_harness",
                    "uv.lock",
                },
            )

            denied_parts = {
                ".git",
                ".mypy_cache",
                ".pytest_cache",
                ".ruff_cache",
                ".venv",
                "__pycache__",
                "build",
                "dist",
                "node_modules",
                "worktrees",
            }
            denied_names = {
                "scheduled-loop.lock",
                "secure_vault.enc",
                "settings.local.json",
            }
            denied_suffixes = (".db", ".db-shm", ".db-wal", ".enc", ".pyc", ".pyo", ".sqlite")
            for name in payload | sdist_names:
                path = Path(name)
                self.assertTrue(denied_parts.isdisjoint(path.parts), name)
                self.assertNotIn(path.name, denied_names, name)
                self.assertFalse(path.name.endswith(denied_suffixes), name)

    def test_build_rejects_allowlisted_files_reached_through_a_symlink_directory(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            source = base / "source"
            source.mkdir()
            _copy_distribution_source(source)
            hooks = source / "scripts" / "git-hooks"
            relocated = source / "scripts" / "local-hooks"
            hooks.rename(relocated)
            hooks.symlink_to(relocated, target_is_directory=True)

            completed = subprocess.run(
                [
                    "uv",
                    "build",
                    "--wheel",
                    "--out-dir",
                    str(base / "dist"),
                    "--no-create-gitignore",
                    str(source),
                ],
                cwd=source,
                text=True,
                capture_output=True,
                check=False,
            )

            self.assertNotEqual(completed.returncode, 0)
            self.assertIn("symlink", (completed.stdout + completed.stderr).lower())

    def test_wheel_install_matches_source_install_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            output = base / "dist"
            completed = subprocess.run(
                [
                    "uv",
                    "build",
                    "--wheel",
                    "--out-dir",
                    str(output),
                    "--no-create-gitignore",
                    str(SOURCE_ROOT),
                ],
                cwd=SOURCE_ROOT,
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
            wheel = next(output.glob("*.whl"))

            site = base / "site"
            installed = subprocess.run(
                [
                    "uv",
                    "pip",
                    "install",
                    "--target",
                    str(site),
                    "--no-deps",
                    str(wheel),
                ],
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(installed.returncode, 0, installed.stdout + installed.stderr)

            script = (
                "from pathlib import Path\n"
                "from solomon_harness.install_layout import install_project\n"
                "install_project(Path(__import__('sys').argv[1]))\n"
            )
            source_target = base / "source-project"
            wheel_target = base / "wheel-project"
            source_env = dict(os.environ)
            source_env["PYTHONPATH"] = str(SOURCE_ROOT)
            wheel_env = dict(os.environ)
            wheel_env["PYTHONPATH"] = str(site)
            for target, environment in (
                (source_target, source_env),
                (wheel_target, wheel_env),
            ):
                run = subprocess.run(
                    [sys.executable, "-c", script, str(target)],
                    cwd=base,
                    env=environment,
                    text=True,
                    capture_output=True,
                    check=False,
                )
                self.assertEqual(run.returncode, 0, run.stdout + run.stderr)

            source_manifest = json.loads(
                (source_target / ".agents" / "solomon" / "manifest.json").read_text(
                    encoding="utf-8"
                )
            )
            wheel_manifest = json.loads(
                (wheel_target / ".agents" / "solomon" / "manifest.json").read_text(encoding="utf-8")
            )
            self.assertEqual(source_manifest, wheel_manifest)
            for target in (source_target, wheel_target):
                canonical = target / ".agents" / "solomon"
                self.assertTrue((canonical / "docker-compose.yml").is_file())
                metadata = (
                    canonical / "host-metadata" / "claude" / "commands" / "solomon-workflow.md"
                ).read_text(encoding="utf-8")
                self.assertIn("allowed-tools:", metadata)

                probe_env = dict(os.environ)
                probe_env["PYTHONPATH"] = str(canonical)
                probe = subprocess.run(
                    [
                        sys.executable,
                        "-c",
                        (
                            "from pathlib import Path; "
                            "from solomon_harness.memory import _packaged_compose; "
                            "path = _packaged_compose(); "
                            "raise SystemExit(0 if path and Path(path).is_file() else 1)"
                        ),
                    ],
                    cwd=base,
                    env=probe_env,
                    text=True,
                    capture_output=True,
                    check=False,
                )
                self.assertEqual(probe.returncode, 0, probe.stdout + probe.stderr)


if __name__ == "__main__":
    unittest.main()
