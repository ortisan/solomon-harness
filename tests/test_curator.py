import os
import shutil
import tempfile
import unittest
import hashlib
from solomon_harness import curator

def _write_agent(root, name, description):
    role_dir = os.path.join(root, "agents", name, "agents")
    os.makedirs(role_dir)
    with open(os.path.join(role_dir, f"{name}.md"), "w", encoding="utf-8") as f:
        f.write(f"# {name}\n\n{description}\n")

def _tree_digest(path):
    h = hashlib.sha256()
    for dirpath, dirnames, filenames in os.walk(path):
        dirnames.sort()
        for name in sorted(filenames):
            full = os.path.join(dirpath, name)
            h.update(os.path.relpath(full, path).encode())
            with open(full, "rb") as f:
                h.update(f.read())
    return h.hexdigest()

class MockDBClient:
    def __init__(self):
        self.decisions = []

    def log_decision(self, title, rationale, outcome, author, branch, commit_sha):
        self.decisions.append({
            "title": title,
            "rationale": rationale,
            "outcome": outcome,
            "author": author,
            "branch": branch,
            "commit_sha": commit_sha,
        })
        return f"decision-{len(self.decisions)}"

class TestSweep(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="curator-")
        _write_agent(self.root, "qa", "The QA Specialist.")
        _write_agent(self.root, "security", "The Security Specialist.")
        self.agents_dir = os.path.join(self.root, "agents")
        self.db = MockDBClient()

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def test_sweep_emits_one_proposal_per_affected_agent_with_two_sources(self):
        # We have two agents, qa is drifted (has 2 sources), security is clean.
        def analyzer(agent_name, catalog_desc, baseline):
            if agent_name == "qa":
                return curator.DriftMatch(
                    agent="qa",
                    drift_description="Missing contract validation",
                    sources=["RFC 2119 (1997)", "SemVer 2.0.0 (2013)"],
                    rationale="QA needs RFC 2119 checking."
                )
            return None

        before = _tree_digest(self.agents_dir)
        result = curator.sweep_fleet("baseline", analyzer, self.db, self.root)
        
        self.assertEqual(len(result.proposals), 1)
        self.assertEqual(result.proposals[0].agent, "qa")
        self.assertEqual(result.proposals[0].drift_description, "Missing contract validation")
        self.assertEqual(result.proposals[0].sources, ("RFC 2119 (1997)", "SemVer 2.0.0 (2013)"))
        self.assertEqual(len(result.needs_evidence), 0)
        
        # Verify save_decision was called
        self.assertEqual(len(self.db.decisions), 1)
        self.assertEqual(self.db.decisions[0]["title"], "Propose gap for qa: Missing contract validation")
        self.assertEqual(self.db.decisions[0]["author"], "practice_curator")
        
        # Verify read-only stance
        self.assertEqual(_tree_digest(self.agents_dir), before)

    def test_sweep_drift_with_insufficient_sources_is_listed_in_needs_evidence(self):
        # qa has drift but only 1 source. It must not emit proposal but go to needs_evidence.
        def analyzer(agent_name, catalog_desc, baseline):
            if agent_name == "qa":
                return curator.DriftMatch(
                    agent="qa",
                    drift_description="Missing contract validation",
                    sources=["RFC 2119 (1997)"],
                    rationale="Insufficient evidence."
                )
            return None

        result = curator.sweep_fleet("baseline", analyzer, self.db, self.root)
        self.assertEqual(len(result.proposals), 0)
        self.assertEqual(len(result.needs_evidence), 1)
        self.assertEqual(result.needs_evidence[0]["agent"], "qa")
        self.assertEqual(result.needs_evidence[0]["drift_description"], "Missing contract validation")
        self.assertEqual(len(self.db.decisions), 0)

    def test_sweep_clean_agents_emit_no_proposals(self):
        # All agents clean.
        def analyzer(agent_name, catalog_desc, baseline):
            return None

        result = curator.sweep_fleet("baseline", analyzer, self.db, self.root)
        self.assertEqual(len(result.proposals), 0)
        self.assertEqual(len(result.needs_evidence), 0)
