import unittest
import os
import json

class TestHarnessInit(unittest.TestCase):
    def setUp(self):
        self.workspace_dir = "/Users/marcelo/Documents/Projects/solomon-harness"

    def test_directories_exist(self):
        expected_dirs = [
            ".agent",
            "agents",
            "skills",
            "tools",
            "memory",
            "memory/short_term",
            "memory/long_term",
            "tests"
        ]
        for d in expected_dirs:
            full_path = os.path.join(self.workspace_dir, d)
            self.assertTrue(
                os.path.isdir(full_path),
                f"Directory {d} does not exist at {full_path}"
            )

    def test_config_json(self):
        config_path = os.path.join(self.workspace_dir, ".agent", "config.json")
        self.assertTrue(os.path.isfile(config_path), f"config.json not found at {config_path}")
        
        with open(config_path, "r", encoding="utf-8") as f:
            config = json.load(f)
            
        self.assertEqual(config.get("timeout_seconds"), 30)
        self.assertEqual(config.get("max_retries"), 3)
        self.assertIn("models", config)
        
        models = config["models"]
        self.assertEqual(models.get("default"), "gemini-3.5-flash")
        self.assertEqual(models.get("reasoning"), "gemini-3.5-pro")
        self.assertEqual(models.get("embedding"), "text-embedding-004")

    def test_template_config_json_database(self):
        config_path = os.path.join(self.workspace_dir, "templates", "harness", ".agent", "config.json")
        self.assertTrue(os.path.isfile(config_path), f"config.json template not found at {config_path}")
        
        with open(config_path, "r", encoding="utf-8") as f:
            config = json.load(f)
            
        self.assertIn("database", config)
        db_config = config["database"]
        self.assertEqual(db_config.get("provider"), "surrealdb")
        self.assertEqual(db_config.get("url"), "ws://localhost:8000/rpc")
        self.assertEqual(db_config.get("namespace"), "solomon")
        self.assertEqual(db_config.get("database"), "harness")
        self.assertEqual(db_config.get("username"), "root")
        self.assertEqual(db_config.get("password"), "root")

    def test_secure_vault_enc(self):
        vault_path = os.path.join(self.workspace_dir, ".agent", "secure_vault.enc")
        self.assertTrue(os.path.isfile(vault_path), f"secure_vault.enc not found at {vault_path}")
        
        with open(vault_path, "r", encoding="utf-8") as f:
            content = f.read().strip()
            
        self.assertEqual(content, "eyJhbnRocm9waWNfYXBpX2tleSI6ICJtb2NrX2tleSJ9")

    def test_gitignore_entries(self):
        gitignore_path = os.path.join(self.workspace_dir, ".gitignore")
        self.assertTrue(os.path.isfile(gitignore_path), f".gitignore not found at {gitignore_path}")
        
        with open(gitignore_path, "r", encoding="utf-8") as f:
            lines = [line.strip() for line in f.readlines()]
            
        expected_ignores = [
            "memory/long_term/harness.db",
            "memory/short_term/*.json",
            ".agent/secure_vault.enc"
        ]
        for rule in expected_ignores:
            self.assertIn(rule, lines, f"Ignore rule '{rule}' not found in .gitignore")

if __name__ == "__main__":
    unittest.main()
