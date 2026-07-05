import os
import tempfile
import unittest

from solomon_harness.agent_selection import CORE_AGENTS, select_agents


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

    def test_auth_signal(self):
        root = _project({"requirements.txt": "authlib\n", "auth.py": "x"})
        self.assertIn("auth_engineer", select_agents(root))

    def test_intersects_with_available_agents(self):
        # When an agents/ tree exists, only existing agents are returned.
        root = _project({
            "main.py": "x",
            "pubspec.yaml": "name: app",
            "agents/flutter/agents/flutter.md": "# Flutter",
            "agents/qa/agents/qa.md": "# QA",
        })
        selected = select_agents(root)
        self.assertEqual(set(selected), {"flutter", "qa"})


if __name__ == "__main__":
    unittest.main()
