import os
import tempfile
import shutil
import json
import unittest
from unittest.mock import patch, MagicMock

from solomon_harness.tools.database_client import DatabaseClient
from solomon_harness.bootstrap import index_codebase, scan_project_structure

class TestMemoryTriggers(unittest.TestCase):
    def setUp(self):
        # Create temp project directory
        self.temp_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.temp_dir, "test_memory.db")
        
        # Setup mock project structure
        self.src_dir = os.path.join(self.temp_dir, "solomon_harness")
        os.makedirs(self.src_dir, exist_ok=True)
        with open(os.path.join(self.src_dir, "__init__.py"), "w") as f:
            f.write("# init\n")

        # Initialize the database client
        self.db = DatabaseClient(db_path=self.db_path, harness_dir=self.temp_dir)
        
        # Populate issue 7 in DB
        self.db.log_issue(
            github_id="7",
            title="feat(memory): living project memory",
            type_="feature",
            status="In Progress",
            milestone_id=None
        )

    def tearDown(self):
        self.db.close()
        shutil.rmtree(self.temp_dir)

    def test_log_handoff_trigger(self):
        # Delete any existing project structure record
        self.db.delete_memory("__project_structure__")
        
        # Log a handoff
        self.db.log_handoff(
            sender="software_engineer",
            recipient="qa",
            contract_type="plan",
            contract_path="PLAN.md",
            status="open",
            summary="Implemented issue 7 plan"
        )
        
        # Verify it automatically generated the project structure
        saved_raw = self.db.get_memory("__project_structure__")
        self.assertIsNotNone(saved_raw)
        saved = json.loads(saved_raw)
        self.assertIn("manifest_signature", saved)

    def test_save_release_trigger(self):
        # Delete any existing project structure and evolution records
        self.db.delete_memory("__project_structure__")
        self.db.delete_memory("__project_evolution__")
        
        # Save a release
        self.db.save_release(
            version="v0.12.0",
            tag="v0.12.0",
            notes="Release notes here",
            issue_github_id="7",
            milestone_id="1"
        )
        
        # 1. Verify project structure is refreshed
        saved_raw = self.db.get_memory("__project_structure__")
        self.assertIsNotNone(saved_raw)
        
        # 2. Verify evolution log is appended
        evo_raw = self.db.get_memory("__project_evolution__")
        self.assertIsNotNone(evo_raw)
        evo = json.loads(evo_raw)
        self.assertEqual(len(evo), 1)
        self.assertEqual(evo[0]["issue_number"], "7")
        self.assertEqual(evo[0]["issue_title"], "feat(memory): living project memory")
        self.assertEqual(evo[0]["version"], "v0.12.0")
        self.assertIsNotNone(evo[0]["date"])
