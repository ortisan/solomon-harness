import os
import shutil
import tempfile
import unittest
import hashlib
import subprocess
import json
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

    def test_sweep_reads_persona_and_skills(self):
        # Create persona.md and skills for the qa agent
        qa_dir = os.path.join(self.root, "agents", "qa")
        
        with open(os.path.join(qa_dir, "persona.md"), "w", encoding="utf-8") as f:
            f.write("QA Persona details")
            
        skills_dir = os.path.join(qa_dir, "skills")
        os.makedirs(skills_dir)
        with open(os.path.join(skills_dir, "test_skill.md"), "w", encoding="utf-8") as f:
            f.write("QA Skill details")
            
        # Write a non-markdown file to ensure it's ignored
        with open(os.path.join(skills_dir, "config.json"), "w", encoding="utf-8") as f:
            f.write("{}")

        captured_content = None
        def analyzer(agent_name, catalog_desc, baseline):
            nonlocal captured_content
            if agent_name == "qa":
                captured_content = catalog_desc
                return curator.DriftMatch(
                    agent="qa",
                    drift_description="Drift found",
                    sources=["source1", "source2"],
                    rationale="rationale"
                )
            return None

        result = curator.sweep_fleet("baseline", analyzer, self.db, self.root)
        self.assertEqual(len(result.proposals), 1)
        self.assertIn("The QA Specialist.", captured_content)
        self.assertIn("QA Persona details", captured_content)
        self.assertIn("QA Skill details", captured_content)
        self.assertNotIn("{}", captured_content)

    def test_sweep_with_zero_sources_goes_to_needs_evidence(self):
        def analyzer(agent_name, catalog_desc, baseline):
            if agent_name == "qa":
                return curator.DriftMatch(
                    agent="qa",
                    drift_description="Drift with zero sources",
                    sources=[],
                    rationale="No sources"
                )
            return None

        result = curator.sweep_fleet("baseline", analyzer, self.db, self.root)
        self.assertEqual(len(result.proposals), 0)
        self.assertEqual(len(result.needs_evidence), 1)
        self.assertEqual(result.needs_evidence[0]["agent"], "qa")
        self.assertEqual(result.needs_evidence[0]["drift_description"], "Drift with zero sources")
        self.assertEqual(len(self.db.decisions), 0)

    def test_sweep_missing_agents_dir_returns_empty(self):
        empty_root = os.path.join(self.root, "non_existent")
        def analyzer(agent_name, catalog_desc, baseline):
            return None
        result = curator.sweep_fleet("baseline", analyzer, self.db, empty_root)
        self.assertEqual(len(result.proposals), 0)
        self.assertEqual(len(result.needs_evidence), 0)

    def test_sweep_db_returns_none_decision_id(self):
        class NullMockDBClient:
            def log_decision(self, *args, **kwargs):
                return None

        def analyzer(agent_name, catalog_desc, baseline):
            if agent_name == "qa":
                return curator.DriftMatch(
                    agent="qa",
                    drift_description="Drift found",
                    sources=["source1", "source2"],
                    rationale="rationale"
                )
            return None

        result = curator.sweep_fleet("baseline", analyzer, NullMockDBClient(), self.root)
        self.assertEqual(len(result.proposals), 1)
        self.assertIsNone(result.proposals[0].decision_id)


