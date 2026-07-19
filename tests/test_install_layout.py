import hashlib
import json
import os
import re
import shutil
import sqlite3
import stat
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from solomon_harness.bootstrap import bootstrap_project, index_codebase
from solomon_harness.install_layout import (
    InstallConflictError,
    install_project,
    load_manifest,
    migrate_layout,
    uninstall_project,
)
from solomon_harness.install_transaction import record_install_mutation
from solomon_harness.layout import HarnessPaths
from solomon_harness.payload_inventory import payload_files


SOURCE_ROOT = Path(__file__).resolve().parents[1]


def _copy_install_source(destination: Path) -> None:
    for name in (".claude", ".github", "agents", "docs", "scripts", "solomon_harness"):
        shutil.copytree(SOURCE_ROOT / name, destination / name)
    for name in ("docker-compose.yml", "pyproject.toml", "skill-sources.json", "uv.lock"):
        shutil.copy2(SOURCE_ROOT / name, destination / name)


def _snapshot(root: Path) -> dict[str, tuple[bytes, int, int]]:
    result: dict[str, tuple[bytes, int, int]] = {}
    for path in sorted(p for p in root.rglob("*") if p.is_file()):
        rel = path.relative_to(root).as_posix()
        if rel == ".agents/solomon/state/install.lock":
            continue
        info = path.stat()
        result[rel] = (path.read_bytes(), stat.S_IMODE(info.st_mode), info.st_mtime_ns)
    return result


def _copy_legacy_payload(destination: Path) -> None:
    for relative in payload_files(SOURCE_ROOT):
        if relative.parts[0] not in {"agents", "scripts", "solomon_harness"}:
            continue
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(SOURCE_ROOT / relative, target)


class InstallLayoutTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        (self.root / "README.md").write_text("# Consumer\n", encoding="utf-8")
        (self.root / "pyproject.toml").write_text(
            '[project]\nname = "consumer"\nversion = "1.0.0"\n', encoding="utf-8"
        )
        (self.root / ".claude").mkdir()
        (self.root / ".claude" / "settings.json").write_text(
            json.dumps({"permissions": {"allow": ["Bash(git status:*)"]}}),
            encoding="utf-8",
        )
        (self.root / ".codex").mkdir()
        (self.root / ".codex" / "config.toml").write_text(
            'model = "host-owned"\n', encoding="utf-8"
        )

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_fresh_install_has_exact_consumer_boundary(self) -> None:
        before_top = {p.name for p in self.root.iterdir()}
        result = install_project(self.root, source_root=SOURCE_ROOT)

        self.assertTrue(result.changed)
        created_top = {p.name for p in self.root.iterdir()} - before_top
        self.assertEqual(
            created_top,
            {".agents", ".github", ".mcp.json", "AGENTS.md", "docs"},
        )
        for forbidden in (
            "agents",
            "scripts",
            "solomon_harness",
            ".agent",
            ".gemini",
            "CLAUDE.md",
            "AGY.md",
            "uv.lock",
            "planning",
            ".solomon",
        ):
            self.assertFalse((self.root / forbidden).exists(), forbidden)
        self.assertEqual(
            (self.root / "pyproject.toml").read_text(encoding="utf-8"),
            '[project]\nname = "consumer"\nversion = "1.0.0"\n',
        )

        paths = HarnessPaths(self.root)
        self.assertTrue(paths.manifest.is_file())
        self.assertTrue(paths.config.is_file())
        self.assertTrue(paths.agents.is_dir())
        self.assertTrue(paths.workflows.is_dir())
        self.assertTrue((paths.solomon / "solomon_harness" / "cli.py").is_file())
        self.assertTrue((paths.solomon / "scripts" / "generate-integrations.py").is_file())
        self.assertTrue((paths.solomon / "pyproject.toml").is_file())

        docs = sorted(
            p.relative_to(self.root / "docs").as_posix()
            for p in (self.root / "docs").rglob("*")
            if p.is_file()
        )
        self.assertEqual(
            docs,
            [
                "adrs/0000-adr-template.md",
                "adrs/README.md",
                "specs/0000-spec-template.md",
                "specs/README.md",
            ],
        )
        self.assertFalse((self.root / ".github" / "workflows").exists())
        self.assertFalse((self.root / ".github" / "copilot-instructions.md").exists())

    def test_manifest_is_deterministic_confined_and_complete(self) -> None:
        install_project(self.root, source_root=SOURCE_ROOT)
        manifest = load_manifest(self.root)

        self.assertEqual(manifest["schema_version"], 1)
        self.assertEqual(manifest["layout_version"], 1)
        self.assertEqual(manifest["hosts"], ["agy", "claude", "codex"])
        self.assertNotIn("created_at", manifest)
        self.assertNotIn(str(SOURCE_ROOT), json.dumps(manifest))
        paths = [entry["path"] for entry in manifest["entries"]]
        self.assertEqual(paths, sorted(set(paths)))
        allowed_strategies = {"replace", "create-only", "json-merge", "toml-merge", "marker-merge"}
        for entry in manifest["entries"]:
            rel = entry["path"]
            self.assertFalse(Path(rel).is_absolute())
            self.assertNotIn("..", Path(rel).parts)
            self.assertIn(entry["strategy"], allowed_strategies)
            self.assertRegex(entry["sha256"], r"^[0-9a-f]{64}$")
            if entry["strategy"] in {"json-merge", "toml-merge", "marker-merge"}:
                self.assertRegex(entry["managed_sha256"], r"^[0-9a-f]{64}$")
            if entry["strategy"] in {"replace", "create-only"}:
                target = self.root / rel
                self.assertTrue(target.is_file(), rel)
                actual = hashlib.sha256(target.read_bytes()).hexdigest()
                self.assertEqual(actual, entry["sha256"], rel)
        self.assertFalse(any("/state/" in p for p in paths))

    def test_install_uses_positive_inventory_and_excludes_local_source_files(self) -> None:
        source = self.root / "source"
        source.mkdir()
        _copy_install_source(source)
        local_files = (
            source / "agents" / "qa" / "credentials.json",
            source / "agents" / "qa" / "skills" / "private_notes.md",
            source / "scripts" / "local-debug.sh",
            source / "solomon_harness" / "credentials.json",
            source / "solomon_harness" / "local-notes.md",
            source / "solomon_harness" / "debug_secret.py",
        )
        for path in local_files:
            path.write_text("DO-NOT-INSTALL\n", encoding="utf-8")

        target = self.root / "consumer"
        install_project(target, source_root=source)

        installed_files = [path for path in target.rglob("*") if path.is_file()]
        self.assertFalse(any(path.read_bytes() == b"DO-NOT-INSTALL\n" for path in installed_files))
        manifest_text = HarnessPaths(target).manifest.read_text(encoding="utf-8")
        for local in local_files:
            self.assertNotIn(local.name, manifest_text)

    def test_installed_workflows_use_only_canonical_paths_and_isolated_uv(self) -> None:
        install_project(self.root, source_root=SOURCE_ROOT)

        workflows = HarnessPaths(self.root).workflows
        installed = sorted(workflows.glob("solomon-*.md"))
        self.assertEqual(len(installed), 11)
        text = "\n".join(path.read_text(encoding="utf-8") for path in installed)
        run_prefix = (
            "UV_PROJECT_ENVIRONMENT=.agents/solomon/state/venv uv run --project .agents/solomon"
        )

        for forbidden in (
            ".agents/solomon/.venv",
            ".agent/config.json",
            ".solomon/",
            "uv run python -m solomon_harness",
            "uv run solomon-harness",
        ):
            self.assertNotIn(forbidden, text)
        self.assertIsNone(re.search(r"(?<!\.agents/solomon/)(?<![\w.-])agents/", text))
        self.assertIsNone(re.search(r"(?<!\.agents/solomon/)(?<![\w.-])scripts/", text))
        self.assertIn(".agents/solomon/state/handoffs/", text)
        self.assertNotIn(".agents/solomon/handoffs/", text)
        self.assertIn(".agents/solomon/state/broker/", text)
        self.assertNotIn(f"{run_prefix} python -m solomon_harness", text)
        self.assertNotIn(f"{run_prefix} python .agents/solomon/scripts/", text)
        self.assertNotIn(f'{run_prefix} python -c "import solomon_harness"', text)
        self.assertIn(f"{run_prefix} python -I -m solomon_harness", text)
        self.assertIn(f"{run_prefix} python -I .agents/solomon/scripts/", text)
        self.assertIn(f'{run_prefix} python -I -c "import solomon_harness"', text)
        for match in re.finditer(r"uv run --project \.agents/solomon", text):
            start = match.start() - len("UV_PROJECT_ENVIRONMENT=.agents/solomon/state/venv ")
            self.assertGreaterEqual(start, 0)
            self.assertEqual(text[start : match.end()], run_prefix)

    def test_every_installed_python_source_is_byte_identical_to_the_allowlist(self) -> None:
        adapter_result = SimpleNamespace(changed=False, conflicts=(), managed_paths=())
        with patch(
            "solomon_harness.host_adapters.compile_adapters",
            return_value=adapter_result,
        ):
            install_project(self.root, source_root=SOURCE_ROOT)

        canonical = HarnessPaths(self.root).solomon
        python_sources = [
            relative for relative in payload_files(SOURCE_ROOT) if relative.suffix == ".py"
        ]
        self.assertTrue(python_sources)
        for relative in python_sources:
            self.assertEqual(
                (canonical / relative).read_bytes(),
                (SOURCE_ROOT / relative).read_bytes(),
                relative.as_posix(),
            )

    def test_agent_python_literals_are_not_rewritten_as_instruction_text(self) -> None:
        source = self.root / "source"
        source.mkdir()
        _copy_install_source(source)
        agent_main = source / "agents" / "qa" / "main.py"
        legacy_contract = (
            '\nLEGACY_PATH_CONTRACT = (".agent/config.json", ".solomon/", "agents/")\n'
        )
        agent_main.write_text(
            agent_main.read_text(encoding="utf-8") + legacy_contract,
            encoding="utf-8",
        )

        target = self.root / "consumer-with-agent-runtime"
        adapter_result = SimpleNamespace(changed=False, conflicts=(), managed_paths=())
        with patch(
            "solomon_harness.host_adapters.compile_adapters",
            return_value=adapter_result,
        ):
            install_project(target, source_root=source)

        installed = HarnessPaths(target).solomon / "agents" / "qa" / "main.py"
        self.assertEqual(installed.read_bytes(), agent_main.read_bytes())

    def test_nested_runtime_import_preserves_legacy_path_resolvers(self) -> None:
        adapter_result = SimpleNamespace(changed=False, conflicts=(), managed_paths=())
        with patch(
            "solomon_harness.host_adapters.compile_adapters",
            return_value=adapter_result,
        ):
            install_project(self.root, source_root=SOURCE_ROOT)
        canonical = HarnessPaths(self.root).solomon
        probe = self.root / "legacy-probe"
        legacy_config = probe / ".agent" / "config.json"
        legacy_config.parent.mkdir(parents=True)
        legacy_config.write_text("{}\n", encoding="utf-8")
        legacy_state = probe / ".solomon"
        legacy_state.mkdir()
        legacy_workflows = probe / ".claude" / "commands"
        legacy_workflows.mkdir(parents=True)
        (legacy_workflows / "solomon-workflow.md").write_text(
            "legacy workflow\n",
            encoding="utf-8",
        )
        script = (
            "import json, sys\n"
            "from pathlib import Path\n"
            "import solomon_harness\n"
            "from solomon_harness.layout import HarnessPaths\n"
            "canonical, probe = map(Path, sys.argv[1:])\n"
            "paths = HarnessPaths(probe)\n"
            "result = {\n"
            "  'module': Path(solomon_harness.__file__).resolve().parent.as_posix(),\n"
            "  'config': paths.resolve_config().relative_to(probe).as_posix(),\n"
            "  'state': paths.resolve_state().relative_to(probe).as_posix(),\n"
            "  'workflows': paths.resolve_workflows().relative_to(probe).as_posix(),\n"
            "}\n"
            "print(json.dumps(result, sort_keys=True))\n"
        )
        environment = dict(os.environ)
        environment["PYTHONPATH"] = str(canonical)

        completed = subprocess.run(
            [sys.executable, "-c", script, str(canonical), str(probe)],
            cwd=self.root,
            env=environment,
            text=True,
            capture_output=True,
            check=False,
        )

        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(
            json.loads(completed.stdout),
            {
                "module": (canonical / "solomon_harness").resolve().as_posix(),
                "config": ".agent/config.json",
                "state": ".solomon",
                "workflows": ".claude/commands",
            },
        )

    def test_second_install_changes_no_bytes_modes_or_mtimes(self) -> None:
        install_project(self.root, source_root=SOURCE_ROOT)
        first = _snapshot(self.root)
        time.sleep(0.01)
        result = install_project(self.root, source_root=SOURCE_ROOT)
        second = _snapshot(self.root)
        self.assertFalse(result.changed)
        self.assertEqual(first, second)

    def test_full_bootstrap_uses_managed_layout_and_stops_before_legacy_scaffolds(self) -> None:
        with (
            patch("solomon_harness.prereqs.check_prerequisites", return_value=True),
            patch("solomon_harness.home.assigned_memory_port", return_value=8099),
            patch("solomon_harness.memory.ensure_home_compose"),
            patch.dict(os.environ, {"SOLOMON_SKIP_GH_CHECK": "1"}),
        ):
            bootstrap_project(str(self.root), non_interactive=True)
        self.assertTrue(HarnessPaths(self.root).manifest.is_file())
        self.assertFalse((self.root / "planning").exists())
        self.assertFalse((self.root / "docs" / "wiki").exists())
        self.assertFalse((self.root / ".gemini").exists())
        self.assertFalse((self.root / ".agent").exists())

    def test_second_full_bootstrap_preserves_bytes_modes_and_mtimes(self) -> None:
        with (
            patch("solomon_harness.prereqs.check_prerequisites", return_value=True),
            patch("solomon_harness.home.assigned_memory_port", return_value=8099),
            patch("solomon_harness.memory.ensure_home_compose"),
            patch.dict(os.environ, {"SOLOMON_SKIP_GH_CHECK": "1"}),
        ):
            bootstrap_project(str(self.root), non_interactive=True)
            first = _snapshot(self.root)
            time.sleep(0.01)
            bootstrap_project(str(self.root), non_interactive=True)

        self.assertEqual(_snapshot(self.root), first)

    def test_legacy_config_and_state_migrate_without_loss(self) -> None:
        legacy_config = self.root / ".agent" / "config.json"
        legacy_config.parent.mkdir()
        config = {"database": {"database": "tenant-one"}, "loop": {"autonomy": "L1"}}
        legacy_config.write_text(json.dumps(config), encoding="utf-8")
        legacy_state = self.root / ".solomon" / "memory-mirror" / "decision"
        legacy_state.mkdir(parents=True)
        (legacy_state / "one.md").write_text("memory", encoding="utf-8")

        result = migrate_layout(self.root, source_root=SOURCE_ROOT)

        self.assertTrue(result.changed)
        paths = HarnessPaths(self.root)
        self.assertEqual(json.loads(paths.config.read_text(encoding="utf-8")), config)
        self.assertEqual(
            (paths.state / "memory-mirror" / "decision" / "one.md").read_text(encoding="utf-8"),
            "memory",
        )
        self.assertFalse((self.root / ".agent").exists())
        self.assertFalse((self.root / ".solomon").exists())

    def test_legacy_sqlite_memory_migrates_to_canonical_state_without_loss(self) -> None:
        legacy = self.root / "memory" / "long_term" / "harness.db"
        legacy.parent.mkdir(parents=True)
        connection = sqlite3.connect(legacy)
        try:
            self.assertEqual(
                connection.execute("PRAGMA journal_mode=WAL").fetchone(),
                ("wal",),
            )
            connection.execute("PRAGMA wal_autocheckpoint=0")
            connection.execute("CREATE TABLE migration_probe (value TEXT NOT NULL)")
            connection.execute(
                "INSERT INTO migration_probe (value) VALUES (?)",
                ("preserve-me",),
            )
            connection.commit()
            self.assertTrue(Path(f"{legacy}-wal").is_file())

            result = migrate_layout(self.root, source_root=SOURCE_ROOT)
        finally:
            connection.close()

        canonical = (
            HarnessPaths(self.root).state / "memory" / "long_term" / "harness.db"
        )
        self.assertTrue(result.changed)
        self.assertTrue(canonical.is_file())
        self.assertFalse(Path(f"{canonical}-wal").exists())
        self.assertFalse(Path(f"{canonical}-shm").exists())
        with sqlite3.connect(canonical) as connection:
            row = connection.execute("SELECT value FROM migration_probe").fetchone()
            integrity = connection.execute("PRAGMA integrity_check").fetchone()
        self.assertEqual(row, ("preserve-me",))
        self.assertEqual(integrity, ("ok",))
        if os.name != "nt":
            self.assertEqual(stat.S_IMODE(canonical.stat().st_mode), 0o600)
            self.assertEqual(
                stat.S_IMODE(HarnessPaths(self.root).state.stat().st_mode),
                0o700,
            )
        self.assertFalse((self.root / "memory").exists())
        self.assertIn("legacy-memory-state", load_manifest(self.root)["migrations"])

    def test_corrupt_legacy_sqlite_is_preserved_and_aborts_migration(self) -> None:
        paths = HarnessPaths(self.root)
        legacy = paths.legacy_memory / "long_term" / "harness.db"
        legacy.parent.mkdir(parents=True)
        original = b"not a sqlite database\n"
        legacy.write_bytes(original)

        with self.assertRaisesRegex(InstallConflictError, "legacy SQLite|integrity"):
            migrate_layout(self.root, source_root=SOURCE_ROOT)

        self.assertEqual(legacy.read_bytes(), original)
        self.assertFalse(
            (paths.state / "memory" / "long_term" / "harness.db").exists()
        )
        self.assertFalse(paths.manifest.exists())

    def test_logically_equal_sqlite_is_idempotent_despite_mode_difference(self) -> None:
        paths = HarnessPaths(self.root)
        legacy = paths.legacy_memory / "long_term" / "harness.db"
        canonical = paths.state / "memory" / "long_term" / "harness.db"
        for database in (legacy, canonical):
            database.parent.mkdir(parents=True, exist_ok=True)
            with sqlite3.connect(database) as connection:
                connection.execute(
                    "CREATE TABLE migration_probe (id INTEGER PRIMARY KEY, value TEXT)"
                )
                connection.execute(
                    "INSERT INTO migration_probe (id, value) VALUES (?, ?)",
                    (1, "same"),
                )
        if os.name != "nt":
            os.chmod(legacy, 0o600)
            os.chmod(canonical, 0o644)

        result = migrate_layout(self.root, source_root=SOURCE_ROOT)

        self.assertNotIn("memory/long_term/harness.db", result.conflicts)
        self.assertFalse(paths.legacy_memory.exists())
        with sqlite3.connect(canonical) as connection:
            self.assertEqual(
                connection.execute("SELECT id, value FROM migration_probe").fetchall(),
                [(1, "same")],
            )
        if os.name != "nt":
            self.assertEqual(stat.S_IMODE(canonical.stat().st_mode), 0o600)

    def test_divergent_canonical_sqlite_is_preserved_as_conflict(self) -> None:
        paths = HarnessPaths(self.root)
        legacy = paths.legacy_memory / "long_term" / "harness.db"
        canonical = paths.state / "memory" / "long_term" / "harness.db"
        for database, value in ((legacy, "legacy"), (canonical, "canonical")):
            database.parent.mkdir(parents=True, exist_ok=True)
            with sqlite3.connect(database) as connection:
                connection.execute("CREATE TABLE migration_probe (value TEXT)")
                connection.execute(
                    "INSERT INTO migration_probe (value) VALUES (?)",
                    (value,),
                )

        result = migrate_layout(self.root, source_root=SOURCE_ROOT)

        self.assertIn("memory/long_term/harness.db", result.conflicts)
        for database, expected in ((legacy, "legacy"), (canonical, "canonical")):
            with sqlite3.connect(database) as connection:
                self.assertEqual(
                    connection.execute("SELECT value FROM migration_probe").fetchone(),
                    (expected,),
                )

    def test_unrelated_root_memory_files_are_not_claimed_by_migration(self) -> None:
        product_memory = self.root / "memory" / "product-owned.bin"
        product_memory.parent.mkdir()
        product_memory.write_bytes(b"consumer data\n")

        result = migrate_layout(self.root, source_root=SOURCE_ROOT)

        self.assertNotIn("memory/product-owned.bin", result.conflicts)
        self.assertEqual(product_memory.read_bytes(), b"consumer data\n")
        self.assertFalse(
            (HarnessPaths(self.root).state / "memory" / "product-owned.bin").exists()
        )

    def test_failed_install_restores_legacy_sqlite_after_verified_backup(self) -> None:
        paths = HarnessPaths(self.root)
        legacy = paths.legacy_sqlite_database
        legacy.parent.mkdir(parents=True)
        with sqlite3.connect(legacy) as connection:
            connection.execute("CREATE TABLE migration_probe (value TEXT)")
            connection.execute(
                "INSERT INTO migration_probe (value) VALUES (?)",
                ("preserve-after-failure",),
            )

        with patch(
            "solomon_harness.host_adapters.compile_adapters",
            side_effect=RuntimeError("renderer failed after SQLite migration"),
        ):
            with self.assertRaisesRegex(
                RuntimeError,
                "renderer failed after SQLite migration",
            ):
                migrate_layout(self.root, source_root=SOURCE_ROOT)

        self.assertTrue(legacy.is_file())
        with sqlite3.connect(legacy) as connection:
            self.assertEqual(
                connection.execute("SELECT value FROM migration_probe").fetchone(),
                ("preserve-after-failure",),
            )
        self.assertFalse(paths.sqlite_database.exists())
        self.assertFalse(paths.manifest.exists())

    def test_previous_canonical_handoffs_migrate_below_state(self) -> None:
        paths = HarnessPaths(self.root)
        previous = paths.previous_handoffs / "review" / "issue-240.md"
        previous.parent.mkdir(parents=True)
        previous.write_text("handoff\n", encoding="utf-8")
        os.chmod(previous, 0o600)
        adapter_result = SimpleNamespace(changed=False, conflicts=(), managed_paths=())

        with patch(
            "solomon_harness.host_adapters.compile_adapters",
            return_value=adapter_result,
        ):
            result = migrate_layout(self.root, source_root=SOURCE_ROOT)

        migrated = paths.handoffs / "review" / "issue-240.md"
        self.assertTrue(result.changed)
        self.assertEqual(migrated.read_text(encoding="utf-8"), "handoff\n")
        self.assertEqual(stat.S_IMODE(migrated.stat().st_mode), 0o600)
        self.assertFalse(paths.previous_handoffs.exists())
        self.assertIn("canonical-handoffs-to-state", load_manifest(self.root)["migrations"])

    def test_divergent_previous_handoff_is_preserved_as_conflict(self) -> None:
        paths = HarnessPaths(self.root)
        previous = paths.previous_handoffs / "review" / "issue-240.md"
        previous.parent.mkdir(parents=True)
        previous.write_text("older handoff\n", encoding="utf-8")
        canonical = paths.handoffs / "review" / "issue-240.md"
        canonical.parent.mkdir(parents=True)
        canonical.write_text("canonical handoff\n", encoding="utf-8")
        adapter_result = SimpleNamespace(changed=False, conflicts=(), managed_paths=())

        with patch(
            "solomon_harness.host_adapters.compile_adapters",
            return_value=adapter_result,
        ):
            result = migrate_layout(self.root, source_root=SOURCE_ROOT)

        self.assertIn(
            previous.relative_to(self.root).as_posix(),
            result.conflicts,
        )
        self.assertEqual(previous.read_text(encoding="utf-8"), "older handoff\n")
        self.assertEqual(canonical.read_text(encoding="utf-8"), "canonical handoff\n")

    def test_exact_legacy_payload_is_rehomed_and_removed_from_project_roots(self) -> None:
        _copy_legacy_payload(self.root)

        result = install_project(self.root, source_root=SOURCE_ROOT)

        self.assertTrue(result.changed)
        for legacy_root in ("agents", "scripts", "solomon_harness"):
            self.assertFalse((self.root / legacy_root).exists(), legacy_root)
        paths = HarnessPaths(self.root)
        self.assertTrue((paths.agents / "qa" / "persona.md").is_file())
        self.assertTrue((paths.solomon / "scripts" / "generate-integrations.py").is_file())
        self.assertTrue((paths.solomon / "solomon_harness" / "cli.py").is_file())

    def test_legacy_cleanup_preserves_and_reports_modified_unrelated_and_gemini(self) -> None:
        _copy_legacy_payload(self.root)
        modified = self.root / "scripts" / "generate-integrations.py"
        modified.write_text("# locally modified\n", encoding="utf-8")
        unrelated = self.root / "scripts" / "consumer-task.sh"
        unrelated.write_text("#!/bin/sh\n", encoding="utf-8")
        gemini = self.root / ".gemini" / "commands" / "custom.md"
        gemini.parent.mkdir(parents=True)
        gemini.write_text("consumer-owned\n", encoding="utf-8")
        legacy_convention = self.root / "docs" / "solomon-workflow.md"
        legacy_convention.parent.mkdir(exist_ok=True)
        shutil.copy2(SOURCE_ROOT / "docs" / "solomon-workflow.md", legacy_convention)

        result = install_project(self.root, source_root=SOURCE_ROOT)

        self.assertEqual(modified.read_text(encoding="utf-8"), "# locally modified\n")
        self.assertTrue(unrelated.is_file())
        self.assertTrue(gemini.is_file())
        self.assertTrue(legacy_convention.is_file())
        self.assertTrue(
            {
                "scripts/generate-integrations.py",
                "scripts/consumer-task.sh",
                ".gemini/commands/custom.md",
            }
            <= set(result.conflicts)
        )
        self.assertFalse((self.root / "agents").exists())
        self.assertFalse((self.root / "solomon_harness").exists())

    def test_legacy_cleanup_recognizes_v011_and_preserves_one_modified_file(
        self,
    ) -> None:
        fixture = SOURCE_ROOT / "tests" / "fixtures" / "legacy-v0.11.0"
        shutil.rmtree(self.root / ".claude")
        (self.root / "README.md").unlink()
        (self.root / "pyproject.toml").unlink()
        shutil.copytree(fixture, self.root, dirs_exist_ok=True)
        for path in (
            self.root / "agents" / "flutter" / "skills" / "navigation.md",
            self.root / "agents" / "quant_trader" / "skills" / "tooling.md",
            self.root / "solomon_harness" / "notify.py",
        ):
            os.chmod(path, 0o644)
        hook = self.root / "scripts" / "git-hooks" / "pre-commit"
        os.chmod(hook, 0o755)
        modified = self.root / "agents" / "quant_trader" / "skills" / "tooling.md"
        modified.write_text(
            modified.read_text(encoding="utf-8") + "\nLocal project change.\n",
            encoding="utf-8",
        )
        result = install_project(self.root, source_root=SOURCE_ROOT)

        self.assertIn(modified.relative_to(self.root).as_posix(), result.conflicts)
        self.assertIn("Local project change.", modified.read_text(encoding="utf-8"))
        self.assertFalse((self.root / "agents" / "flutter" / "skills" / "navigation.md").exists())
        self.assertFalse(hook.exists())
        self.assertFalse((self.root / "solomon_harness" / "notify.py").exists())
        self.assertFalse((self.root / ".gemini").exists())
        self.assertFalse((self.root / "GEMINI.md").exists())
        self.assertFalse((self.root / "CLAUDE.md").exists())
        self.assertFalse((self.root / "README.md").exists())
        self.assertFalse((self.root / "pyproject.toml").exists())
        self.assertFalse((self.root / "skill-sources.json").exists())
        self.assertTrue((self.root / "AGENTS.md").is_file())
        self.assertIn(
            ".agents/solomon/AGENTS.md",
            (self.root / "AGENTS.md").read_text(encoding="utf-8"),
        )
        mcp = json.loads((self.root / ".mcp.json").read_text(encoding="utf-8"))
        self.assertEqual(
            mcp["mcpServers"]["solomon-memory"]["args"][:4],
            ["run", "--frozen", "--project", ".agents/solomon"],
        )
        self.assertIn(
            ".agents/solomon/agents/qa",
            (self.root / ".claude" / "agents" / "qa.md").read_text(
                encoding="utf-8"
            ),
        )

    def test_v011_modified_shared_json_adapters_migrate_only_legacy_nodes(self) -> None:
        fixture = SOURCE_ROOT / "tests" / "fixtures" / "legacy-v0.11.0"
        for directory in ("agents", "scripts", "solomon_harness"):
            shutil.copytree(fixture / directory, self.root / directory)
        for path in (
            self.root / "agents" / "flutter" / "skills" / "navigation.md",
            self.root / "agents" / "quant_trader" / "skills" / "tooling.md",
            self.root / "solomon_harness" / "notify.py",
        ):
            os.chmod(path, 0o644)
        os.chmod(self.root / "scripts" / "git-hooks" / "pre-commit", 0o755)

        legacy_mcp = json.loads((fixture / ".mcp.json").read_text(encoding="utf-8"))
        legacy_mcp["mcpServers"]["consumer-server"] = {
            "command": "consumer-mcp",
            "args": ["serve"],
        }
        (self.root / ".mcp.json").write_text(
            json.dumps(legacy_mcp, indent=2) + "\n",
            encoding="utf-8",
        )
        legacy_settings = json.loads(
            (fixture / ".claude" / "settings.json").read_text(encoding="utf-8")
        )
        legacy_settings["consumer-setting"] = True
        (self.root / ".claude" / "settings.json").write_text(
            json.dumps(legacy_settings, indent=2) + "\n",
            encoding="utf-8",
        )

        result = install_project(self.root, source_root=SOURCE_ROOT)

        self.assertNotIn(".mcp.json", result.conflicts)
        self.assertNotIn(".claude/settings.json", result.conflicts)
        mcp = json.loads((self.root / ".mcp.json").read_text(encoding="utf-8"))
        self.assertEqual(mcp["mcpServers"]["consumer-server"]["command"], "consumer-mcp")
        self.assertEqual(
            mcp["mcpServers"]["solomon-memory"]["args"][:4],
            ["run", "--frozen", "--project", ".agents/solomon"],
        )
        settings = json.loads(
            (self.root / ".claude" / "settings.json").read_text(encoding="utf-8")
        )
        self.assertIs(settings["consumer-setting"], True)
        serialized_hooks = json.dumps(settings["hooks"], sort_keys=True)
        self.assertNotIn("uv run python -m solomon_harness.cli", serialized_hooks)
        self.assertIn("solomon_harness.cli host-hook", serialized_hooks)

    def test_unowned_gemini_tree_is_preserved_and_reported_without_legacy_signature(self) -> None:
        gemini = self.root / ".gemini" / "commands" / "custom.md"
        gemini.parent.mkdir(parents=True)
        gemini.write_text("consumer-owned\n", encoding="utf-8")

        result = install_project(self.root, source_root=SOURCE_ROOT)

        self.assertEqual(gemini.read_text(encoding="utf-8"), "consumer-owned\n")
        self.assertIn(".gemini/commands/custom.md", result.conflicts)

    def test_modified_owned_file_is_preserved_as_conflict(self) -> None:
        install_project(self.root, source_root=SOURCE_ROOT)
        target = self.root / ".claude" / "agents" / "qa.md"
        target.write_text("user changed this\n", encoding="utf-8")

        result = install_project(self.root, source_root=SOURCE_ROOT)

        self.assertIn(target.relative_to(self.root).as_posix(), result.conflicts)
        self.assertEqual(target.read_text(encoding="utf-8"), "user changed this\n")

    def test_upgrade_preserves_mode_only_changes_for_core_and_adapter(self) -> None:
        install_project(self.root, source_root=SOURCE_ROOT)
        core = HarnessPaths(self.root).python_package / "cli.py"
        adapter = self.root / ".claude" / "agents" / "qa.md"
        core_bytes = core.read_bytes()
        adapter_bytes = adapter.read_bytes()
        os.chmod(core, 0o600)
        os.chmod(adapter, 0o600)

        result = install_project(self.root, source_root=SOURCE_ROOT)

        expected = {
            core.relative_to(self.root).as_posix(),
            adapter.relative_to(self.root).as_posix(),
        }
        self.assertTrue(expected <= set(result.conflicts))
        self.assertEqual(core.read_bytes(), core_bytes)
        self.assertEqual(adapter.read_bytes(), adapter_bytes)
        self.assertEqual(stat.S_IMODE(core.stat().st_mode), 0o600)
        self.assertEqual(stat.S_IMODE(adapter.stat().st_mode), 0o600)
        manifest_entries = {entry["path"]: entry for entry in load_manifest(self.root)["entries"]}
        self.assertEqual(manifest_entries[core.relative_to(self.root).as_posix()]["mode"], "0644")
        self.assertEqual(
            manifest_entries[adapter.relative_to(self.root).as_posix()]["mode"],
            "0644",
        )

    def test_upgrade_preserves_mode_only_change_on_stale_core_file(self) -> None:
        install_project(self.root, source_root=SOURCE_ROOT)
        paths = HarnessPaths(self.root)
        stale = paths.solomon / "obsolete-owned.txt"
        stale.write_text("old release\n", encoding="utf-8")
        os.chmod(stale, 0o644)
        manifest = load_manifest(self.root)
        relative = stale.relative_to(self.root).as_posix()
        manifest["entries"].append(
            {
                "mode": "0644",
                "owner": "core",
                "path": relative,
                "sha256": hashlib.sha256(stale.read_bytes()).hexdigest(),
                "strategy": "replace",
            }
        )
        manifest["entries"] = sorted(manifest["entries"], key=lambda entry: entry["path"])
        paths.manifest.write_text(
            json.dumps(manifest, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        os.chmod(stale, 0o600)

        result = install_project(self.root, source_root=SOURCE_ROOT)

        self.assertIn(relative, result.conflicts)
        self.assertEqual(stale.read_text(encoding="utf-8"), "old release\n")
        self.assertEqual(stat.S_IMODE(stale.stat().st_mode), 0o600)
        entry = next(
            entry for entry in load_manifest(self.root)["entries"] if entry["path"] == relative
        )
        self.assertEqual(entry["mode"], "0644")

    def test_preexisting_reserved_mcp_names_are_preserved_for_all_hosts(self) -> None:
        custom = {"command": "custom-memory", "args": ["serve"]}
        (self.root / ".mcp.json").write_text(
            json.dumps({"mcpServers": {"solomon-memory": custom}}),
            encoding="utf-8",
        )
        agy_mcp = HarnessPaths(self.root).agy_mcp
        agy_mcp.parent.mkdir(parents=True)
        agy_mcp.write_text(
            json.dumps({"mcpServers": {"solomon-memory": custom}}),
            encoding="utf-8",
        )
        with (self.root / ".codex" / "config.toml").open("a", encoding="utf-8") as stream:
            stream.write(
                '\n[mcp_servers.solomon-memory]\ncommand = "custom-memory"\nargs = ["serve"]\n'
            )

        result = install_project(self.root, source_root=SOURCE_ROOT)

        self.assertTrue(
            {
                ".mcp.json",
                ".agents/plugins/solomon/mcp_config.json",
                ".codex/config.toml",
            }
            <= set(result.conflicts)
        )
        self.assertEqual(
            json.loads((self.root / ".mcp.json").read_text(encoding="utf-8"))["mcpServers"][
                "solomon-memory"
            ],
            custom,
        )
        self.assertEqual(
            json.loads(agy_mcp.read_text(encoding="utf-8"))["mcpServers"]["solomon-memory"],
            custom,
        )
        self.assertIn(
            'command = "custom-memory"',
            (self.root / ".codex" / "config.toml").read_text(encoding="utf-8"),
        )

    def test_upgrade_changes_owned_mcp_fragments_after_unrelated_user_edits(self) -> None:
        install_project(self.root, source_root=SOURCE_ROOT)
        json_paths = (self.root / ".mcp.json", HarnessPaths(self.root).agy_mcp)
        for path in json_paths:
            document = json.loads(path.read_text(encoding="utf-8"))
            document["consumer"] = {"keep": True}
            path.write_text(json.dumps(document, indent=2), encoding="utf-8")
        codex = self.root / ".codex" / "config.toml"
        with codex.open("a", encoding="utf-8") as stream:
            stream.write("\n[consumer]\nkeep = true\n")

        with patch("solomon_harness.host_adapters._MCP_COMMAND", "uvx"):
            result = install_project(self.root, source_root=SOURCE_ROOT)

        expected = {
            ".mcp.json",
            ".agents/plugins/solomon/mcp_config.json",
            ".codex/config.toml",
        }
        self.assertTrue(expected.isdisjoint(result.conflicts))
        for path in json_paths:
            document = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(document["consumer"], {"keep": True})
            self.assertEqual(
                document["mcpServers"]["solomon-memory"]["command"], "uvx"
            )
        codex_text = codex.read_text(encoding="utf-8")
        self.assertIn("[consumer]", codex_text)
        self.assertIn('command = "uvx"', codex_text)

    def test_preexisting_reserved_hook_nodes_are_preserved_for_all_hosts(self) -> None:
        claude_custom = {
            "hooks": {
                "SessionStart": [
                    {
                        "hooks": [
                            {
                                "type": "command",
                                "command": (
                                    "uv run python -m solomon_harness.cli host-hook "
                                    "session-start --host claude --custom"
                                ),
                            }
                        ]
                    }
                ]
            }
        }
        (self.root / ".claude" / "settings.json").write_text(
            json.dumps(claude_custom), encoding="utf-8"
        )
        agy_hooks = self.root / ".agents" / "hooks.json"
        agy_hooks.parent.mkdir()
        agy_hooks.write_text(
            json.dumps({"solomon-loop-guard": {"custom": True}}),
            encoding="utf-8",
        )
        codex_config = self.root / ".codex" / "config.toml"
        with codex_config.open("a", encoding="utf-8") as stream:
            stream.write(
                "\n[[hooks.PreToolUse]]\n"
                'matcher = "Bash"\n\n'
                "[[hooks.PreToolUse.hooks]]\n"
                'type = "command"\n'
                'command = "solomon_harness.cli host-hook pre-tool-use '
                '--host codex --custom"\n'
                "timeout = 30\n"
            )

        result = install_project(self.root, source_root=SOURCE_ROOT)

        expected = {
            ".claude/settings.json",
            ".agents/hooks.json",
            ".codex/config.toml",
        }
        self.assertTrue(expected <= set(result.conflicts))
        self.assertIn("--custom", (self.root / ".claude" / "settings.json").read_text())
        self.assertIn('"custom": true', agy_hooks.read_text())
        self.assertIn("--custom", codex_config.read_text())

    def test_uninstall_removes_only_unchanged_owned_files(self) -> None:
        install_project(self.root, source_root=SOURCE_ROOT)
        modified = self.root / ".claude" / "agents" / "qa.md"
        modified.write_text("custom qa\n", encoding="utf-8")
        state_file = HarnessPaths(self.root).state / "keep.txt"
        state_file.parent.mkdir(parents=True, exist_ok=True)
        state_file.write_text("state", encoding="utf-8")

        result = uninstall_project(self.root)

        self.assertIn(modified.relative_to(self.root).as_posix(), result.conflicts)
        self.assertTrue(modified.is_file())
        self.assertTrue(state_file.is_file())
        self.assertTrue(HarnessPaths(self.root).config.is_file())
        self.assertEqual(
            json.loads((self.root / ".claude" / "settings.json").read_text(encoding="utf-8"))[
                "permissions"
            ],
            {"allow": ["Bash(git status:*)"]},
        )
        settings_text = (self.root / ".claude" / "settings.json").read_text(encoding="utf-8")
        self.assertNotIn("solomon_harness.cli host-hook", settings_text)
        root_instructions = self.root / "AGENTS.md"
        if root_instructions.exists():
            self.assertNotIn(
                "solomon-harness managed adapter",
                root_instructions.read_text(encoding="utf-8"),
            )
        mcp_config = self.root / ".mcp.json"
        if mcp_config.exists():
            self.assertNotIn("solomon-memory", mcp_config.read_text(encoding="utf-8"))
        codex_config = (self.root / ".codex" / "config.toml").read_text(encoding="utf-8")
        self.assertIn('model = "host-owned"', codex_config)
        self.assertNotIn("solomon-harness managed adapter", codex_config)
        agy_hooks = self.root / ".agents" / "hooks.json"
        if agy_hooks.exists():
            self.assertNotIn("solomon-", agy_hooks.read_text(encoding="utf-8"))
        self.assertTrue((self.root / "docs" / "adrs" / "README.md").is_file())
        self.assertTrue((self.root / "docs" / "specs" / "README.md").is_file())
        self.assertTrue((self.root / ".github" / "PULL_REQUEST_TEMPLATE.md").is_file())

    def test_uninstall_preserves_every_diverged_managed_adapter_fragment(self) -> None:
        install_project(self.root, source_root=SOURCE_ROOT)

        root_instructions = self.root / "AGENTS.md"
        root_instructions.write_text(
            root_instructions.read_text(encoding="utf-8").replace(
                "Read that file completely before starting work.",
                "Keep this user-modified managed instruction.",
            ),
            encoding="utf-8",
        )

        codex_config = self.root / ".codex" / "config.toml"
        codex_config.write_text(
            codex_config.read_text(encoding="utf-8").replace(
                "required = true",
                "required = false",
            ).replace(
                "host-hook session-start --host codex",
                "host-hook session-start --host codex --custom",
            ),
            encoding="utf-8",
        )

        mcp = self.root / ".mcp.json"
        mcp_document = json.loads(mcp.read_text(encoding="utf-8"))
        mcp_document["mcpServers"]["solomon-memory"]["args"].append("--custom")
        mcp.write_text(json.dumps(mcp_document), encoding="utf-8")

        agy_mcp = HarnessPaths(self.root).agy_mcp
        agy_mcp_document = json.loads(agy_mcp.read_text(encoding="utf-8"))
        agy_mcp_document["mcpServers"]["solomon-memory"]["env"]["UV_PROJECT_ENVIRONMENT"] = (
            "custom-venv"
        )
        agy_mcp.write_text(json.dumps(agy_mcp_document), encoding="utf-8")

        claude_settings = self.root / ".claude" / "settings.json"
        claude_document = json.loads(claude_settings.read_text(encoding="utf-8"))
        claude_document["hooks"]["SessionStart"][0]["hooks"][0]["command"] += " --custom"
        claude_settings.write_text(json.dumps(claude_document), encoding="utf-8")

        agy_hooks = self.root / ".agents" / "hooks.json"
        agy_document = json.loads(agy_hooks.read_text(encoding="utf-8"))
        agy_document["solomon-loop-guard"]["PreToolUse"][0]["hooks"][0]["timeout"] = 999
        agy_hooks.write_text(json.dumps(agy_document), encoding="utf-8")

        result = uninstall_project(self.root)

        diverged = {
            "AGENTS.md",
            ".codex/config.toml",
            ".mcp.json",
            ".agents/plugins/solomon/mcp_config.json",
            ".claude/settings.json",
            ".agents/hooks.json",
        }
        self.assertTrue(diverged <= set(result.conflicts))
        self.assertTrue(diverged.isdisjoint(result.removed))
        self.assertIn("user-modified", root_instructions.read_text(encoding="utf-8"))
        self.assertIn("required = false", codex_config.read_text(encoding="utf-8"))
        self.assertIn("--custom", mcp.read_text(encoding="utf-8"))
        self.assertIn("custom-venv", agy_mcp.read_text(encoding="utf-8"))
        self.assertIn("--custom", claude_settings.read_text(encoding="utf-8"))
        self.assertIn('"timeout": 999', agy_hooks.read_text(encoding="utf-8"))
        self.assertIn("--custom", codex_config.read_text(encoding="utf-8"))

    def test_uninstall_preserves_mode_only_changes_for_core_and_merged_adapter(
        self,
    ) -> None:
        install_project(self.root, source_root=SOURCE_ROOT)
        core = HarnessPaths(self.root).python_package / "cli.py"
        adapter = self.root / ".claude" / "settings.json"
        core_bytes = core.read_bytes()
        adapter_bytes = adapter.read_bytes()
        os.chmod(core, 0o600)
        os.chmod(adapter, 0o600)

        result = uninstall_project(self.root)

        expected = {
            core.relative_to(self.root).as_posix(),
            adapter.relative_to(self.root).as_posix(),
        }
        self.assertTrue(expected <= set(result.conflicts))
        self.assertTrue(expected.isdisjoint(result.removed))
        self.assertEqual(core.read_bytes(), core_bytes)
        self.assertEqual(adapter.read_bytes(), adapter_bytes)
        self.assertEqual(stat.S_IMODE(core.stat().st_mode), 0o600)
        self.assertEqual(stat.S_IMODE(adapter.stat().st_mode), 0o600)

    def test_preexisting_identical_project_scaffold_is_never_claimed_or_removed(self) -> None:
        source = SOURCE_ROOT / "docs" / "adrs" / "README.md"
        target = self.root / "docs" / "adrs" / "README.md"
        target.parent.mkdir(parents=True)
        target.write_bytes(source.read_bytes())

        install_project(self.root, source_root=SOURCE_ROOT)
        entry_paths = {entry["path"] for entry in load_manifest(self.root)["entries"]}
        self.assertNotIn("docs/adrs/README.md", entry_paths)

        uninstall_project(self.root)
        self.assertEqual(target.read_bytes(), source.read_bytes())

    def test_malicious_manifest_path_fails_closed(self) -> None:
        install_project(self.root, source_root=SOURCE_ROOT)
        outside = self.root.parent / "outside-solomon-test.txt"
        outside.write_text("safe", encoding="utf-8")
        manifest_path = HarnessPaths(self.root).manifest
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["entries"].append(
            {
                "path": "../outside-solomon-test.txt",
                "owner": "core",
                "strategy": "replace",
                "sha256": hashlib.sha256(b"safe").hexdigest(),
                "mode": "0644",
            }
        )
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
        try:
            with self.assertRaises(InstallConflictError):
                uninstall_project(self.root)
            self.assertEqual(outside.read_text(encoding="utf-8"), "safe")
        finally:
            outside.unlink(missing_ok=True)

    def test_manifest_symlink_is_rejected_without_trusting_external_json(self) -> None:
        outside = self.root.parent / f"{self.root.name}-external-manifest.json"
        outside.write_text(
            json.dumps({"schema_version": 1, "entries": []}),
            encoding="utf-8",
        )
        manifest = HarnessPaths(self.root).manifest
        manifest.parent.mkdir(parents=True)
        manifest.symlink_to(outside)
        try:
            with self.assertRaisesRegex(InstallConflictError, "symlink"):
                load_manifest(self.root)
            self.assertEqual(
                json.loads(outside.read_text(encoding="utf-8")),
                {"schema_version": 1, "entries": []},
            )
        finally:
            manifest.unlink(missing_ok=True)
            outside.unlink(missing_ok=True)

    def test_manifest_cannot_claim_an_unmanaged_project_file(self) -> None:
        install_project(self.root, source_root=SOURCE_ROOT)
        readme = self.root / "README.md"
        manifest_path = HarnessPaths(self.root).manifest
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["entries"].append(
            {
                "path": "README.md",
                "owner": "core",
                "strategy": "replace",
                "sha256": hashlib.sha256(readme.read_bytes()).hexdigest(),
                "mode": "0644",
            }
        )
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

        with self.assertRaises(InstallConflictError):
            uninstall_project(self.root)

        self.assertEqual(readme.read_text(encoding="utf-8"), "# Consumer\n")

    def test_adapter_symlink_cannot_write_outside_the_workspace(self) -> None:
        outside = self.root.parent / "outside-solomon-mcp.json"
        outside.write_text('{"safe": true}\n', encoding="utf-8")
        mcp_path = self.root / ".mcp.json"
        mcp_path.symlink_to(outside)
        try:
            with self.assertRaises(InstallConflictError):
                install_project(self.root, source_root=SOURCE_ROOT)
            self.assertEqual(outside.read_text(encoding="utf-8"), '{"safe": true}\n')
        finally:
            mcp_path.unlink(missing_ok=True)
            outside.unlink(missing_ok=True)

    def test_legacy_config_symlink_cannot_import_an_external_file(self) -> None:
        outside = self.root.parent / "outside-solomon-config.json"
        outside.write_text('{"secret": "keep"}\n', encoding="utf-8")
        legacy = self.root / ".agent" / "config.json"
        legacy.parent.mkdir()
        legacy.symlink_to(outside)
        try:
            with self.assertRaises(InstallConflictError):
                install_project(self.root, source_root=SOURCE_ROOT)
            self.assertEqual(
                outside.read_text(encoding="utf-8"),
                '{"secret": "keep"}\n',
            )
        finally:
            legacy.unlink(missing_ok=True)
            outside.unlink(missing_ok=True)

    def test_legacy_state_symlink_cannot_remove_external_files(self) -> None:
        outside = self.root.parent / "outside-solomon-state"
        outside.mkdir()
        victim = outside / "keep.txt"
        victim.write_text("keep\n", encoding="utf-8")
        legacy = self.root / ".solomon"
        legacy.symlink_to(outside, target_is_directory=True)
        try:
            with self.assertRaises(InstallConflictError):
                install_project(self.root, source_root=SOURCE_ROOT)
            self.assertEqual(victim.read_text(encoding="utf-8"), "keep\n")
        finally:
            legacy.unlink(missing_ok=True)
            victim.unlink(missing_ok=True)
            outside.rmdir()

    def test_legacy_migration_rejects_canonical_destination_symlink_before_writing(self) -> None:
        outside = self.root.parent / f"{self.root.name}-outside-state"
        outside.mkdir()
        legacy = self.root / ".solomon" / "memory-mirror" / "decision" / "one.md"
        legacy.parent.mkdir(parents=True)
        legacy.write_text("legacy decision\n", encoding="utf-8")
        state = HarnessPaths(self.root).state
        state.mkdir(parents=True)
        (state / "memory-mirror").symlink_to(outside, target_is_directory=True)
        try:
            with self.assertRaisesRegex(InstallConflictError, "symlink|escapes"):
                install_project(self.root, source_root=SOURCE_ROOT)
            self.assertFalse((outside / "decision" / "one.md").exists())
            self.assertEqual(legacy.read_text(encoding="utf-8"), "legacy decision\n")
            self.assertFalse(HarnessPaths(self.root).manifest.exists())
        finally:
            (state / "memory-mirror").unlink(missing_ok=True)
            shutil.rmtree(outside)

    def test_previous_handoff_migration_rejects_destination_symlink_before_writing(
        self,
    ) -> None:
        paths = HarnessPaths(self.root)
        previous = paths.previous_handoffs / "review" / "issue-240.md"
        previous.parent.mkdir(parents=True)
        previous.write_text("legacy handoff\n", encoding="utf-8")
        outside = self.root.parent / f"{self.root.name}-outside-handoffs"
        outside.mkdir()
        paths.handoffs.mkdir(parents=True)
        (paths.handoffs / "review").symlink_to(outside, target_is_directory=True)

        try:
            with self.assertRaisesRegex(InstallConflictError, "symlink|escapes"):
                install_project(self.root, source_root=SOURCE_ROOT)
            self.assertEqual(previous.read_text(encoding="utf-8"), "legacy handoff\n")
            self.assertFalse((outside / "issue-240.md").exists())
            self.assertFalse(paths.manifest.exists())
        finally:
            (paths.handoffs / "review").unlink(missing_ok=True)
            outside.rmdir()

    def test_failed_adapter_compile_rolls_back_the_fresh_install(self) -> None:
        before = _snapshot(self.root)

        with patch(
            "solomon_harness.host_adapters.compile_adapters",
            side_effect=RuntimeError("renderer failed"),
        ):
            with self.assertRaisesRegex(RuntimeError, "renderer failed"):
                install_project(self.root, source_root=SOURCE_ROOT)

        self.assertEqual(_snapshot(self.root), before)
        self.assertFalse(HarnessPaths(self.root).rules.exists())
        self.assertFalse((self.root / "AGENTS.md").exists())

    def test_failed_install_rolls_back_both_sides_of_legacy_state_migration(self) -> None:
        legacy = self.root / ".solomon" / "memory-mirror" / "decision" / "one.md"
        legacy.parent.mkdir(parents=True)
        legacy.write_text("legacy decision\n", encoding="utf-8")
        os.chmod(legacy, 0o600)
        before = _snapshot(self.root)

        with patch(
            "solomon_harness.host_adapters.compile_adapters",
            side_effect=RuntimeError("renderer failed after migration"),
        ):
            with self.assertRaisesRegex(RuntimeError, "renderer failed after migration"):
                install_project(self.root, source_root=SOURCE_ROOT)

        self.assertEqual(_snapshot(self.root), before)
        self.assertTrue(legacy.is_file())
        self.assertFalse(
            (HarnessPaths(self.root).state / "memory-mirror" / "decision" / "one.md").exists()
        )
        self.assertFalse(HarnessPaths(self.root).rules.exists())

    def test_failed_install_rolls_back_previous_handoff_migration(self) -> None:
        paths = HarnessPaths(self.root)
        previous = paths.previous_handoffs / "review" / "issue-240.md"
        previous.parent.mkdir(parents=True)
        previous.write_text("legacy handoff\n", encoding="utf-8")
        os.chmod(previous, 0o600)
        before = _snapshot(self.root)

        with patch(
            "solomon_harness.host_adapters.compile_adapters",
            side_effect=RuntimeError("renderer failed after handoff migration"),
        ):
            with self.assertRaisesRegex(
                RuntimeError,
                "renderer failed after handoff migration",
            ):
                install_project(self.root, source_root=SOURCE_ROOT)

        self.assertEqual(_snapshot(self.root), before)
        self.assertTrue(previous.is_file())
        self.assertFalse((paths.handoffs / "review" / "issue-240.md").exists())

    def test_failed_compile_rolls_back_adapters_for_custom_canonical_specialist(self) -> None:
        custom = HarnessPaths(self.root).agents / "local_specialist"
        role = custom / "agents" / "local_specialist.md"
        role.parent.mkdir(parents=True)
        role.write_text("# Local specialist\n", encoding="utf-8")
        before = _snapshot(self.root)

        def render_then_fail(root: Path) -> None:
            workspace = Path(root)
            outputs = {
                workspace / ".agents" / "agents" / "local_specialist" / "agent.md": "agy",
                workspace / ".claude" / "agents" / "local_specialist.md": "claude",
                workspace / ".codex" / "agents" / "local_specialist.toml": "codex",
            }
            for path, content in outputs.items():
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(content, encoding="utf-8")
                record_install_mutation(path)
            raise RuntimeError("custom adapter failed")

        with patch(
            "solomon_harness.host_adapters.compile_adapters",
            side_effect=render_then_fail,
        ):
            with self.assertRaisesRegex(RuntimeError, "custom adapter failed"):
                install_project(self.root, source_root=SOURCE_ROOT)

        self.assertEqual(_snapshot(self.root), before)

    def test_code_index_excludes_harness_and_host_bridges(self) -> None:
        install_project(self.root, source_root=SOURCE_ROOT)

        class Memory:
            def __init__(self) -> None:
                self.values: dict[str, str] = {}

            def get_memory(self, key: str):
                return self.values.get(key)

            def save_memory(self, key: str, value: str, category: str):
                self.values[key] = value

            def delete_memory(self, key: str):
                self.values.pop(key, None)

        db = Memory()
        index_codebase(str(self.root), db)
        manifest = json.loads(db.values["__code_index_manifest__"])
        self.assertIn("README.md", manifest)
        self.assertFalse(
            any(
                path == "AGENTS.md"
                or path == ".mcp.json"
                or path.startswith((".agents/", ".claude/", ".codex/"))
                for path in manifest
            )
        )


if __name__ == "__main__":
    unittest.main()
