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

    def test_agy_md_imports_central_source(self):
        self.assertIn("@agents/AGENTS.md", _read("AGY.md"))


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

    def _load_generator(self):
        path = os.path.join(WORKSPACE, "scripts", "generate-integrations.py")
        spec = importlib.util.spec_from_file_location("gen_integrations", path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def test_role_description_appends_delegation_cue(self):
        # A profile with a Delegation cue section yields a description that
        # carries both the role one-liner and the when-to-delegate trigger.
        import tempfile

        gen = self._load_generator()
        with tempfile.TemporaryDirectory() as tmp:
            role = os.path.join(tmp, "role.md")
            with open(role, "w", encoding="utf-8") as f:
                f.write(
                    "# Widget Maker Profile\n\n"
                    "The Widget Maker builds widgets.\n\n"
                    "## Delegation cue\n\n"
                    "Use this agent when a task involves designing or repairing widgets.\n\n"
                    "## Core Duties\n\n- Build widgets.\n"
                )
            description = gen.role_description(role, "widget_maker")
        self.assertEqual(
            description,
            "The Widget Maker builds widgets. "
            "Use this agent when a task involves designing or repairing widgets.",
        )

    def test_role_description_without_cue_keeps_one_liner(self):
        import tempfile

        gen = self._load_generator()
        with tempfile.TemporaryDirectory() as tmp:
            role = os.path.join(tmp, "role.md")
            with open(role, "w", encoding="utf-8") as f:
                f.write("# Widget Maker Profile\n\nThe Widget Maker builds widgets.\n")
            description = gen.role_description(role, "widget_maker")
        self.assertEqual(description, "The Widget Maker builds widgets.")

    def test_every_generated_subagent_carries_a_delegation_trigger(self):
        # Every profile has a Delegation cue, so every generated subagent
        # description must contain the "Use this agent when" trigger phrase.
        for name in _agent_names():
            body = _read(os.path.join(".claude", "agents", f"{name}.md"))
            self.assertIn(
                "Use this agent when",
                body.split("---")[1],
                f"subagent {name} lacks a delegation trigger in its description",
            )


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
            patch("solomon_harness.bootstrap.scaffold_agents") as mock_scaffold,
            patch.object(cli, "_generate_integrations") as mock_gen,
        ):
            cli.main(harness_dir=WORKSPACE, argv=["compile"])
        mock_scaffold.assert_called_once()
        mock_gen.assert_called_once()


class TestStartWorktree(unittest.TestCase):
    def test_start_command_creates_worktree_instead_of_switching(self):
        body = _read(os.path.join(".claude", "commands", "solomon-start.md"))
        self.assertIn("solomon_harness.cli worktree", body)
        self.assertNotIn("git switch -c", body)

    def test_workflow_doc_documents_worktree_location(self):
        doc = _read(os.path.join("docs", "solomon-workflow.md"))
        self.assertIn("-worktrees", doc)

    def test_gemini_start_mirror_includes_worktree_call(self):
        toml = _read(os.path.join(".gemini", "commands", "solomon-start.toml"))
        self.assertIn("solomon_harness.cli worktree", toml)


class TestGeminiDrift(unittest.TestCase):
    def _generator(self):
        path = os.path.join(WORKSPACE, "scripts", "generate-integrations.py")
        spec = importlib.util.spec_from_file_location("gen_integrations_drift", path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def test_gemini_commands_match_regenerated_source(self):
        # A true fitness function: every .gemini/commands/*.toml must equal what the
        # generator produces from its .claude/commands/*.md source. A hand-edit to a
        # command without recompiling fails here.
        gen = self._generator()
        cmd_dir = os.path.join(WORKSPACE, ".claude", "commands")
        for name in sorted(os.listdir(cmd_dir)):
            if not name.endswith(".md"):
                continue
            description, body = gen._parse_command_file(os.path.join(cmd_dir, name))
            expected = gen.gemini_command_toml(description, body)
            actual = _read(os.path.join(".gemini", "commands", name[:-3] + ".toml"))
            self.assertEqual(
                actual, expected, f"{name[:-3]}.toml is out of sync; run the generator"
            )


class TestStartAdr(unittest.TestCase):
    def test_adr_0001_records_the_start_stage_decision(self):
        adr = _read(
            os.path.join(
                "docs", "adr", "0001-isolated-worktree-and-implementation-mode-on-start.md"
            )
        )
        low = adr.lower()
        self.assertIn("worktree", low)
        self.assertIn("manual", low)
        self.assertIn("#8", adr)
        self.assertIn("#23", adr)


class TestStartImplementationMode(unittest.TestCase):
    def test_start_command_asks_mode_before_coding(self):
        body = _read(os.path.join(".claude", "commands", "solomon-start.md"))
        low = body.lower()
        self.assertIn("implementation mode", low)
        self.assertIn("automatic", low)
        self.assertIn("manual", low)
        # The third enumerated option is required by the enumerable-options rule.
        self.assertIn("Other", body)
        # The choice must precede any code, and print the selected mode.
        self.assertIn("Before writing any production or test code", body)
        self.assertIn("(selected)", body)
        # The headless default line is asserted verbatim so QA can grep for it.
        self.assertIn("Implementation mode: Automatic (non-interactive default)", body)
        # Manual mode must leave the card in progress; assert the manual-specific
        # phrase, not the bare "In Progress" that also appears in step 2.
        self.assertIn("do not advance it to Code Review", body)

    def test_gemini_start_mirror_carries_mode_and_default(self):
        toml = _read(os.path.join(".gemini", "commands", "solomon-start.toml"))
        self.assertIn("Implementation mode: Automatic (non-interactive default)", toml)
        self.assertIn("Manual", toml)

    def test_workflow_doc_documents_both_modes(self):
        doc = _read(os.path.join("docs", "solomon-workflow.md")).lower()
        self.assertIn("automatic", doc)
        self.assertIn("manual", doc)


if __name__ == "__main__":
    unittest.main()