class TestApplyProposal(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="curator-apply-")
        import subprocess
        subprocess.run(["git", "init", "-b", "main"], cwd=self.root, check=True)
        subprocess.run(["git", "config", "user.name", "Test User"], cwd=self.root, check=True)
        subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=self.root, check=True)
        
        # Create agents directory and qa agent
        _write_agent(self.root, "qa", "The QA Specialist.")
        
        # Create a dummy AGENTS.md
        agents_dir = os.path.join(self.root, "agents")
        os.makedirs(agents_dir, exist_ok=True)
        with open(os.path.join(self.root, "agents", "AGENTS.md"), "w", encoding="utf-8") as f:
            f.write("# Shared Rules\n- strict TDD is required for all changes.\n- do not use duplicate rules.")
            
        # Initial commit so git checkout -b doesn't fail on empty repo
        with open(os.path.join(self.root, "dummy.txt"), "w") as f:
            f.write("dummy")
        subprocess.run(["git", "add", "."], cwd=self.root, check=True)
        subprocess.run(["git", "commit", "-m", "initial commit"], cwd=self.root, check=True)
        
        self.proposal = curator.Proposal(
            agent="qa",
            drift_description="Implement some new qa check",
            sources=("source1", "source2"),
            rationale="we need this",
            decision_id="123"
        )
        
    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)
        
    def test_apply_proposal_requires_two_sources(self):
        p = curator.Proposal(
            agent="qa",
            drift_description="Implement check",
            sources=("source1",),
            rationale="we need this"
        )
        with self.assertRaisesRegex(ValueError, "evidence regressed"):
            curator.apply_proposal(p, lambda ad: None, self.root)
            
    def test_apply_proposal_requires_valid_single_agent(self):
        p = curator.Proposal(
            agent="invalid_agent",
            drift_description="Implement check",
            sources=("source1", "source2"),
            rationale="we need this"
        )
        with self.assertRaisesRegex(ValueError, "targets multiple or invalid agent"):
            curator.apply_proposal(p, lambda ad: None, self.root)
            
    def test_apply_proposal_guards_against_restated_rules(self):
        p = curator.Proposal(
            agent="qa",
            drift_description="We need strict TDD is required for all changes, which is a rule",
            sources=("source1", "source2"),
            rationale="we need this"
        )
        with self.assertRaisesRegex(ValueError, "restates shared rules"):
            curator.apply_proposal(p, lambda ad: None, self.root)
            
    def test_apply_proposal_executes_branching_and_committing(self):
        class MockCompletedProcess:
            def __init__(self):
                self.stdout = "https://github.com/ortisan/solomon-harness/pull/123\n"
                
        def gh_runner(args):
            return MockCompletedProcess()
            
        def edit_callback(agent_dir):
            skill_dir = os.path.join(agent_dir, "skills")
            os.makedirs(skill_dir, exist_ok=True)
            with open(os.path.join(skill_dir, "new_skill.md"), "w", encoding="utf-8") as f:
                f.write("New skill content")
                
        pr_url = curator.apply_proposal(self.proposal, edit_callback, self.root, gh_runner=gh_runner)
        self.assertEqual(pr_url, "https://github.com/ortisan/solomon-harness/pull/123")
        
        # Verify git branch exists
        import subprocess
        proc = subprocess.run(["git", "branch", "--show-current"], cwd=self.root, capture_output=True, text=True, check=True)
        self.assertTrue(proc.stdout.strip().startswith("feature/implement-some-new-qa-check"))


