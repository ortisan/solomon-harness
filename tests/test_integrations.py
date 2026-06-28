import importlib.util
import json
import os
import sys
import unittest

WORKSPACE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if WORKSPACE not in sys.path:
    sys.path.insert(0, WORKSPACE)


def _read(rel_path):
    with open(os.path.join(WORKSPACE, rel_path), "r", encoding="utf-8") as f:
        return f.read()


def _agent_names():
    agents_dir = os.path.join(WORKSPACE, "agents")
    names = []
    for item in sorted(os.listdir(agents_dir)):
        if os.path.isfile(os.path.join(agents_dir, item, "agents", f"{item}.md")):
            names.append(item)
    return names


class TestCentralSource(unittest.TestCase):
    def test_holds_relocated_governance(self):
        central = _read(os.path.join("agents", "AGENTS.md"))
        self.assertIn("Test-Driven Development", central)
        self.assertIn("emojis", central.lower())
        self.assertIn("strictly prohibited", central.lower())
        self.assertIn("Development workflow lifecycle", central)

    def test_documents_memory_and_indexes_agents(self):
        central = _read(os.path.join("agents", "AGENTS.md"))
        self.assertIn("database_client.py", central)
        for name in _agent_names():
            self.assertIn(name, central, f"{name} is missing from the agent index")


class TestThinPointers(unittest.TestCase):
    def test_claude_md_imports_central_source(self):
        self.assertIn("@agents/AGENTS.md", _read("CLAUDE.md"))

    def test_root_agents_md_points_to_central(self):
        self.assertIn("agents/AGENTS.md", _read("AGENTS.md"))

    def test_copilot_instructions_point_to_central(self):
        self.assertIn(
            "agents/AGENTS.md",
            _read(os.path.join(".github", "copilot-instructions.md")),
        )

    def test_gemini_md_imports_central_source(self):
        self.assertIn("@agents/AGENTS.md", _read("GEMINI.md"))


class TestMcpRegistration(unittest.TestCase):
    def _registers_memory_server(self, rel_path):
        config = json.loads(_read(rel_path))
        servers = config.get("mcpServers", {})
        self.assertIn("solomon-memory", servers)
        args = servers["solomon-memory"].get("args", [])
        self.assertIn("solomon_harness.mcp_server", args)

    def test_claude_mcp_json_registers_server(self):
        self._registers_memory_server(".mcp.json")

    def test_gemini_settings_register_server(self):
        self._registers_memory_server(os.path.join(".gemini", "settings.json"))

    def test_mcp_server_module_imports_without_sdk(self):
        # build_server imports the mcp SDK lazily, so the module must import
        # cleanly even when mcp is not installed.
        import solomon_harness.mcp_server as server_module

        self.assertTrue(hasattr(server_module, "build_server"))


class TestGeneratedSubagents(unittest.TestCase):
    def test_every_agent_has_a_thin_subagent(self):
        for name in _agent_names():
            rel = os.path.join(".claude", "agents", f"{name}.md")
            self.assertTrue(
                os.path.isfile(os.path.join(WORKSPACE, rel)),
                f"missing Claude Code subagent for {name}",
            )
            body = _read(rel)
            self.assertIn(f"name: {name}", body)
            self.assertIn(f"agents/{name}/", body)
            self.assertIn("agents/AGENTS.md", body)

    def test_generator_discovers_all_agents(self):
        path = os.path.join(WORKSPACE, "scripts", "generate-integrations.py")
        spec = importlib.util.spec_from_file_location("gen_integrations", path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        discovered = module.discover_agents(os.path.join(WORKSPACE, "agents"))
        self.assertEqual(sorted(discovered), sorted(_agent_names()))


class TestGeminiCommands(unittest.TestCase):
    def test_every_slash_command_has_a_gemini_mirror(self):
        cmd_dir = os.path.join(WORKSPACE, ".claude", "commands")
        for name in sorted(os.listdir(cmd_dir)):
            if not name.endswith(".md"):
                continue
            toml_rel = os.path.join(".gemini", "commands", name[:-3] + ".toml")
            self.assertTrue(
                os.path.isfile(os.path.join(WORKSPACE, toml_rel)),
                f"missing Gemini mirror for {name}",
            )
            body = _read(toml_rel)
            self.assertIn("description =", body)
            self.assertIn("prompt =", body)
            # Claude-isms must be translated, not leaked.
            self.assertNotIn("$ARGUMENTS", body)
            self.assertNotIn("mcp__solomon-memory__", body)


class TestCompileSyncsIntegrations(unittest.TestCase):
    def test_compile_command_regenerates_integrations(self):
        from unittest.mock import patch

        from solomon_harness import cli

        with (
            patch("solomon_harness.compiler.compile_harnesses") as mock_compile,
            patch.object(cli, "_generate_integrations") as mock_gen,
        ):
            cli.main(harness_dir=WORKSPACE, argv=["compile"])
        mock_compile.assert_called_once()
        mock_gen.assert_called_once()


if __name__ == "__main__":
    unittest.main()
