import os
import tempfile
import shutil
import unittest
from types import SimpleNamespace
from unittest import mock

from solomon_harness.bootstrap import scaffold_new_agent


class TestScaffoldAgent(unittest.TestCase):
    def setUp(self):
        self.real_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        self.tmp_dir = tempfile.mkdtemp()
        self.agents_dir = os.path.join(self.tmp_dir, "agents")
        os.makedirs(self.agents_dir, exist_ok=True)
        # Copy scripts directory so we can run them hermetically, plus the
        # solomon_harness package the scripts import (shared frontmatter
        # parser, ADR-0026).
        shutil.copytree(
            os.path.join(self.real_root, "scripts"),
            os.path.join(self.tmp_dir, "scripts")
        )
        shutil.copytree(
            os.path.join(self.real_root, "solomon_harness"),
            os.path.join(self.tmp_dir, "solomon_harness"),
            ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
        )
        # Create an AGENTS.md file mock
        with open(os.path.join(self.agents_dir, "AGENTS.md"), "w", encoding="utf-8") as f:
            f.write("# solomon-harness — Agent Rules and Definitions\n\n## The specialist agents\n\n")
        commands_dir = os.path.join(self.tmp_dir, ".claude", "commands")
        os.makedirs(commands_dir, exist_ok=True)
        with open(
            os.path.join(commands_dir, "solomon-workflow.md"),
            "w",
            encoding="utf-8",
        ) as f:
            f.write("# Workflow\n\nRun the delivery workflow.\n")

    def tearDown(self):
        shutil.rmtree(self.tmp_dir)

    def test_scaffold_name_validation(self):
        # Spaces, capital letters, special characters, path traversal
        invalid_names = ["TestAgent", "test agent", "test-agent", "../test", "test/agent", "test@agent"]
        for name in invalid_names:
            with self.assertRaises(ValueError):
                scaffold_new_agent(self.tmp_dir, name, "Description")

    def test_scaffold_creates_correct_files(self):
        scaffold_new_agent(self.tmp_dir, "test_scaffolded_agent", "Test specialist description")
        
        agent_dir = os.path.join(self.agents_dir, "test_scaffolded_agent")
        self.assertTrue(os.path.isdir(agent_dir))
        self.assertTrue(os.path.isdir(os.path.join(agent_dir, "agents")))
        self.assertTrue(os.path.isdir(os.path.join(agent_dir, "skills")))

        # Check persona.md
        persona_path = os.path.join(agent_dir, "persona.md")
        self.assertTrue(os.path.isfile(persona_path))
        with open(persona_path, "r", encoding="utf-8") as f:
            content = f.read()
        self.assertIn("Test Scaffolded Agent Persona", content)
        self.assertIn("Test specialist description", content)
        self.assertIn("agents/test_scaffolded_agent/agents/test_scaffolded_agent.md", content)
        self.assertIn("agents/AGENTS.md", content)

        # Check role file
        role_path = os.path.join(agent_dir, "agents", "test_scaffolded_agent.md")
        self.assertTrue(os.path.isfile(role_path))
        with open(role_path, "r", encoding="utf-8") as f:
            content = f.read()
        self.assertIn("Test Scaffolded Agent Profile", content)
        self.assertIn("Test specialist description", content)
        self.assertIn("`skill-sources.json`", content)

        # Check scope_and_mandate.md skill
        skill_path = os.path.join(agent_dir, "skills", "scope_and_mandate.md")
        self.assertTrue(os.path.isfile(skill_path))
        with open(skill_path, "r", encoding="utf-8") as f:
            content = f.read()
        self.assertIn("Test Scaffolded Agent Best Practices", content)

    def test_scaffolded_skill_meets_the_format_gate(self):
        # New agents are born on the mandated skill format: discovery
        # frontmatter plus both required closing sections.
        scaffold_new_agent(self.tmp_dir, "format_gate_agent", "Gate description")
        skill_path = os.path.join(
            self.agents_dir, "format_gate_agent", "skills", "scope_and_mandate.md"
        )
        with open(skill_path, "r", encoding="utf-8") as f:
            content = f.read()
        self.assertTrue(content.startswith("---\n"))
        self.assertIn("name: scope-and-mandate", content)
        self.assertIn("description:", content)
        self.assertIn("Use when", content)
        self.assertIn("## Common pitfalls", content)
        self.assertIn("## Definition of done", content)

    def test_scaffolded_profile_has_a_delegation_cue(self):
        scaffold_new_agent(self.tmp_dir, "cue_agent", "Cue description")
        role_path = os.path.join(
            self.agents_dir, "cue_agent", "agents", "cue_agent.md"
        )
        with open(role_path, "r", encoding="utf-8") as f:
            content = f.read()
        self.assertIn("## Delegation cue", content)
        self.assertIn("Use this agent when", content)
        # The cue names the actual mandate, not a circular "duties below".
        self.assertIn("this mandate: Cue description", content)

    def test_scaffold_copies_harness_templates(self):
        scaffold_new_agent(self.tmp_dir, "test_template_agent", "Another description")
        agent_dir = os.path.join(self.agents_dir, "test_template_agent")
        
        main_path = os.path.join(agent_dir, "main.py")
        config_path = os.path.join(agent_dir, ".agent", "config.json")

        self.assertTrue(os.path.isfile(main_path))
        self.assertTrue(os.path.isfile(config_path))

        with open(config_path, "r", encoding="utf-8") as f:
            import json
            config = json.load(f)
        self.assertEqual(config.get("agent_name"), "test_template_agent")

    def test_scaffold_registers_in_agents_md(self):
        # We start with:
        # ## The specialist agents
        # 
        # inside AGENTS.md mock.
        scaffold_new_agent(self.tmp_dir, "beta_agent", "Second agent")
        scaffold_new_agent(self.tmp_dir, "alpha_agent", "First agent")

        agents_md_path = os.path.join(self.agents_dir, "AGENTS.md")
        with open(agents_md_path, "r", encoding="utf-8") as f:
            content = f.read()

        # Check they are registered alphabetically under ## The specialist agents
        expected_part = "## The specialist agents\n\n- `alpha_agent` — first agent\n- `beta_agent` — second agent"
        self.assertIn(expected_part, content)

        # Check idempotence (running it again does not duplicate)
        scaffold_new_agent(self.tmp_dir, "alpha_agent", "First agent")
        with open(agents_md_path, "r", encoding="utf-8") as f:
            content = f.read()
        self.assertEqual(content.count("- `alpha_agent`"), 1)

    def test_scaffold_compiles_agent(self):
        # setUp already copied solomon_harness/ (templates included) into
        # self.tmp_dir, which the compile step needs.
        scaffold_new_agent(self.tmp_dir, "test_compiled_agent", "To compile test")

        # 1. Check skill is documented in the agent's profile file
        profile_path = os.path.join(self.tmp_dir, "agents", "test_compiled_agent", "agents", "test_compiled_agent.md")
        self.assertTrue(os.path.isfile(profile_path))
        with open(profile_path, "r", encoding="utf-8") as f:
            profile_content = f.read()
        
        # document-skills.py appends ## Active Skills
        self.assertIn("## Active Skills", profile_content)
        self.assertIn("scope_and_mandate", profile_content)

        # 2. Check compiled integration in .claude/agents/
        compiled_path = os.path.join(self.tmp_dir, ".claude", "agents", "test_compiled_agent.md")
        self.assertTrue(os.path.isfile(compiled_path))
        with open(compiled_path, "r", encoding="utf-8") as f:
            compiled_content = f.read()
        # The description is a quoted YAML scalar carrying the role line plus
        # a thin pointer back to the neutral catalog.
        self.assertIn('description: "To compile test', compiled_content)
        self.assertIn(
            "agents/test_compiled_agent/agents/test_compiled_agent.md",
            compiled_content,
        )
        self.assertTrue(
            os.path.isfile(
                os.path.join(
                    self.tmp_dir,
                    ".agents",
                    "agents",
                    "test_compiled_agent",
                    "agent.md",
                )
            )
        )
        self.assertTrue(
            os.path.isfile(
                os.path.join(
                    self.tmp_dir,
                    ".codex",
                    "agents",
                    "test_compiled_agent.toml",
                )
            )
        )

    def test_scaffold_cli_command(self):
        from unittest.mock import patch
        from solomon_harness import cli

        with patch("solomon_harness.cli.scaffold_new_agent") as mock_scaffold:
            cli.main(harness_dir=self.tmp_dir, argv=["agents", "scaffold", "cli_agent", "--description", "CLI desc"])
            mock_scaffold.assert_called_once_with(
                os.path.abspath(self.tmp_dir), "cli_agent", "CLI desc"
            )

    def test_scaffold_writes_a_consumer_catalog_and_recompiles_from_outer_root(self):
        consumer = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, consumer, True)
        rules = os.path.join(consumer, ".agents", "solomon", "AGENTS.md")
        os.makedirs(os.path.dirname(rules), exist_ok=True)
        with open(rules, "w", encoding="utf-8") as f:
            f.write("# Rules\n\n## The specialist agents\n\n")
        with open(
            os.path.join(consumer, ".agents", "solomon", "manifest.json"),
            "w",
            encoding="utf-8",
        ) as f:
            f.write("{}\n")

        result = SimpleNamespace(changed=True, conflicts=(), managed_paths=())
        with (
            mock.patch(
                "solomon_harness.install_layout.install_project",
                return_value=result,
            ) as install,
            mock.patch(
                "solomon_harness.host_adapters.compile_adapters",
                return_value=result,
            ) as compile_,
        ):
            scaffold_new_agent(
                consumer,
                "consumer_agent",
                "Consumer specialist description",
            )

        role = os.path.join(
            consumer,
            ".agents",
            "solomon",
            "agents",
            "consumer_agent",
            "agents",
            "consumer_agent.md",
        )
        self.assertTrue(os.path.isfile(role))
        self.assertFalse(os.path.exists(os.path.join(consumer, "agents")))
        persona = os.path.join(
            consumer,
            ".agents",
            "solomon",
            "agents",
            "consumer_agent",
            "persona.md",
        )
        with open(persona, encoding="utf-8") as f:
            persona_content = f.read()
        with open(role, encoding="utf-8") as f:
            role_content = f.read()
        self.assertIn("`.agents/solomon/AGENTS.md`", persona_content)
        self.assertIn(
            "`.agents/solomon/agents/consumer_agent/agents/consumer_agent.md`",
            persona_content,
        )
        self.assertIn(
            "`.agents/solomon/agents/consumer_agent/skills/`",
            persona_content,
        )
        self.assertIn("`.agents/solomon/skill-sources.json`", role_content)
        install.assert_called_once_with(consumer)
        compile_.assert_not_called()

    def test_scaffold_rejects_a_symlinked_canonical_agent_catalog(self):
        consumer = tempfile.mkdtemp()
        outside = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, consumer, True)
        self.addCleanup(shutil.rmtree, outside, True)
        core = os.path.join(consumer, ".agents", "solomon")
        os.makedirs(core)
        os.symlink(outside, os.path.join(core, "agents"))

        with self.assertRaisesRegex(ValueError, "symlink"):
            scaffold_new_agent(consumer, "escaped_agent", "Must stay inside")

        self.assertFalse(os.path.exists(os.path.join(outside, "escaped_agent")))


if __name__ == "__main__":
    unittest.main()
