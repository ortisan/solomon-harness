import os
import tempfile
import unittest
from unittest.mock import patch

from solomon_harness import agent_selection
from solomon_harness.agent_selection import (
    CORE_AGENTS,
    MAX_MANIFEST_BYTES,
    _manifest_text,
    select_agents,
)


def _project(files: dict) -> str:
    tmp = tempfile.mkdtemp()
    for rel, content in files.items():
        path = os.path.join(tmp, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
    return tmp


class TestAgentSelection(unittest.TestCase):
    def test_core_agents_always_selected(self):
        root = _project({"main.py": "print(1)", "pyproject.toml": "[project]\nname='x'"})
        selected = select_agents(root)
        for agent in CORE_AGENTS:
            self.assertIn(agent, selected)

    def test_agent_builder_in_core_agents(self):
        self.assertIn("agent_builder", CORE_AGENTS)


    def test_plain_python_does_not_pull_platform_agents(self):
        root = _project({"main.py": "print(1)", "requirements.txt": "requests\n"})
        selected = select_agents(root)
        for agent in ("flutter", "apple", "android", "frontend", "quant_trader"):
            self.assertNotIn(agent, selected)

    def test_flutter_signal(self):
        root = _project({"pubspec.yaml": "name: app\n", "lib/main.dart": "void main() {}"})
        self.assertIn("flutter", select_agents(root))

    def test_apple_signal(self):
        root = _project({"App.swift": "import SwiftUI"})
        self.assertIn("apple", select_agents(root))

    def test_android_signal(self):
        root = _project({"app/build.gradle": "android {}", "Main.kt": "fun main() {}"})
        self.assertIn("android", select_agents(root))

    def test_react_frontend_signal(self):
        root = _project({"package.json": '{"dependencies": {"react": "^18.0.0"}}', "app.tsx": "x"})
        selected = select_agents(root)
        self.assertIn("frontend", selected)
        self.assertIn("seo", selected)

    def test_ml_signal(self):
        root = _project({"pyproject.toml": "[project]\ndependencies=['torch','pandas']", "train.py": "x"})
        selected = select_agents(root)
        self.assertIn("ml_engineer", selected)
        self.assertIn("data_analyst", selected)

    def test_trading_signal(self):
        root = _project({"requirements.txt": "ccxt\nbacktrader\n", "strategy.py": "x"})
        self.assertIn("quant_trader", select_agents(root))

    def test_trading_signal_from_nested_monorepo_manifest(self):
        root = _project({
            "qtrader/packages/qtrader-strategy/pyproject.toml": (
                "[project.optional-dependencies]\ntalib = ['ta-lib>=0.5.1']\n"
            ),
            "qtrader/packages/qtrader-strategy/src/strategy.py": "x",
        })
        self.assertIn("quant_trader", select_agents(root))

    def test_manifest_beyond_scan_depth_is_ignored(self):
        root = _project({
            "main.py": "x",
            "one/two/three/four/five/requirements.txt": "ccxt\n",
        })
        self.assertNotIn("quant_trader", select_agents(root))

    def test_manifests_in_skipped_directories_are_ignored(self):
        files = {"main.py": "x"}
        for directory in (".git", "node_modules", ".venv", "__pycache__", "build", "dist"):
            files[f"{directory}/requirements.txt"] = "ccxt\n"
        root = _project(files)
        self.assertNotIn("quant_trader", select_agents(root))

    def test_solomon_control_trees_cannot_activate_an_agent(self):
        files = {
            "main.py": "x",
            "agents/quant_trader/agents/quant_trader.md": "# Quant Trader",
            "agents/quant_trader/persona.md": "# Quant Trader Persona",
            "agents/quant_trader/skills/scope.md": "# Scope",
        }
        for directory in (
            "agents",
            ".agent",
            ".agents",
            ".claude",
            ".gemini",
            ".solomon",
            ".solomon-harness",
            "solomon_harness",
        ):
            files[f"{directory}/activation/requirements.txt"] = "ccxt\n"
        root = _project(files)

        self.assertNotIn("quant_trader", select_agents(root))

    def test_manifest_scan_stops_when_total_read_budget_is_exhausted(self):
        first = "requests\n"
        root = _project({
            "main.py": "x",
            "a/requirements.txt": first,
            "b/requirements.txt": "ccxt\n",
        })
        opened = []
        real_open = open

        def recording_open(path, *args, **kwargs):
            if str(path).endswith("requirements.txt"):
                opened.append(str(path))
            return real_open(path, *args, **kwargs)

        with (
            patch.object(agent_selection, "MAX_MANIFEST_TOTAL_BYTES", len(first.encode())),
            patch("builtins.open", side_effect=recording_open),
        ):
            _manifest_text(root)

        self.assertEqual(opened, [os.path.join(root, "a", "requirements.txt")])

    def test_oversized_manifest_is_ignored(self):
        root = _project({
            "main.py": "x",
            "requirements.txt": "ccxt\n" + ("x" * MAX_MANIFEST_BYTES),
        })
        self.assertNotIn("quant_trader", select_agents(root))

    def test_auth_signal(self):
        root = _project({"requirements.txt": "authlib\n", "auth.py": "x"})
        self.assertIn("auth_engineer", select_agents(root))

    def test_intersects_with_available_agents(self):
        # When an agents/ tree exists, only existing agents are returned.
        root = _project({
            "main.py": "x",
            "pubspec.yaml": "name: app",
            "agents/flutter/agents/flutter.md": "# Flutter",
            "agents/flutter/persona.md": "# Flutter Persona",
            "agents/flutter/skills/scope.md": "# Scope",
            "agents/qa/agents/qa.md": "# QA",
            "agents/qa/persona.md": "# QA Persona",
            "agents/qa/skills/scope.md": "# Scope",
        })
        selected = select_agents(root)
        self.assertEqual(set(selected), {"flutter", "qa"})

    def test_present_incomplete_catalog_fails_closed(self):
        root = _project({
            "requirements.txt": "ccxt\n",
            "strategy.py": "x",
            "agents/quant_trader/agents/quant_trader.md": "# Quant Trader",
        })

        self.assertEqual(select_agents(root), [])

    def test_present_empty_catalog_fails_closed(self):
        root = _project({
            "requirements.txt": "ccxt\n",
            "strategy.py": "x",
        })
        os.makedirs(os.path.join(root, "agents"))

        self.assertEqual(select_agents(root), [])


if __name__ == "__main__":
    unittest.main()
