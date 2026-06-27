import unittest
import os
import tempfile
import json
import importlib
import sys


class TestCompileHarnesses(unittest.TestCase):
    def setUp(self):
        # Create a temporary directory structure to simulate the project
        self.temp_dir = tempfile.TemporaryDirectory()
        self.workspace_root = self.temp_dir.name

        # Create directories
        self.agents_dir = os.path.join(self.workspace_root, "agents")
        self.templates_dir = os.path.join(self.workspace_root, "templates", "harness")
        self.patterns_dir = os.path.join(self.workspace_root, "templates", "patterns")

        os.makedirs(self.agents_dir)
        os.makedirs(os.path.join(self.templates_dir, ".agent"))
        os.makedirs(os.path.join(self.templates_dir, "skills"))

        os.makedirs(os.path.join(self.patterns_dir, "architecture"))
        os.makedirs(os.path.join(self.patterns_dir, "observability"))
        os.makedirs(os.path.join(self.patterns_dir, "security"))

        # Create global AGENTS.md
        self.global_agents_path = os.path.join(self.agents_dir, "AGENTS.md")
        with open(self.global_agents_path, "w", encoding="utf-8") as f:
            f.write("# Global Rules")

        # Create specialist agent markdown files
        self.po_md_path = os.path.join(self.agents_dir, "product_owner.md")
        with open(self.po_md_path, "w", encoding="utf-8") as f:
            f.write("# Product Owner Specialist")

        self.sm_md_path = os.path.join(self.agents_dir, "scrum_master.md")
        with open(self.sm_md_path, "w", encoding="utf-8") as f:
            f.write("# Scrum Master Specialist")

        # Create a subdirectory to ensure it is ignored
        sub_dir = os.path.join(self.agents_dir, "subdir")
        os.makedirs(sub_dir)
        with open(os.path.join(sub_dir, "ignored.md"), "w", encoding="utf-8") as f:
            f.write("# Ignored")

        # Create harness templates
        self.config_template_path = os.path.join(
            self.templates_dir, ".agent", "config.json"
        )
        with open(self.config_template_path, "w", encoding="utf-8") as f:
            json.dump({"agent_name": "{{AGENT_NAME}}", "timeout_seconds": 30}, f)

        self.main_template_path = os.path.join(self.templates_dir, "main.py")
        with open(self.main_template_path, "w", encoding="utf-8") as f:
            f.write("print('Hello from harness template')")

        self.skill_template_path = os.path.join(
            self.templates_dir, "skills", "git_operations.md"
        )
        with open(self.skill_template_path, "w", encoding="utf-8") as f:
            f.write("# Git Operations Instructions")

        # Create pattern template files
        self.hexagonal_pattern_path = os.path.join(
            self.patterns_dir, "architecture", "hexagonal.md"
        )
        with open(self.hexagonal_pattern_path, "w", encoding="utf-8") as f:
            f.write("# Hexagonal Architecture\nUse hexagonal patterns.")

        self.opentelemetry_pattern_path = os.path.join(
            self.patterns_dir, "observability", "opentelemetry.md"
        )
        with open(self.opentelemetry_pattern_path, "w", encoding="utf-8") as f:
            f.write("# OpenTelemetry\nImplement OpenTelemetry tracing.")

        self.secure_dev_pattern_path = os.path.join(
            self.patterns_dir, "security", "secure_dev.md"
        )
        with open(self.secure_dev_pattern_path, "w", encoding="utf-8") as f:
            f.write("# Secure Dev\nFollow secure coding practices.")

        # Create global config.json
        self.global_config_dir = os.path.join(self.workspace_root, ".agent")
        os.makedirs(self.global_config_dir, exist_ok=True)
        self.global_config_path = os.path.join(self.global_config_dir, "config.json")
        with open(self.global_config_path, "w", encoding="utf-8") as f:
            json.dump(
                {
                    "architecture_pattern": "hexagonal",
                    "observability_pattern": "opentelemetry",
                    "security_pattern": "secure_dev",
                },
                f,
            )

        # Inject scripts path to sys.path
        scripts_path = os.path.abspath(
            os.path.join(os.path.dirname(__file__), "..", "scripts")
        )
        if scripts_path not in sys.path:
            sys.path.insert(0, scripts_path)

    def tearDown(self):
        self.temp_dir.cleanup()

    def _get_compiler_module(self):
        # Always reload the compile-harnesses module to ensure we pick up fresh changes
        if "compile-harnesses" in sys.modules:
            del sys.modules["compile-harnesses"]
        return importlib.import_module("compile-harnesses")

    def test_compilation_success(self):
        compile_harnesses = self._get_compiler_module()

        # Run compilation
        compile_harnesses.compile_harnesses(self.workspace_root)

        # Verify compiled agent directory structure and files
        for agent_name in ["product_owner", "scrum_master"]:
            agent_root = os.path.join(self.agents_dir, agent_name)

            # Check target directory exists
            self.assertTrue(
                os.path.isdir(agent_root),
                f"Agent directory for {agent_name} not created",
            )

            # Check config.json has replaced {{AGENT_NAME}}
            config_path = os.path.join(agent_root, ".agent", "config.json")
            self.assertTrue(
                os.path.isfile(config_path), f"config.json not copied for {agent_name}"
            )
            with open(config_path, "r", encoding="utf-8") as f:
                config_data = json.load(f)
            self.assertEqual(
                config_data.get("agent_name"),
                agent_name,
                f"config.json placeholder replacement failed for {agent_name}",
            )
            self.assertEqual(config_data.get("timeout_seconds"), 30)

            # Check main.py exists
            self.assertTrue(
                os.path.isfile(os.path.join(agent_root, "main.py")),
                f"main.py not copied for {agent_name}",
            )

            # Check skills/git_operations.md exists
            self.assertTrue(
                os.path.isfile(os.path.join(agent_root, "skills", "git_operations.md")),
                f"git_operations.md not copied for {agent_name}",
            )

            # Check AGENTS.md exists in agents/agent_name/agents/
            compiled_agents_dir = os.path.join(agent_root, "agents")
            self.assertTrue(
                os.path.isdir(compiled_agents_dir),
                f"agents/ subdirectory not created for {agent_name}",
            )

            compiled_agents_md = os.path.join(compiled_agents_dir, "AGENTS.md")
            self.assertTrue(
                os.path.isfile(compiled_agents_md),
                f"AGENTS.md not copied to compiled subdirectory for {agent_name}",
            )
            with open(compiled_agents_md, "r", encoding="utf-8") as f:
                self.assertEqual(f.read(), "# Global Rules")

            # Check specific agent md exists in agents/agent_name/agents/
            specific_agent_md = os.path.join(compiled_agents_dir, f"{agent_name}.md")
            self.assertTrue(
                os.path.isfile(specific_agent_md),
                f"Specific markdown not copied to compiled subdirectory for {agent_name}",
            )
            with open(specific_agent_md, "r", encoding="utf-8") as f:
                expected_content = (
                    "# Product Owner Specialist"
                    if agent_name == "product_owner"
                    else "# Scrum Master Specialist"
                )
                self.assertTrue(f.read().startswith(expected_content))

        # Verify that subdirectories (like subdir) were not treated as agents
        self.assertFalse(
            os.path.isdir(os.path.join(self.agents_dir, "subdir", "agents"))
        )

    def test_compilation_with_nested_source_only(self):
        # Remove flat scrum_master.md to simulate cleanup
        if os.path.exists(self.sm_md_path):
            os.remove(self.sm_md_path)

        # Manually create the nested structure and write a nested agent file
        nested_sm_dir = os.path.join(self.agents_dir, "scrum_master", "agents")
        os.makedirs(nested_sm_dir, exist_ok=True)
        nested_sm_md = os.path.join(nested_sm_dir, "scrum_master.md")
        with open(nested_sm_md, "w", encoding="utf-8") as f:
            f.write("# Nested Scrum Master Specialist")

        compile_harnesses = self._get_compiler_module()

        # Run compilation
        compile_harnesses.compile_harnesses(self.workspace_root)

        # Verify compiled agent directory structure and files for scrum_master
        agent_root = os.path.join(self.agents_dir, "scrum_master")
        self.assertTrue(os.path.isdir(agent_root))

        # Check config.json exists and is updated
        config_path = os.path.join(agent_root, ".agent", "config.json")
        self.assertTrue(os.path.isfile(config_path))
        with open(config_path, "r", encoding="utf-8") as f:
            config_data = json.load(f)
        self.assertEqual(config_data.get("agent_name"), "scrum_master")

        # Check main.py exists
        self.assertTrue(os.path.isfile(os.path.join(agent_root, "main.py")))

        # Check specific agent md was preserved/restored in agents/scrum_master/agents/scrum_master.md
        specific_agent_md = os.path.join(agent_root, "agents", "scrum_master.md")
        self.assertTrue(os.path.isfile(specific_agent_md))
        with open(specific_agent_md, "r", encoding="utf-8") as f:
            self.assertTrue(f.read().startswith("# Nested Scrum Master Specialist"))

    def test_pattern_injections(self):
        # Create all subagents that should be compiled
        agents_to_create = {
            "software_architect": "# Software Architect",
            "software_engineer": "# Software Engineer",
            "qa": "# QA Specialist",
            "sre": "# SRE Specialist",
            "observability": "# Observability Specialist",
            "security": "# Security Specialist",
            "product_owner": "# Product Owner Specialist",
        }

        for name, content in agents_to_create.items():
            with open(
                os.path.join(self.agents_dir, f"{name}.md"), "w", encoding="utf-8"
            ) as f:
                f.write(content)

        compile_harnesses = self._get_compiler_module()
        compile_harnesses.compile_harnesses(self.workspace_root)

        # Verification dictionary of expected patterns
        # Format: agent_name -> (has_arch, has_obs, has_sec)
        expected = {
            "software_architect": (True, False, False),
            "software_engineer": (True, True, True),
            "qa": (True, False, True),
            "sre": (True, True, True),
            "observability": (False, True, False),
            "security": (False, False, True),
            "product_owner": (False, False, False),
        }

        for agent_name, (has_arch, has_obs, has_sec) in expected.items():
            compiled_md_path = os.path.join(
                self.agents_dir, agent_name, "agents", f"{agent_name}.md"
            )
            self.assertTrue(
                os.path.isfile(compiled_md_path),
                f"Compiled markdown missing for {agent_name}",
            )

            with open(compiled_md_path, "r", encoding="utf-8") as f:
                content = f.read()

            if has_arch:
                self.assertIn("# Hexagonal Architecture", content)
            else:
                self.assertNotIn("# Hexagonal Architecture", content)

            if has_obs:
                self.assertIn("# OpenTelemetry", content)
            else:
                self.assertNotIn("# OpenTelemetry", content)

            if has_sec:
                self.assertIn("# Secure Dev", content)
            else:
                self.assertNotIn("# Secure Dev", content)

    def test_double_append_prevention(self):
        # Create software_engineer agent
        se_path = os.path.join(self.agents_dir, "software_engineer.md")
        with open(se_path, "w", encoding="utf-8") as f:
            f.write("# Software Engineer\nOriginal content.")

        compile_harnesses = self._get_compiler_module()

        # Compile first time
        compile_harnesses.compile_harnesses(self.workspace_root)

        compiled_md_path = os.path.join(
            self.agents_dir, "software_engineer", "agents", "software_engineer.md"
        )
        with open(compiled_md_path, "r", encoding="utf-8") as f:
            content_v1 = f.read()

        # Count occurrences of Hexagonal Architecture pattern text
        self.assertEqual(content_v1.count("# Hexagonal Architecture"), 1)

        # Compile second time, reading from nested compiled agent as the source
        # But wait, to simulate nested-only source, we remove the flat source
        os.remove(se_path)
        compile_harnesses.compile_harnesses(self.workspace_root)

        with open(compiled_md_path, "r", encoding="utf-8") as f:
            content_v2 = f.read()

        # Count occurrences of patterns after second compile
        self.assertEqual(content_v2.count("# Hexagonal Architecture"), 1)
        self.assertEqual(content_v2.count("# OpenTelemetry"), 1)
        self.assertEqual(content_v2.count("# Secure Dev"), 1)
        self.assertTrue(content_v2.startswith("# Software Engineer\nOriginal content."))

    def test_pattern_removal_when_config_cleared(self):
        # Create software_engineer agent
        se_path = os.path.join(self.agents_dir, "software_engineer.md")
        with open(se_path, "w", encoding="utf-8") as f:
            f.write("# Software Engineer\nOriginal content.")

        compile_harnesses = self._get_compiler_module()
        compile_harnesses.compile_harnesses(self.workspace_root)

        # Verify it has hexagonal architecture
        compiled_md_path = os.path.join(
            self.agents_dir, "software_engineer", "agents", "software_engineer.md"
        )
        with open(compiled_md_path, "r", encoding="utf-8") as f:
            content_v1 = f.read()
        self.assertIn("# Hexagonal Architecture", content_v1)

        # Clear pattern from config
        with open(self.global_config_path, "w", encoding="utf-8") as f:
            json.dump(
                {
                    "architecture_pattern": "none",
                    "observability_pattern": "none",
                    "security_pattern": "none",
                },
                f,
            )

        # Compile again
        os.remove(se_path)  # simulate nested source
        compile_harnesses.compile_harnesses(self.workspace_root)

        with open(compiled_md_path, "r", encoding="utf-8") as f:
            content_v2 = f.read()

        # Assert patterns are removed
        self.assertNotIn("# Hexagonal Architecture", content_v2)
        self.assertNotIn("# OpenTelemetry", content_v2)
        self.assertNotIn("# Secure Dev", content_v2)
        self.assertTrue(content_v2.startswith("# Software Engineer\nOriginal content."))

    def test_path_traversal_prevention(self):
        # Create a software_engineer agent which is affected by architecture patterns
        se_path = os.path.join(self.agents_dir, "software_engineer.md")
        with open(se_path, "w", encoding="utf-8") as f:
            f.write("# Software Engineer")

        # Set malicious architecture_pattern in config
        with open(self.global_config_path, "w", encoding="utf-8") as f:
            json.dump(
                {
                    "architecture_pattern": "../../../malicious_pattern",
                    "observability_pattern": "none",
                    "security_pattern": "none",
                },
                f,
            )

        compile_harnesses = self._get_compiler_module()

        # Run compilation - should exit with SystemExit
        with self.assertRaises(SystemExit):
            compile_harnesses.compile_harnesses(self.workspace_root)


if __name__ == "__main__":
    unittest.main()
