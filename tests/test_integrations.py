import importlib.util
import os
import unittest

WORKSPACE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


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


if __name__ == "__main__":
    unittest.main()
