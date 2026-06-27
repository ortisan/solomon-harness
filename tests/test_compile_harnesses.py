import unittest
import os
import tempfile
import shutil
import json

# We will import scripts.compile_harnesses or run it.
# Since compile-harnesses.py might not exist yet, we import it inside the test method or catch ImportError.

class TestCompileHarnesses(unittest.TestCase):
    def setUp(self):
        # Create a temporary directory structure to simulate the project
        self.temp_dir = tempfile.TemporaryDirectory()
        self.workspace_root = self.temp_dir.name
        
        # Create directories
        self.agents_dir = os.path.join(self.workspace_root, "agents")
        self.templates_dir = os.path.join(self.workspace_root, "templates", "harness")
        os.makedirs(self.agents_dir)
        os.makedirs(os.path.join(self.templates_dir, ".agent"))
        os.makedirs(os.path.join(self.templates_dir, "skills"))

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
        self.config_template_path = os.path.join(self.templates_dir, ".agent", "config.json")
        with open(self.config_template_path, "w", encoding="utf-8") as f:
            json.dump({
                "agent_name": "{{AGENT_NAME}}",
                "timeout_seconds": 30
            }, f)

        self.main_template_path = os.path.join(self.templates_dir, "main.py")
        with open(self.main_template_path, "w", encoding="utf-8") as f:
            f.write("print('Hello from harness template')")

        self.skill_template_path = os.path.join(self.templates_dir, "skills", "git_operations.md")
        with open(self.skill_template_path, "w", encoding="utf-8") as f:
            f.write("# Git Operations Instructions")

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_compilation_success(self):
        # Dynamically import scripts/compile-harnesses.py
        # To handle python file naming (with hyphen), we can import via runpy or sys.path
        import sys
        scripts_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "scripts"))
        if scripts_path not in sys.path:
            sys.path.insert(0, scripts_path)
        
        # This import should succeed now
        import importlib
        compile_harnesses = importlib.import_module("compile-harnesses")
        
        # Run compilation
        compile_harnesses.compile_harnesses(self.workspace_root)
        
        # Verify compiled agent directory structure and files
        for agent_name in ["product_owner", "scrum_master"]:
            agent_root = os.path.join(self.agents_dir, agent_name)
            
            # Check target directory exists
            self.assertTrue(os.path.isdir(agent_root), f"Agent directory for {agent_name} not created")
            
            # Check config.json has replaced {{AGENT_NAME}}
            config_path = os.path.join(agent_root, ".agent", "config.json")
            self.assertTrue(os.path.isfile(config_path), f"config.json not copied for {agent_name}")
            with open(config_path, "r", encoding="utf-8") as f:
                config_data = json.load(f)
            self.assertEqual(config_data.get("agent_name"), agent_name, f"config.json placeholder replacement failed for {agent_name}")
            self.assertEqual(config_data.get("timeout_seconds"), 30)

            # Check main.py exists
            self.assertTrue(os.path.isfile(os.path.join(agent_root, "main.py")), f"main.py not copied for {agent_name}")

            # Check skills/git_operations.md exists
            self.assertTrue(os.path.isfile(os.path.join(agent_root, "skills", "git_operations.md")), f"git_operations.md not copied for {agent_name}")

            # Check AGENTS.md exists in agents/agent_name/agents/
            compiled_agents_dir = os.path.join(agent_root, "agents")
            self.assertTrue(os.path.isdir(compiled_agents_dir), f"agents/ subdirectory not created for {agent_name}")
            
            compiled_agents_md = os.path.join(compiled_agents_dir, "AGENTS.md")
            self.assertTrue(os.path.isfile(compiled_agents_md), f"AGENTS.md not copied to compiled subdirectory for {agent_name}")
            with open(compiled_agents_md, "r", encoding="utf-8") as f:
                self.assertEqual(f.read(), "# Global Rules")

            # Check specific agent md exists in agents/agent_name/agents/
            specific_agent_md = os.path.join(compiled_agents_dir, f"{agent_name}.md")
            self.assertTrue(os.path.isfile(specific_agent_md), f"Specific markdown not copied to compiled subdirectory for {agent_name}")
            with open(specific_agent_md, "r", encoding="utf-8") as f:
                expected_content = "# Product Owner Specialist" if agent_name == "product_owner" else "# Scrum Master Specialist"
                self.assertEqual(f.read(), expected_content)

        # Verify that subdirectories (like subdir) were not treated as agents
        self.assertFalse(os.path.isdir(os.path.join(self.agents_dir, "subdir", "agents")))

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
            
        # Dynamically import compile-harnesses
        import sys
        scripts_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "scripts"))
        if scripts_path not in sys.path:
            sys.path.insert(0, scripts_path)
        
        import importlib
        compile_harnesses = importlib.import_module("compile-harnesses")
        
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
            self.assertEqual(f.read(), "# Nested Scrum Master Specialist")

if __name__ == "__main__":
    unittest.main()
