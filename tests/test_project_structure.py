import os
import tempfile
import shutil
import json
import unittest
from unittest.mock import patch, MagicMock

from solomon_harness.tools.database_client import DatabaseClient
from solomon_harness.bootstrap import index_codebase, scan_project_structure

class TestProjectStructure(unittest.TestCase):
    def setUp(self):
        # Create temp project directory
        self.temp_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.temp_dir, "test_memory.db")
        
        # Setup mock project structure
        self.src_dir = os.path.join(self.temp_dir, "solomon_harness")
        os.makedirs(self.src_dir, exist_ok=True)
        
        with open(os.path.join(self.src_dir, "__init__.py"), "w") as f:
            f.write("# init\n")
            
        with open(os.path.join(self.src_dir, "cli.py"), "w") as f:
            f.write("import os\nfrom solomon_harness.tools import database_client\n")
            
        self.tools_dir = os.path.join(self.src_dir, "tools")
        os.makedirs(self.tools_dir, exist_ok=True)
        with open(os.path.join(self.tools_dir, "__init__.py"), "w") as f:
            f.write("# tools init\n")
        with open(os.path.join(self.tools_dir, "database_client.py"), "w") as f:
            f.write("import sqlite3\n")
            
        self.tests_dir = os.path.join(self.temp_dir, "tests")
        os.makedirs(self.tests_dir, exist_ok=True)
        with open(os.path.join(self.tests_dir, "test_dummy.py"), "w") as f:
            f.write("def test_dummy(): pass\n")
            
        # Create dummy ADR
        self.adr_dir = os.path.join(self.temp_dir, "docs", "adr")
        os.makedirs(self.adr_dir, exist_ok=True)
        with open(os.path.join(self.adr_dir, "0001-test.md"), "w") as f:
            f.write("# ADR 1\n")
            
        # Create dummy agent
        self.agents_dir = os.path.join(self.temp_dir, "agents")
        os.makedirs(self.agents_dir, exist_ok=True)
        os.makedirs(os.path.join(self.agents_dir, "scrum_master"), exist_ok=True)
        
        # Create dummy command
        self.cmd_dir = os.path.join(self.temp_dir, ".claude", "commands")
        os.makedirs(self.cmd_dir, exist_ok=True)
        with open(os.path.join(self.cmd_dir, "solomon-start.md"), "w") as f:
            f.write("# Start command\n")
            
        # Create pyproject.toml
        self.pyproject_path = os.path.join(self.temp_dir, "pyproject.toml")
        with open(self.pyproject_path, "w") as f:
            f.write('[project]\nname = "test-project"\ndependencies = ["fastapi", "surrealdb"]\n[project.scripts]\nrun-cli = "solomon_harness.cli:main"\n')

        # Initialize the database client
        self.db = DatabaseClient(db_path=self.db_path, harness_dir=self.temp_dir)

    def tearDown(self):
        self.db.close()
        shutil.rmtree(self.temp_dir)

    def test_scan_project_structure(self):
        # 1. Ensure indexing works
        index_codebase(self.temp_dir, self.db)
        
        # 2. Scan project structure
        structure = scan_project_structure(self.temp_dir, self.db)
        
        # Verify structure contents
        self.assertIsNotNone(structure)
        self.assertIn("manifest_signature", structure)
        self.assertIn("generated_at", structure)
        self.assertIn("pyproject.toml", structure.get("detected_stack", []))
        self.assertIn("FastAPI", structure.get("detected_stack", []))
        self.assertIn("SurrealDB", structure.get("detected_stack", []))
        self.assertIn("script:run-cli = \"solomon_harness.cli:main\"", structure.get("entry_points", []))
        self.assertIn("solomon_harness", structure.get("modules", {}))
        self.assertIn("solomon_harness.tools", structure.get("modules", {}))
        self.assertIn("sqlite3", structure.get("modules", {}).get("solomon_harness.tools", []))
        self.assertIn("tests/test_dummy.py", structure.get("test_layout", []))
        self.assertIn("0001-test.md", structure.get("patterns", {}).get("adrs", []))
        self.assertIn("scrum_master", structure.get("patterns", {}).get("agents", []))
        self.assertIn("solomon-start.md", structure.get("patterns", {}).get("commands", []))
        
        # Verify saved in memory
        saved_raw = self.db.get_memory("__project_structure__")
        self.assertIsNotNone(saved_raw)
        saved = json.loads(saved_raw)
        self.assertEqual(saved["manifest_signature"], structure["manifest_signature"])

    def test_idempotent_skip(self):
        # Run initial scan
        index_codebase(self.temp_dir, self.db)
        structure1 = scan_project_structure(self.temp_dir, self.db)
        timestamp1 = structure1["generated_at"]
        
        # Run second scan immediately (no changes)
        structure2 = scan_project_structure(self.temp_dir, self.db)
        timestamp2 = structure2["generated_at"]
        
        # Verify it skipped (timestamp did not change)
        self.assertEqual(timestamp1, timestamp2)

    def test_incremental_delta_update(self):
        # Run initial scan
        index_codebase(self.temp_dir, self.db)
        structure1 = scan_project_structure(self.temp_dir, self.db)
        timestamp1 = structure1["generated_at"]
        
        # Sleep or make modification
        import time
        time.sleep(1) # Ensure modification time is different
        
        # Modify a file to change manifest signature
        with open(os.path.join(self.src_dir, "cli.py"), "a") as f:
            f.write("# some edit\n")
            
        # Re-index and scan
        index_codebase(self.temp_dir, self.db)
        structure2 = scan_project_structure(self.temp_dir, self.db)
        timestamp2 = structure2["generated_at"]
        
        # Verify scan updated the record and timestamp changed
        self.assertNotEqual(timestamp1, timestamp2)
        self.assertNotEqual(structure1["manifest_signature"], structure2["manifest_signature"])

    def test_scan_failure_safe(self):
        # Verify scan failure does not raise / block
        mock_db = MagicMock()
        mock_db.get_memory.side_effect = Exception("SurrealDB connection lost")
        
        # Should not raise exception
        try:
            res = scan_project_structure(self.temp_dir, mock_db)
            # Should still return some structure or fallback
            self.assertIsNotNone(res)
        except Exception as e:
            self.fail(f"scan_project_structure raised exception on DB error: {e}")
