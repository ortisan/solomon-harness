import json
import os
import shutil
import subprocess
import tempfile
import unittest


class TestBootstrapAgent(unittest.TestCase):
    def setUp(self):
        # Resolve real workspace root dynamically
        self.real_workspace_dir = os.path.dirname(
            os.path.dirname(os.path.abspath(__file__))
        )

        # Create a temporary directory for isolation
        self.test_dir = tempfile.TemporaryDirectory()
        self.workspace_dir = self.test_dir.name

        # Copy required templates, agents, and scripts to the test workspace
        shutil.copytree(
            os.path.join(self.real_workspace_dir, "templates"),
            os.path.join(self.workspace_dir, "templates"),
        )
        shutil.copytree(
            os.path.join(self.real_workspace_dir, "agents"),
            os.path.join(self.workspace_dir, "agents"),
        )
        shutil.copytree(
            os.path.join(self.real_workspace_dir, "scripts"),
            os.path.join(self.workspace_dir, "scripts"),
        )

        # Initialize a dummy git repository in the temporary workspace
        # to satisfy git command dependencies in the bootstrap script.
        subprocess.run(["git", "init"], cwd=self.workspace_dir, capture_output=True)
        subprocess.run(
            [
                "git",
                "remote",
                "add",
                "origin",
                "https://github.com/dummy/repo.git",
            ],
            cwd=self.workspace_dir,
            capture_output=True,
        )
        subprocess.run(
            ["git", "config", "user.name", "Test User"],
            cwd=self.workspace_dir,
            capture_output=True,
        )
        subprocess.run(
            ["git", "config", "user.email", "test@example.com"],
            cwd=self.workspace_dir,
            capture_output=True,
        )
        with open(os.path.join(self.workspace_dir, "README.md"), "w") as f:
            f.write("# Dummy project")
        subprocess.run(
            ["git", "add", "README.md"], cwd=self.workspace_dir, capture_output=True
        )
        subprocess.run(
            ["git", "commit", "-m", "Initial commit"],
            cwd=self.workspace_dir,
            capture_output=True,
        )

        # Setup paths inside the sandboxed directory
        self.config_dir = os.path.join(self.workspace_dir, ".agent")
        self.config_path = os.path.join(self.config_dir, "config.json")
        self.script_path = os.path.join(
            self.workspace_dir, "scripts", "bootstrap-agent.sh"
        )

        # Write a clean, known starting configuration to test preservation
        self.test_initial_config = {
            "models": {
                "default": "test-default-model",
                "reasoning": "test-reasoning-model",
                "embedding": "test-embedding-model",
            },
            "timeout_seconds": 99,
            "max_retries": 5,
            "database": {"provider": "sqlite", "url": "test.db"},
        }
        os.makedirs(self.config_dir, exist_ok=True)
        with open(self.config_path, "w", encoding="utf-8") as f:
            json.dump(self.test_initial_config, f, indent=2)

    def tearDown(self):
        # Clean up temporary directory
        self.test_dir.cleanup()

    def test_non_interactive_default_via_env(self):
        env = os.environ.copy()
        env["NON_INTERACTIVE"] = "true"

        result = subprocess.run(
            ["bash", self.script_path],
            cwd=self.workspace_dir,
            env=env,
            capture_output=True,
            text=True,
        )

        self.assertEqual(result.returncode, 0, f"Script failed with: {result.stderr}")

        with open(self.config_path, "r", encoding="utf-8") as f:
            config = json.load(f)

        self.assertEqual(config.get("architecture_pattern"), "hexagonal")
        self.assertEqual(config.get("observability_pattern"), "opentelemetry")
        self.assertEqual(config.get("security_pattern"), "secure_dev")

        # Check preserved initial configuration
        self.assertEqual(config.get("timeout_seconds"), 99)
        self.assertEqual(config.get("max_retries"), 5)
        self.assertEqual(config.get("models", {}).get("default"), "test-default-model")
        self.assertEqual(config.get("database", {}).get("provider"), "sqlite")

    def test_non_interactive_default_via_flag(self):
        result = subprocess.run(
            ["bash", self.script_path, "--non-interactive"],
            cwd=self.workspace_dir,
            capture_output=True,
            text=True,
        )

        self.assertEqual(result.returncode, 0, f"Script failed with: {result.stderr}")

        with open(self.config_path, "r", encoding="utf-8") as f:
            config = json.load(f)

        self.assertEqual(config.get("architecture_pattern"), "hexagonal")
        self.assertEqual(config.get("observability_pattern"), "opentelemetry")
        self.assertEqual(config.get("security_pattern"), "secure_dev")

    def test_interactive_choices_first_option(self):
        inputs = "1\n1\n1\n"

        result = subprocess.run(
            ["bash", self.script_path],
            cwd=self.workspace_dir,
            input=inputs,
            capture_output=True,
            text=True,
        )

        self.assertEqual(result.returncode, 0, f"Script failed with: {result.stderr}")

        with open(self.config_path, "r", encoding="utf-8") as f:
            config = json.load(f)

        self.assertEqual(config.get("architecture_pattern"), "clean")
        self.assertEqual(config.get("observability_pattern"), "basic")
        self.assertEqual(config.get("security_pattern"), "standard")
        self.assertEqual(config.get("timeout_seconds"), 99)

    def test_interactive_choices_alternative_option(self):
        inputs = "2\n2\n2\n"

        result = subprocess.run(
            ["bash", self.script_path],
            cwd=self.workspace_dir,
            input=inputs,
            capture_output=True,
            text=True,
        )

        self.assertEqual(result.returncode, 0, f"Script failed with: {result.stderr}")

        with open(self.config_path, "r", encoding="utf-8") as f:
            config = json.load(f)

        self.assertEqual(config.get("architecture_pattern"), "functional")
        self.assertEqual(config.get("observability_pattern"), "opentelemetry")
        self.assertEqual(config.get("security_pattern"), "secure_dev")


if __name__ == "__main__":
    unittest.main()