class TestBrokerAcquisition(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = self.tmp.name
        
        # Init main project git repo
        subprocess.run(["git", "init", "-b", "main"], cwd=self.root, check=True)
        subprocess.run(["git", "config", "user.name", "Test User"], cwd=self.root, check=True)
        subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=self.root, check=True)
        
        # Create agents directory and qa agent
        _write_agent(self.root, "qa", "The QA Specialist.")
        
        # Create a dummy AGENTS.md
        agents_dir = os.path.join(self.root, "agents")
        os.makedirs(agents_dir, exist_ok=True)
        with open(os.path.join(self.root, "agents", "AGENTS.md"), "w", encoding="utf-8") as f:
            f.write("# Shared Rules\n- strict TDD is required for all changes.\n- do not use duplicate rules.")
            
        with open(os.path.join(self.root, "dummy.txt"), "w") as f:
            f.write("dummy")
        subprocess.run(["git", "add", "."], cwd=self.root, check=True)
        subprocess.run(["git", "commit", "-m", "initial commit"], cwd=self.root, check=True)
        
        # Set up a mock external source repository
        self.src_tmp = tempfile.TemporaryDirectory()
        self.src_git = self.src_tmp.name
        subprocess.run(["git", "init", "-b", "main"], cwd=self.src_git, check=True)
        subprocess.run(["git", "config", "user.name", "Source Author"], cwd=self.src_git, check=True)
        subprocess.run(["git", "config", "user.email", "src@example.com"], cwd=self.src_git, check=True)
        
        # Commit a standalone skill
        os.makedirs(os.path.join(self.src_git, "skills"), exist_ok=True)
        with open(os.path.join(self.src_git, "skills", "standalone.md"), "w", encoding="utf-8") as f:
            f.write("# Standalone Skill\n\nexamine leverage delve tapestry 😊")
            
        # Commit a packaged skill
        os.makedirs(os.path.join(self.src_git, "packaged"), exist_ok=True)
        with open(os.path.join(self.src_git, "packaged", "SKILL.md"), "w", encoding="utf-8") as f:
            f.write("# Packaged Skill\n\nThis is a packaged skill.")
            
        subprocess.run(["git", "add", "."], cwd=self.src_git, check=True)
        subprocess.run(["git", "commit", "-m", "add skills"], cwd=self.src_git, check=True)
        
        proc = subprocess.run(["git", "rev-parse", "HEAD"], cwd=self.src_git, capture_output=True, text=True, check=True)
        self.pin = proc.stdout.strip()
        
        # Write skill-sources.json
        self.sources_data = {
            "sources": [
                {
                    "name": "mock-source",
                    "type": "git",
                    "url": f"file://{self.src_git}",
                    "pin": self.pin
                },
                {
                    "name": "unpinned-source",
                    "type": "git",
                    "url": f"file://{self.src_git}"
                }
            ]
        }
        with open(os.path.join(self.root, "skill-sources.json"), "w", encoding="utf-8") as f:
            json.dump(self.sources_data, f)
            
    def tearDown(self):
        self.tmp.cleanup()
        self.src_tmp.cleanup()
        
    def test_broker_skill_allowlist_check(self):
        with self.assertRaisesRegex(ValueError, "not in the allowlist"):
            curator.broker_skill(self.root, "unknown-source", "standalone", "qa")
            
    def test_broker_skill_sha_pin_check(self):
        with self.assertRaisesRegex(ValueError, "SHA-pin mandatory"):
            curator.broker_skill(self.root, "unpinned-source", "standalone", "qa")
            
    def test_broker_skill_not_found(self):
        class MockCompletedProcess:
            def __init__(self):
                self.stdout = "https://github.com/ortisan/solomon-harness/pull/123\n"
        def gh_runner(args):
            return MockCompletedProcess()
            
        with self.assertRaisesRegex(ValueError, "not found in source"):
            curator.broker_skill(self.root, "mock-source", "non_existent_skill", "qa", gh_runner=gh_runner)
            
    def test_broker_skill_oversized_standalone(self):
        # Commit an oversized standalone skill
        with open(os.path.join(self.src_git, "skills", "oversized.md"), "w", encoding="utf-8") as f:
            f.write("# Oversized Skill\n" + ("x" * 300000))
        subprocess.run(["git", "add", "."], cwd=self.src_git, check=True)
        subprocess.run(["git", "commit", "-m", "add oversized"], cwd=self.src_git, check=True)
        proc = subprocess.run(["git", "rev-parse", "HEAD"], cwd=self.src_git, capture_output=True, text=True, check=True)
        new_pin = proc.stdout.strip()
        
        self.sources_data["sources"][0]["pin"] = new_pin
        with open(os.path.join(self.root, "skill-sources.json"), "w", encoding="utf-8") as f:
            json.dump(self.sources_data, f)
            
        with self.assertRaisesRegex(ValueError, "exceeds the 256 KiB cap"):
            curator.broker_skill(self.root, "mock-source", "oversized", "qa")
            
    def test_broker_skill_packaged_executable_quarantine(self):
        # Create scripts dir in packaged skill
        os.makedirs(os.path.join(self.src_git, "packaged", "scripts"), exist_ok=True)
        with open(os.path.join(self.src_git, "packaged", "scripts", "run.sh"), "w", encoding="utf-8") as f:
            f.write("echo bad")
        subprocess.run(["git", "add", "."], cwd=self.src_git, check=True)
        subprocess.run(["git", "commit", "-m", "add script"], cwd=self.src_git, check=True)
        proc = subprocess.run(["git", "rev-parse", "HEAD"], cwd=self.src_git, capture_output=True, text=True, check=True)
        new_pin = proc.stdout.strip()
        
        self.sources_data["sources"][0]["pin"] = new_pin
        with open(os.path.join(self.root, "skill-sources.json"), "w", encoding="utf-8") as f:
            json.dump(self.sources_data, f)
            
        with self.assertRaisesRegex(ValueError, "Security risk: skill contains scripts/executables"):
            curator.broker_skill(self.root, "mock-source", "packaged", "qa")
            
        quarantine_path = os.path.join(self.root, ".solomon", "quarantine", "packaged")
        self.assertTrue(os.path.isdir(quarantine_path))
        self.assertTrue(os.path.isfile(os.path.join(quarantine_path, "scripts", "run.sh")))
        
    def test_broker_skill_successful_adapt_and_install(self):
        class MockCompletedProcess:
            def __init__(self):
                self.stdout = "https://github.com/ortisan/solomon-harness/pull/123\n"
        
        gh_args = []
        def gh_runner(args):
            gh_args.append(args)
            return MockCompletedProcess()
            
        pr_url = curator.broker_skill(self.root, "mock-source", "standalone", "qa", gh_runner=gh_runner)
        self.assertEqual(pr_url, "https://github.com/ortisan/solomon-harness/pull/123")
        
        self.assertTrue(any("--reviewer" in args and "security" in args for args in gh_args))
        
        import subprocess
        proc = subprocess.run(["git", "branch", "--show-current"], cwd=self.root, capture_output=True, text=True, check=True)
        branch = proc.stdout.strip()
        self.assertTrue(branch.startswith("feature/adapt-skill-standalone-from-mock-source"))
        
        installed_path = os.path.join(self.root, "agents", "qa", "skills", "standalone.md")
        self.assertTrue(os.path.isfile(installed_path))
        with open(installed_path, "r", encoding="utf-8") as f:
            content = f.read()
            
        self.assertNotIn("😊", content)
        self.assertNotIn("leverage", content)
        self.assertNotIn("delve", content)
        self.assertIn("use", content)
        self.assertIn("examine", content)
        self.assertIn("## Common pitfalls", content)
        self.assertIn("## Definition of done", content)


if __name__ == "__main__":
    unittest.main()

