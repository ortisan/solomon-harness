import importlib.util
import json
import os
import sys
import unittest

WORKSPACE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if WORKSPACE not in sys.path:
    sys.path.insert(0, WORKSPACE)


def _read(rel_path):
    parts = rel_path.split(os.sep)
    if parts[:2] == [".claude", "commands"] and parts[-1].startswith("solomon-"):
        rel_path = os.path.join(
            "solomon_harness", "catalog", "workflows", parts[-1]
        )
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

    def test_instruction_docs_reference_specs_and_adrs(self):
        files = [
            "CLAUDE.md",
            "agents/AGENTS.md",
            "AGY.md",
            os.path.join(".github", "copilot-instructions.md"),
        ]
        for f in files:
            content = _read(f)
            self.assertIn("docs/specs/", content, f"{f} is missing a reference to docs/specs/")
            self.assertIn("docs/adrs/", content, f"{f} is missing a reference to docs/adrs/")



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
        # Every generated subagent frontmatter must parse as strict YAML (the
        # description is a quoted scalar, so colons in prose cannot break it)
        # and its description must carry the "Use this agent when" trigger.
        import yaml

        for name in _agent_names():
            body = _read(os.path.join(".claude", "agents", f"{name}.md"))
            parts = body.split("---\n")
            self.assertGreaterEqual(
                len(parts), 3, f"subagent {name} has no frontmatter block"
            )
            data = yaml.safe_load(parts[1])
            self.assertIsInstance(
                data, dict, f"subagent {name} frontmatter is not a YAML mapping"
            )
            self.assertEqual(data.get("name"), name)
            self.assertIn(
                "Use this agent when",
                data.get("description", ""),
                f"subagent {name} lacks a delegation trigger in its description",
            )

    def test_every_subagent_is_pinned_to_sonnet(self):
        # Task-tool subagents must never silently inherit whatever model the
        # orchestrating session happens to run under (e.g. Opus) -- each
        # specialist subagent is pinned to Sonnet in its own frontmatter, per
        # the Agent tool's documented `model:` field.
        for name in _agent_names():
            body = _read(os.path.join(".claude", "agents", f"{name}.md"))
            self.assertIn("model: sonnet", body, f"{name} subagent is not pinned to sonnet")

    def test_subagent_markdown_emits_the_model_field(self):
        path = os.path.join(WORKSPACE, "scripts", "generate-integrations.py")
        spec = importlib.util.spec_from_file_location("gen_integrations_model", path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        body = module.subagent_markdown("software_engineer", "desc")
        self.assertIn("model: sonnet", body)
        front, _, _rest = body.partition("\n\n")
        self.assertIn("model:", front)


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
    def _write_external_agent(self, tmp, name="qa", role_body=None):
        agent_dir = os.path.join(tmp, "agents", name)
        role_dir = os.path.join(agent_dir, "agents")
        os.makedirs(role_dir)
        skills_dir = os.path.join(agent_dir, "skills")
        os.makedirs(skills_dir)
        with open(os.path.join(skills_dir, "scope.md"), "w", encoding="utf-8") as f:
            f.write(f"# {name} Scope\n")
        with open(os.path.join(agent_dir, "persona.md"), "w", encoding="utf-8") as f:
            f.write(f"# {name} Persona\n")
        with open(os.path.join(role_dir, f"{name}.md"), "w", encoding="utf-8") as f:
            f.write(role_body or f"# {name} Profile\n\nThe {name} specialist validates changes.\n")

    def test_compile_command_regenerates_integrations(self):
        from unittest.mock import patch

        from solomon_harness import cli

        with patch.object(cli, "_generate_integrations", return_value=0) as mock_gen:
            with self.assertRaises(SystemExit) as raised:
                cli.main(harness_dir=WORKSPACE, argv=["compile"])
        self.assertEqual(raised.exception.code, 0)
        mock_gen.assert_called_once()

    def test_compile_keeps_behavioral_evaluations_default_off(self):
        import shutil
        import tempfile
        from pathlib import Path
        from unittest.mock import patch

        from solomon_harness import behavioral_evals, cli

        blocked = AssertionError("compile must not enter behavioral evaluation")
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._write_external_agent(tmp, "qa")
            root.joinpath("AGENTS.md").write_text(
                "# Project instructions\n",
                encoding="utf-8",
            )
            scripts = root / "scripts"
            scripts.mkdir()
            shutil.copy2(
                Path(WORKSPACE) / "scripts" / "generate-integrations.py",
                scripts / "generate-integrations.py",
            )
            before = {
                path.relative_to(root)
                for path in root.rglob("*")
            }

            with (
                patch.object(
                    behavioral_evals,
                    "load_manifest",
                    side_effect=blocked,
                ) as load_manifest,
                patch.object(
                    behavioral_evals,
                    "prepare_pilot",
                    side_effect=blocked,
                ) as prepare_pilot,
                patch.object(
                    behavioral_evals,
                    "load_recordings",
                    side_effect=blocked,
                ) as load_recordings,
                patch.object(
                    behavioral_evals,
                    "score_recordings",
                    side_effect=blocked,
                ) as score_recordings,
                patch.object(
                    behavioral_evals,
                    "validate_complete_comparison",
                    side_effect=blocked,
                ) as validate_comparison,
                patch.object(
                    behavioral_evals,
                    "compare_recordings",
                    side_effect=blocked,
                ) as compare_recordings,
                patch.object(
                    behavioral_evals,
                    "main",
                    side_effect=blocked,
                ) as behavioral_main,
                patch(
                    "urllib.request.urlopen",
                    side_effect=AssertionError("compile must not open a network connection"),
                ) as urlopen,
                patch(
                    "socket.create_connection",
                    side_effect=AssertionError("compile must not open a network connection"),
                ) as create_connection,
                patch.object(sys, "dont_write_bytecode", True),
            ):
                cli.main(harness_dir=tmp, argv=["compile"])

            created = {
                path.relative_to(root)
                for path in root.rglob("*")
            } - before
            self.assertEqual(
                created,
                {
                    Path(".claude"),
                    Path(".claude/agents"),
                    Path(".claude/agents/qa.md"),
                },
            )
            self.assertEqual(list(root.rglob("behavioral-eval-*")), [])
            load_manifest.assert_not_called()
            prepare_pilot.assert_not_called()
            load_recordings.assert_not_called()
            score_recordings.assert_not_called()
            validate_comparison.assert_not_called()
            compare_recordings.assert_not_called()
            behavioral_main.assert_not_called()
            urlopen.assert_not_called()
            create_connection.assert_not_called()

    def test_packaged_generator_filters_and_reconciles_allowed_agents(self):
        import tempfile

        from solomon_harness.integrations import generate_claude_agents

        with tempfile.TemporaryDirectory() as tmp:
            self._write_external_agent(tmp, "quant_trader")
            self._write_external_agent(tmp, "execution_engineer")
            with open(os.path.join(tmp, "AGENTS.md"), "w", encoding="utf-8") as f:
                f.write("# Project instructions\n")

            self.assertEqual(generate_claude_agents(tmp), 2)
            output = os.path.join(tmp, ".claude", "agents")
            human = os.path.join(output, "custom.md")
            with open(human, "w", encoding="utf-8") as f:
                f.write("# Human-managed wrapper\n")

            self.assertEqual(
                generate_claude_agents(tmp, allowed_names=["quant_trader"]),
                1,
            )
            self.assertTrue(os.path.isfile(os.path.join(output, "quant_trader.md")))
            self.assertFalse(os.path.lexists(os.path.join(output, "execution_engineer.md")))
            self.assertTrue(os.path.isfile(human))

    def test_packaged_generator_prefers_agents_trust_file_when_present(self):
        import tempfile

        from solomon_harness.integrations import generate_claude_agents

        with tempfile.TemporaryDirectory() as tmp:
            agent_dir = os.path.join(tmp, "agents", "qa")
            role_dir = os.path.join(agent_dir, "agents")
            os.makedirs(role_dir)
            skills_dir = os.path.join(agent_dir, "skills")
            os.makedirs(skills_dir)
            with open(os.path.join(skills_dir, "scope.md"), "w", encoding="utf-8") as f:
                f.write("# QA Scope\n")
            with open(os.path.join(tmp, "AGENTS.md"), "w", encoding="utf-8") as f:
                f.write("# Root pointer\n")
            with open(
                os.path.join(tmp, "agents", "AGENTS.md"), "w", encoding="utf-8"
            ) as f:
                f.write("# Shared rules\n")
            with open(os.path.join(agent_dir, "persona.md"), "w", encoding="utf-8") as f:
                f.write("# QA Persona\n")
            with open(os.path.join(role_dir, "qa.md"), "w", encoding="utf-8") as f:
                f.write("# QA Profile\n\nThe QA specialist validates changes.\n")

            generate_claude_agents(tmp)

            with open(
                os.path.join(tmp, ".claude", "agents", "qa.md"),
                "r",
                encoding="utf-8",
            ) as f:
                body = f.read()
            self.assertIn("The shared project rules are in `agents/AGENTS.md`.", body)

    def test_packaged_generator_refuses_to_emit_a_broken_trust_reference(self):
        import tempfile

        from solomon_harness.integrations import generate_claude_agents

        with tempfile.TemporaryDirectory() as tmp:
            agent_dir = os.path.join(tmp, "agents", "qa")
            role_dir = os.path.join(agent_dir, "agents")
            os.makedirs(role_dir)
            skills_dir = os.path.join(agent_dir, "skills")
            os.makedirs(skills_dir)
            with open(os.path.join(skills_dir, "scope.md"), "w", encoding="utf-8") as f:
                f.write("# QA Scope\n")
            with open(os.path.join(agent_dir, "persona.md"), "w", encoding="utf-8") as f:
                f.write("# QA Persona\n")
            with open(os.path.join(role_dir, "qa.md"), "w", encoding="utf-8") as f:
                f.write("# QA Profile\n\nThe QA specialist validates changes.\n")

            with self.assertRaisesRegex(FileNotFoundError, "project instructions"):
                generate_claude_agents(tmp)

            self.assertFalse(os.path.exists(os.path.join(tmp, ".claude", "agents")))

    def _assert_existing_wrapper_revoked_with_trust_root(self, *, symlink):
        import tempfile

        from solomon_harness.integrations import generate_claude_agents

        with tempfile.TemporaryDirectory() as tmp:
            self._write_external_agent(tmp)
            trust_root = os.path.join(tmp, "AGENTS.md")
            with open(trust_root, "w", encoding="utf-8") as f:
                f.write("# Project instructions\n")

            self.assertEqual(generate_claude_agents(tmp), 1)
            generated = os.path.join(tmp, ".claude", "agents", "qa.md")
            custom = os.path.join(tmp, ".claude", "agents", "custom.md")
            with open(custom, "w", encoding="utf-8") as f:
                f.write("# Human-managed agent\n")

            os.unlink(trust_root)
            if symlink:
                outside = os.path.join(tmp, "outside-rules.md")
                with open(outside, "w", encoding="utf-8") as f:
                    f.write("# Untrusted rules\n")
                os.symlink(outside, trust_root)

            with self.assertRaisesRegex(FileNotFoundError, "project instructions"):
                generate_claude_agents(tmp)

            self.assertFalse(os.path.lexists(generated))
            self.assertTrue(os.path.isfile(custom))

    def test_packaged_generator_revokes_existing_wrapper_when_trust_root_is_removed(self):
        self._assert_existing_wrapper_revoked_with_trust_root(symlink=False)

    @unittest.skipUnless(hasattr(os, "symlink"), "symlinks are unavailable")
    def test_packaged_generator_revokes_existing_wrapper_when_trust_root_is_symlinked(self):
        self._assert_existing_wrapper_revoked_with_trust_root(symlink=True)

    def test_packaged_generator_rejects_oversized_role_content(self):
        import tempfile

        from solomon_harness.integrations import MAX_ROLE_BYTES, generate_claude_agents

        with tempfile.TemporaryDirectory() as tmp:
            agent_dir = os.path.join(tmp, "agents", "qa")
            role_dir = os.path.join(agent_dir, "agents")
            os.makedirs(role_dir)
            skills_dir = os.path.join(agent_dir, "skills")
            os.makedirs(skills_dir)
            with open(os.path.join(skills_dir, "scope.md"), "w", encoding="utf-8") as f:
                f.write("# QA Scope\n")
            with open(os.path.join(tmp, "AGENTS.md"), "w", encoding="utf-8") as f:
                f.write("# Project instructions\n")
            with open(os.path.join(agent_dir, "persona.md"), "w", encoding="utf-8") as f:
                f.write("# QA Persona\n")
            with open(os.path.join(role_dir, "qa.md"), "w", encoding="utf-8") as f:
                f.write("x" * (MAX_ROLE_BYTES + 1))

            self.assertEqual(generate_claude_agents(tmp), 0)
            self.assertFalse(os.path.exists(os.path.join(tmp, ".claude", "agents")))

    def test_packaged_generator_rejects_oversized_persona_content(self):
        import tempfile

        from solomon_harness.integrations import MAX_PERSONA_BYTES, generate_claude_agents

        with tempfile.TemporaryDirectory() as tmp:
            self._write_external_agent(tmp)
            persona = os.path.join(tmp, "agents", "qa", "persona.md")
            with open(persona, "w", encoding="utf-8") as f:
                f.write("x" * (MAX_PERSONA_BYTES + 1))
            with open(os.path.join(tmp, "AGENTS.md"), "w", encoding="utf-8") as f:
                f.write("# Project instructions\n")

            self.assertEqual(generate_claude_agents(tmp), 0)
            self.assertFalse(os.path.exists(os.path.join(tmp, ".claude", "agents")))

    @unittest.skipUnless(hasattr(os, "symlink"), "symlinks are unavailable")
    def test_packaged_generator_rejects_role_symlink_outside_agents(self):
        import tempfile

        from solomon_harness.integrations import generate_claude_agents

        with tempfile.TemporaryDirectory() as tmp:
            agent_dir = os.path.join(tmp, "agents", "qa")
            role_dir = os.path.join(agent_dir, "agents")
            os.makedirs(role_dir)
            skills_dir = os.path.join(agent_dir, "skills")
            os.makedirs(skills_dir)
            with open(os.path.join(skills_dir, "scope.md"), "w", encoding="utf-8") as f:
                f.write("# QA Scope\n")
            with open(os.path.join(tmp, "AGENTS.md"), "w", encoding="utf-8") as f:
                f.write("# Project instructions\n")
            with open(os.path.join(agent_dir, "persona.md"), "w", encoding="utf-8") as f:
                f.write("# QA Persona\n")
            outside = os.path.join(tmp, "outside-role.md")
            with open(outside, "w", encoding="utf-8") as f:
                f.write("# QA Profile\n\nInjected instructions.\n")
            os.symlink(outside, os.path.join(role_dir, "qa.md"))

            self.assertEqual(generate_claude_agents(tmp), 0)
            self.assertFalse(os.path.exists(os.path.join(tmp, ".claude", "agents")))

    def test_packaged_generator_rejects_empty_skills_directory(self):
        import tempfile

        from solomon_harness.integrations import generate_claude_agents

        with tempfile.TemporaryDirectory() as tmp:
            self._write_external_agent(tmp)
            os.unlink(os.path.join(tmp, "agents", "qa", "skills", "scope.md"))
            with open(os.path.join(tmp, "AGENTS.md"), "w", encoding="utf-8") as f:
                f.write("# Project instructions\n")

            self.assertEqual(generate_claude_agents(tmp), 0)
            self.assertFalse(os.path.exists(os.path.join(tmp, ".claude", "agents")))

    @unittest.skipUnless(hasattr(os, "symlink"), "symlinks are unavailable")
    def test_packaged_generator_rejects_symlinked_skill(self):
        import tempfile

        from solomon_harness.integrations import generate_claude_agents

        with tempfile.TemporaryDirectory() as tmp:
            self._write_external_agent(tmp)
            skill = os.path.join(tmp, "agents", "qa", "skills", "scope.md")
            outside = os.path.join(tmp, "outside-skill.md")
            with open(outside, "w", encoding="utf-8") as f:
                f.write("# Untrusted skill\n")
            os.unlink(skill)
            os.symlink(outside, skill)
            with open(os.path.join(tmp, "AGENTS.md"), "w", encoding="utf-8") as f:
                f.write("# Project instructions\n")

            self.assertEqual(generate_claude_agents(tmp), 0)
            self.assertFalse(os.path.exists(os.path.join(tmp, ".claude", "agents")))

    def test_packaged_generator_rejects_package_without_manifest(self):
        import tempfile

        from solomon_harness.integrations import generate_claude_agents

        with tempfile.TemporaryDirectory() as tmp:
            self._write_external_agent(tmp)
            nested = os.path.join(tmp, "agents", "qa", "skills", "nested")
            os.makedirs(nested)
            with open(os.path.join(nested, "escape.md"), "w", encoding="utf-8") as f:
                f.write("# Nested skill\n")
            with open(os.path.join(tmp, "AGENTS.md"), "w", encoding="utf-8") as f:
                f.write("# Project instructions\n")

            self.assertEqual(generate_claude_agents(tmp), 0)
            self.assertFalse(os.path.exists(os.path.join(tmp, ".claude", "agents")))

    def test_packaged_generator_accepts_bounded_inert_package(self):
        import tempfile

        from solomon_harness.integrations import generate_claude_agents

        with tempfile.TemporaryDirectory() as tmp:
            self._write_external_agent(tmp)
            package = os.path.join(tmp, "agents", "qa", "skills", "goodpkg")
            os.makedirs(os.path.join(package, "docs"))
            with open(os.path.join(package, "SKILL.md"), "w", encoding="utf-8") as f:
                f.write("# Good Package\n")
            with open(os.path.join(package, "reference.json"), "w", encoding="utf-8") as f:
                f.write("{}")
            with open(os.path.join(package, "docs", "notes.md"), "w", encoding="utf-8") as f:
                f.write("# Notes\n")
            with open(os.path.join(tmp, "AGENTS.md"), "w", encoding="utf-8") as f:
                f.write("# Project instructions\n")

            self.assertEqual(generate_claude_agents(tmp), 1)
            self.assertTrue(os.path.isfile(os.path.join(tmp, ".claude", "agents", "qa.md")))

    @unittest.skipUnless(hasattr(os, "symlink"), "symlinks are unavailable")
    def test_packaged_generator_rejects_nested_skill_symlink(self):
        import tempfile

        from solomon_harness.integrations import generate_claude_agents

        with tempfile.TemporaryDirectory() as tmp:
            self._write_external_agent(tmp)
            package = os.path.join(tmp, "agents", "qa", "skills", "goodpkg")
            docs = os.path.join(package, "docs")
            os.makedirs(docs)
            with open(os.path.join(package, "SKILL.md"), "w", encoding="utf-8") as f:
                f.write("# Good Package\n")
            outside = os.path.join(tmp, "outside-skill.md")
            with open(outside, "w", encoding="utf-8") as f:
                f.write("# Untrusted skill\n")
            os.symlink(outside, os.path.join(docs, "leak.md"))
            with open(os.path.join(tmp, "AGENTS.md"), "w", encoding="utf-8") as f:
                f.write("# Project instructions\n")

            self.assertEqual(generate_claude_agents(tmp), 0)
            self.assertFalse(os.path.exists(os.path.join(tmp, ".claude", "agents")))

    def test_packaged_generator_enforces_skills_depth_limit(self):
        import tempfile
        from unittest.mock import patch

        from solomon_harness import integrations

        with tempfile.TemporaryDirectory() as tmp:
            self._write_external_agent(tmp)
            package = os.path.join(tmp, "agents", "qa", "skills", "goodpkg")
            os.makedirs(os.path.join(package, "docs"))
            with open(os.path.join(package, "SKILL.md"), "w", encoding="utf-8") as f:
                f.write("# Good Package\n")
            with open(os.path.join(package, "docs", "notes.md"), "w", encoding="utf-8") as f:
                f.write("# Notes\n")
            with open(os.path.join(tmp, "AGENTS.md"), "w", encoding="utf-8") as f:
                f.write("# Project instructions\n")

            with patch.object(integrations, "MAX_SKILL_DEPTH", 1):
                self.assertEqual(integrations.generate_claude_agents(tmp), 0)
            self.assertFalse(os.path.exists(os.path.join(tmp, ".claude", "agents")))

    def test_packaged_generator_rejects_unexpected_skills_file(self):
        import tempfile

        from solomon_harness.integrations import generate_claude_agents

        with tempfile.TemporaryDirectory() as tmp:
            self._write_external_agent(tmp)
            unexpected = os.path.join(tmp, "agents", "qa", "skills", "config.json")
            with open(unexpected, "w", encoding="utf-8") as f:
                f.write("{}")
            with open(os.path.join(tmp, "AGENTS.md"), "w", encoding="utf-8") as f:
                f.write("# Project instructions\n")

            self.assertEqual(generate_claude_agents(tmp), 0)
            self.assertFalse(os.path.exists(os.path.join(tmp, ".claude", "agents")))

    def test_packaged_generator_enforces_skills_tree_limits(self):
        import tempfile
        from unittest.mock import patch

        from solomon_harness import integrations

        for limit_name in (
            "MAX_SKILL_FILES",
            "MAX_SKILL_BYTES",
            "MAX_SKILLS_TOTAL_BYTES",
        ):
            with self.subTest(limit=limit_name), tempfile.TemporaryDirectory() as tmp:
                self._write_external_agent(tmp)
                with open(os.path.join(tmp, "AGENTS.md"), "w", encoding="utf-8") as f:
                    f.write("# Project instructions\n")
                with patch.object(integrations, limit_name, 0):
                    self.assertEqual(integrations.generate_claude_agents(tmp), 0)
                self.assertFalse(os.path.exists(os.path.join(tmp, ".claude", "agents")))

    @unittest.skipUnless(hasattr(os, "symlink"), "symlinks are unavailable")
    def test_packaged_generator_revokes_wrapper_after_skill_becomes_symlink(self):
        import tempfile

        from solomon_harness.integrations import generate_claude_agents

        with tempfile.TemporaryDirectory() as tmp:
            self._write_external_agent(tmp)
            with open(os.path.join(tmp, "AGENTS.md"), "w", encoding="utf-8") as f:
                f.write("# Project instructions\n")
            self.assertEqual(generate_claude_agents(tmp), 1)

            generated = os.path.join(tmp, ".claude", "agents", "qa.md")
            custom = os.path.join(tmp, ".claude", "agents", "custom.md")
            with open(custom, "w", encoding="utf-8") as f:
                f.write("# Human-managed agent\n")
            skill = os.path.join(tmp, "agents", "qa", "skills", "scope.md")
            outside = os.path.join(tmp, "outside-skill.md")
            with open(outside, "w", encoding="utf-8") as f:
                f.write("# Untrusted skill\n")
            os.unlink(skill)
            os.symlink(outside, skill)

            self.assertEqual(generate_claude_agents(tmp), 0)
            self.assertFalse(os.path.lexists(generated))
            self.assertTrue(os.path.isfile(custom))

    def test_role_description_rejects_an_oversized_line(self):
        import tempfile

        from solomon_harness.integrations import (
            MAX_ROLE_LINE_CHARS,
            role_description,
        )

        with tempfile.TemporaryDirectory() as tmp:
            self._write_external_agent(
                tmp,
                role_body="# QA Profile\n\n" + ("x" * (MAX_ROLE_LINE_CHARS + 1)) + "\n",
            )
            agents_dir = os.path.join(tmp, "agents")
            role = os.path.join(agents_dir, "qa", "agents", "qa.md")

            self.assertEqual(
                role_description(role, "qa", agents_dir),
                "The qa specialist for this project.",
            )

    @unittest.skipUnless(hasattr(os, "symlink"), "symlinks are unavailable")
    def test_packaged_generator_rejects_symlinked_trust_root_and_output_dir(self):
        import tempfile

        from solomon_harness.integrations import generate_claude_agents

        with tempfile.TemporaryDirectory() as tmp:
            self._write_external_agent(tmp)
            outside_rules = os.path.join(tmp, "outside-rules.md")
            with open(outside_rules, "w", encoding="utf-8") as f:
                f.write("# Outside rules\n")
            os.symlink(outside_rules, os.path.join(tmp, "AGENTS.md"))

            with self.assertRaisesRegex(FileNotFoundError, "project instructions"):
                generate_claude_agents(tmp)

            os.unlink(os.path.join(tmp, "AGENTS.md"))
            with open(os.path.join(tmp, "AGENTS.md"), "w", encoding="utf-8") as f:
                f.write("# Project instructions\n")
            outside_dir = os.path.join(tmp, "outside-output")
            os.makedirs(os.path.join(tmp, ".claude"))
            os.makedirs(outside_dir)
            os.symlink(outside_dir, os.path.join(tmp, ".claude", "agents"))

            with self.assertRaisesRegex(ValueError, "unsafe"):
                generate_claude_agents(tmp)
            self.assertEqual(os.listdir(outside_dir), [])

    @unittest.skipUnless(hasattr(os, "symlink"), "symlinks are unavailable")
    def test_packaged_generator_replaces_destination_symlink_without_following_it(self):
        import tempfile

        from solomon_harness.integrations import generate_claude_agents

        with tempfile.TemporaryDirectory() as tmp:
            self._write_external_agent(tmp)
            with open(os.path.join(tmp, "AGENTS.md"), "w", encoding="utf-8") as f:
                f.write("# Project instructions\n")
            out_dir = os.path.join(tmp, ".claude", "agents")
            os.makedirs(out_dir)
            outside = os.path.join(tmp, "outside-output.md")
            with open(outside, "w", encoding="utf-8") as f:
                f.write("do not overwrite\n")
            destination = os.path.join(out_dir, "qa.md")
            os.symlink(outside, destination)

            self.assertEqual(generate_claude_agents(tmp), 1)

            self.assertFalse(os.path.islink(destination))
            with open(outside, "r", encoding="utf-8") as f:
                self.assertEqual(f.read(), "do not overwrite\n")

    @unittest.skipUnless(hasattr(os, "symlink"), "symlinks are unavailable")
    def test_packaged_generator_revokes_stale_wrapper_after_role_becomes_symlink(self):
        import tempfile

        from solomon_harness.integrations import generate_claude_agents

        with tempfile.TemporaryDirectory() as tmp:
            self._write_external_agent(tmp)
            with open(os.path.join(tmp, "AGENTS.md"), "w", encoding="utf-8") as f:
                f.write("# Project instructions\n")

            self.assertEqual(generate_claude_agents(tmp), 1)
            generated = os.path.join(tmp, ".claude", "agents", "qa.md")
            custom = os.path.join(tmp, ".claude", "agents", "custom.md")
            with open(custom, "w", encoding="utf-8") as f:
                f.write("# Human-managed agent\n")

            role = os.path.join(tmp, "agents", "qa", "agents", "qa.md")
            outside = os.path.join(tmp, "outside-role.md")
            with open(outside, "w", encoding="utf-8") as f:
                f.write("# Revoked role\n")
            os.unlink(role)
            os.symlink(outside, role)

            self.assertEqual(generate_claude_agents(tmp), 0)
            self.assertFalse(os.path.lexists(generated))
            self.assertTrue(os.path.isfile(custom))

    def test_packaged_generator_anchors_atomic_replace_to_output_directory_fd(self):
        import tempfile
        from unittest.mock import patch

        from solomon_harness import integrations, secure_paths

        with tempfile.TemporaryDirectory() as tmp:
            self._write_external_agent(tmp)
            with open(os.path.join(tmp, "AGENTS.md"), "w", encoding="utf-8") as f:
                f.write("# Project instructions\n")
            real_replace = os.replace
            calls = []

            def anchored_replace(src, dst, *, src_dir_fd=None, dst_dir_fd=None):
                calls.append((src_dir_fd, dst_dir_fd))
                return real_replace(
                    src,
                    dst,
                    src_dir_fd=src_dir_fd,
                    dst_dir_fd=dst_dir_fd,
                )

            with patch.object(secure_paths.os, "replace", side_effect=anchored_replace):
                self.assertEqual(integrations.generate_claude_agents(tmp), 1)

            self.assertTrue(calls)
            self.assertTrue(all(src_fd is not None for src_fd, _ in calls))
            self.assertTrue(all(dst_fd is not None for _, dst_fd in calls))


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


class TestDeprecatedGeminiGeneration(unittest.TestCase):
    def _generator(self):
        path = os.path.join(WORKSPACE, "scripts", "generate-integrations.py")
        spec = importlib.util.spec_from_file_location("gen_integrations_drift", path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def test_deprecated_gemini_generator_is_inert(self):
        gen = self._generator()
        gemini = os.path.join(WORKSPACE, ".gemini")
        before = {
            path: os.stat(os.path.join(root, path)).st_mtime_ns
            for root, _, files in os.walk(gemini)
            for path in files
        }

        self.assertEqual(gen.generate_gemini_commands(WORKSPACE), 0)

        after = {
            path: os.stat(os.path.join(root, path)).st_mtime_ns
            for root, _, files in os.walk(gemini)
            for path in files
        }
        self.assertEqual(after, before)


class TestStartAdr(unittest.TestCase):
    def test_adr_0001_records_the_start_stage_decision(self):
        adr = _read(
            os.path.join(
                "docs", "adrs", "0001-isolated-worktree-and-implementation-mode-on-start.md"
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
