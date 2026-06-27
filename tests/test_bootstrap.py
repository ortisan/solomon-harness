import unittest
import os
import json
import subprocess
import shutil

class TestBootstrapAgent(unittest.TestCase):
    def setUp(self):
        self.workspace_dir = "/Users/marcelo/Documents/Projects/solomon-harness"
        self.config_dir = os.path.join(self.workspace_dir, ".agent")
        self.config_path = os.path.join(self.config_dir, "config.json")
        self.backup_path = os.path.join(self.config_dir, "config.json.bak")
        self.script_path = os.path.join(self.workspace_dir, "scripts", "bootstrap-agent.sh")
        
        # Ensure we backup config.json if it exists
        if os.path.exists(self.config_path):
            shutil.copyfile(self.config_path, self.backup_path)
            
        # Write a clean, known starting configuration to test preservation
        self.test_initial_config = {
            "models": {
                "default": "test-default-model",
                "reasoning": "test-reasoning-model",
                "embedding": "test-embedding-model"
            },
            "timeout_seconds": 99,
            "max_retries": 5,
            "database": {
                "provider": "sqlite",
                "url": "test.db"
            }
        }
        os.makedirs(self.config_dir, exist_ok=True)
        with open(self.config_path, "w", encoding="utf-8") as f:
            json.dump(self.test_initial_config, f, indent=2)

    def tearDown(self):
        # Restore the original config.json if we backed it up
        if os.path.exists(self.backup_path):
            shutil.move(self.backup_path, self.config_path)
        elif os.path.exists(self.config_path):
            os.remove(self.config_path)

    def test_non_interactive_default_via_env(self):
        # Run bootstrap-agent.sh with NON_INTERACTIVE=true
        env = os.environ.copy()
        env["NON_INTERACTIVE"] = "true"
        
        result = subprocess.run(
            ["bash", self.script_path],
            cwd=self.workspace_dir,
            env=env,
            capture_output=True,
            text=True
        )
        
        self.assertEqual(result.returncode, 0, f"Script failed with: {result.stderr}")
        
        # Verify config.json values
        with open(self.config_path, "r", encoding="utf-8") as f:
            config = json.load(f)
            
        # Check defaults are written
        self.assertEqual(config.get("architecture_pattern"), "hexagonal")
        self.assertEqual(config.get("observability_pattern"), "opentelemetry")
        self.assertEqual(config.get("security_pattern"), "secure_dev")
        
        # Check preserved initial configuration
        self.assertEqual(config.get("timeout_seconds"), 99)
        self.assertEqual(config.get("max_retries"), 5)
        self.assertEqual(config.get("models", {}).get("default"), "test-default-model")
        self.assertEqual(config.get("database", {}).get("provider"), "sqlite")

    def test_non_interactive_default_via_flag(self):
        # Run bootstrap-agent.sh with --non-interactive
        result = subprocess.run(
            ["bash", self.script_path, "--non-interactive"],
            cwd=self.workspace_dir,
            capture_output=True,
            text=True
        )
        
        self.assertEqual(result.returncode, 0, f"Script failed with: {result.stderr}")
        
        # Verify config.json values
        with open(self.config_path, "r", encoding="utf-8") as f:
            config = json.load(f)
            
        # Check defaults are written
        self.assertEqual(config.get("architecture_pattern"), "hexagonal")
        self.assertEqual(config.get("observability_pattern"), "opentelemetry")
        self.assertEqual(config.get("security_pattern"), "secure_dev")

    def test_interactive_choices_first_option(self):
        # Run bootstrap-agent.sh interactively and send:
        # 1 (Clean Architecture)
        # 1 (Basic Logs)
        # 1 (Standard Security)
        inputs = "1\n1\n1\n"
        
        result = subprocess.run(
            ["bash", self.script_path],
            cwd=self.workspace_dir,
            input=inputs,
            capture_output=True,
            text=True
        )
        
        self.assertEqual(result.returncode, 0, f"Script failed with: {result.stderr}")
        
        # Verify config.json values
        with open(self.config_path, "r", encoding="utf-8") as f:
            config = json.load(f)
            
        self.assertEqual(config.get("architecture_pattern"), "clean")
        self.assertEqual(config.get("observability_pattern"), "basic")
        self.assertEqual(config.get("security_pattern"), "standard")
        
        # Verify preservation
        self.assertEqual(config.get("timeout_seconds"), 99)

    def test_interactive_choices_alternative_option(self):
        # Run bootstrap-agent.sh interactively and send:
        # 2 (Functional Architecture)
        # 2 (OpenTelemetry)
        # 2 (Secure Dev)
        inputs = "2\n2\n2\n"
        
        result = subprocess.run(
            ["bash", self.script_path],
            cwd=self.workspace_dir,
            input=inputs,
            capture_output=True,
            text=True
        )
        
        self.assertEqual(result.returncode, 0, f"Script failed with: {result.stderr}")
        
        # Verify config.json values
        with open(self.config_path, "r", encoding="utf-8") as f:
            config = json.load(f)
            
        self.assertEqual(config.get("architecture_pattern"), "functional")
        self.assertEqual(config.get("observability_pattern"), "opentelemetry")
        self.assertEqual(config.get("security_pattern"), "secure_dev")

if __name__ == "__main__":
    unittest.main()
