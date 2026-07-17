import hashlib
import os
import shutil
import tempfile
import unittest

from solomon_harness import capability_router as cr


def _write_agent(root, name, description):
    agent_dir = os.path.join(root, "agents", name)
    role_dir = os.path.join(agent_dir, "agents")
    os.makedirs(role_dir)
    os.makedirs(os.path.join(agent_dir, "skills"))
    with open(os.path.join(agent_dir, "persona.md"), "w", encoding="utf-8") as f:
        f.write(f"# {name} Persona\n")
    with open(os.path.join(role_dir, f"{name}.md"), "w", encoding="utf-8") as f:
        f.write(f"# {name}\n\n{description}\n")


def _tree_digest(path):
    """Stable sha256 over every file path + content under ``path`` (read-only proof)."""
    h = hashlib.sha256()
    for dirpath, dirnames, filenames in os.walk(path):
        dirnames.sort()
        for name in sorted(filenames):
            full = os.path.join(dirpath, name)
            h.update(os.path.relpath(full, path).encode())
            with open(full, "rb") as f:
                h.update(f.read())
    return h.hexdigest()


class _StubMatcher:
    """A deterministic matcher: returns the Match it was constructed with, and records
    that it was the only match path invoked (no network/model in the core)."""

    def __init__(self, match):
        self.match = match
        self.calls = 0

    def __call__(self, demand, catalog):
        self.calls += 1
        return self.match


class CapabilityRouterTestBase(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="cap-router-")
        _write_agent(self.root, "qa", "The QA Specialist owns integration testing and UAT.")
        _write_agent(self.root, "security", "The Security Specialist owns STRIDE and SAST.")
        _write_agent(self.root, "software_engineer", "The Software Engineer implements features with TDD.")
        self.agents_dir = os.path.join(self.root, "agents")

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)


class TestRoute(CapabilityRouterTestBase):
    def test_routes_to_a_capable_agent_with_rationale_and_no_mutation(self):
        before = _tree_digest(self.agents_dir)
        matcher = _StubMatcher(cr.Match(agent="qa", rationale="qa owns integration testing"))
        verdict = cr.route("write integration tests for the memory client", matcher, self.root)
        self.assertEqual(verdict.kind, "route")
        self.assertEqual(verdict.agent, "qa")
        self.assertEqual(verdict.rationale, "qa owns integration testing")
        self.assertEqual(verdict.alternatives, ())
        self.assertEqual(matcher.calls, 1)
        self.assertEqual(_tree_digest(self.agents_dir), before)

    def test_ambiguous_demand_surfaces_ranked_alternatives(self):
        matcher = _StubMatcher(
            cr.Match(agent="qa", rationale="qa is the best fit", alternatives=["software_engineer"])
        )
        verdict = cr.route("add a regression test and fix the failing assertion", matcher, self.root)
        self.assertEqual(verdict.kind, "route")
        self.assertEqual(verdict.agent, "qa")
        self.assertEqual(verdict.alternatives, ("software_engineer",))

    def test_rationale_collapses_to_a_single_line(self):
        matcher = _StubMatcher(cr.Match(agent="qa", rationale="line one\nline two"))
        verdict = cr.route("test something", matcher, self.root)
        self.assertEqual(verdict.rationale, "line one")

    def test_route_to_unknown_agent_fails_closed(self):
        matcher = _StubMatcher(cr.Match(agent="ghost", rationale="nope"))
        with self.assertRaises(cr.MatcherContractError):
            cr.route("do a thing", matcher, self.root)

    def test_whitespace_only_rationale_does_not_crash(self):
        matcher = _StubMatcher(cr.Match(agent="qa", rationale="\n   "))
        verdict = cr.route("test something", matcher, self.root)
        self.assertEqual(verdict.kind, "route")
        self.assertEqual(verdict.rationale, "")

    def test_alternatives_strip_unknown_and_self(self):
        matcher = _StubMatcher(
            cr.Match(agent="qa", rationale="r", alternatives=["ghost", "qa", "security"])
        )
        verdict = cr.route("do a thing", matcher, self.root)
        self.assertEqual(verdict.alternatives, ("security",))

    def test_alternatives_preserves_order(self):
        matcher = _StubMatcher(
            cr.Match(agent="qa", rationale="r", alternatives=["security", "software_engineer"])
        )
        verdict = cr.route("do a thing", matcher, self.root)
        self.assertEqual(verdict.alternatives, ("security", "software_engineer"))
        
        matcher_rev = _StubMatcher(
            cr.Match(agent="qa", rationale="r", alternatives=["software_engineer", "security"])
        )
        verdict_rev = cr.route("do a thing", matcher_rev, self.root)
        self.assertEqual(verdict_rev.alternatives, ("software_engineer", "security"))



class TestCatalog(CapabilityRouterTestBase):
    def test_load_catalog_returns_sorted_agents_with_descriptions(self):
        catalog = cr.load_catalog(self.root)
        self.assertEqual([a.name for a in catalog], ["qa", "security", "software_engineer"])
        by_name = {a.name: a.description for a in catalog}
        self.assertEqual(by_name["qa"], "The QA Specialist owns integration testing and UAT.")
        self.assertTrue(by_name["security"].startswith("The Security Specialist"))

    def test_role_file_with_only_a_heading_has_empty_description(self):
        agent_dir = os.path.join(self.root, "agents", "blankrole")
        role_dir = os.path.join(agent_dir, "agents")
        os.makedirs(role_dir)
        os.makedirs(os.path.join(agent_dir, "skills"))
        with open(os.path.join(agent_dir, "persona.md"), "w", encoding="utf-8") as f:
            f.write("# Blank Role Persona\n")
        with open(os.path.join(role_dir, "blankrole.md"), "w", encoding="utf-8") as f:
            f.write("# blankrole\n")
        catalog = cr.load_catalog(self.root)
        by_name = {a.name: a.description for a in catalog}
        self.assertIn("blankrole", by_name)
        self.assertEqual(by_name["blankrole"], "")

    def test_role_file_with_giant_line_is_read_capped(self):
        agent_dir = os.path.join(self.root, "agents", "giantline")
        role_dir = os.path.join(agent_dir, "agents")
        os.makedirs(role_dir)
        os.makedirs(os.path.join(agent_dir, "skills"))
        with open(os.path.join(agent_dir, "persona.md"), "w", encoding="utf-8") as f:
            f.write("# Giant Line Persona\n")
        giant_desc = "A" * 20000
        with open(os.path.join(role_dir, "giantline.md"), "w", encoding="utf-8") as f:
            f.write(f"# giantline\n\n{giant_desc}\n")
        catalog = cr.load_catalog(self.root)
        by_name = {a.name: a.description for a in catalog}
        self.assertIn("giantline", by_name)
        # It should cap at 8192 bytes/chars
        self.assertEqual(len(by_name["giantline"]), 8192)

    def test_symlink_role_file_rejected(self):
        agent_dir = os.path.join(self.root, "agents", "symlinked_agent")
        role_dir = os.path.join(agent_dir, "agents")
        os.makedirs(role_dir)
        os.makedirs(os.path.join(agent_dir, "skills"))
        with open(os.path.join(agent_dir, "persona.md"), "w", encoding="utf-8") as f:
            f.write("# Symlinked Agent Persona\n")
        target_file = os.path.join(self.root, "target.md")
        with open(target_file, "w", encoding="utf-8") as f:
            f.write("# symlinked_agent\n\nsome description\n")
        symlink_file = os.path.join(role_dir, "symlinked_agent.md")
        os.symlink(target_file, symlink_file)
        with self.assertRaises(cr.CatalogError):
            cr.load_catalog(self.root)

    def test_path_confinement_violation_rejected(self):
        agent_dir = os.path.join(self.root, "agents", "evil_agent")
        role_dir = os.path.join(agent_dir, "agents")
        os.makedirs(role_dir)
        os.makedirs(os.path.join(agent_dir, "skills"))
        with open(os.path.join(agent_dir, "persona.md"), "w", encoding="utf-8") as f:
            f.write("# Evil Agent Persona\n")
        outside_dir = tempfile.mkdtemp(prefix="outside-")
        try:
            outside_role = os.path.join(outside_dir, "evil_agent.md")
            with open(outside_role, "w", encoding="utf-8") as f:
                f.write("# evil_agent\n\ndescription\n")
            os.rmdir(role_dir)
            os.symlink(outside_dir, role_dir)
            with self.assertRaises(cr.CatalogError):
                cr.load_catalog(self.root)
        finally:
            shutil.rmtree(outside_dir, ignore_errors=True)




class TestGap(CapabilityRouterTestBase):
    def test_missing_skill_on_an_existing_agent_is_an_adapt_gap(self):
        before = _tree_digest(self.agents_dir)
        matcher = _StubMatcher(
            cr.Match(
                missing_capability="sbom-signing-cosign",
                nearest_agent="security",
                rationale="security is closest but lacks cosign signing",
            )
        )
        verdict = cr.route("sign release artifacts and produce a signed SBOM with cosign", matcher, self.root)
        self.assertEqual(verdict.kind, "gap")
        self.assertEqual(verdict.missing_capability, "sbom-signing-cosign")
        self.assertEqual(verdict.nearest_agent, "security")
        self.assertEqual(verdict.suggested_action, cr.ADAPT_SKILL)
        self.assertEqual(_tree_digest(self.agents_dir), before)

    def test_no_agent_fits_is_a_create_gap(self):
        matcher = _StubMatcher(
            cr.Match(missing_capability="figma-plugin-publishing", rationale="no agent covers this")
        )
        verdict = cr.route("build and publish a Figma plugin", matcher, self.root)
        self.assertEqual(verdict.kind, "gap")
        self.assertIsNone(verdict.nearest_agent)
        self.assertEqual(verdict.suggested_action, cr.CREATE_AGENT)

    def test_unknown_nearest_agent_degrades_to_create(self):
        matcher = _StubMatcher(
            cr.Match(missing_capability="x", nearest_agent="ghost", rationale="r")
        )
        verdict = cr.route("do x", matcher, self.root)
        self.assertEqual(verdict.suggested_action, cr.CREATE_AGENT)
        self.assertIsNone(verdict.nearest_agent)

    def test_gap_without_missing_capability_is_rejected(self):
        matcher = _StubMatcher(cr.Match())
        with self.assertRaises(ValueError):
            cr.route("something", matcher, self.root)


class TestInvariants(CapabilityRouterTestBase):
    def test_deterministic_byte_identical_on_rerun(self):
        matcher = _StubMatcher(cr.Match(agent="qa", rationale="r", alternatives=["security"]))
        v1 = cr.route("d", matcher, self.root)
        v2 = cr.route("d", _StubMatcher(cr.Match(agent="qa", rationale="r", alternatives=["security"])), self.root)
        self.assertEqual(v1, v2)

    def test_empty_catalog_fails_closed(self):
        empty = tempfile.mkdtemp(prefix="cap-empty-")
        try:
            with self.assertRaises(cr.CatalogError):
                cr.route("anything", _StubMatcher(cr.Match(agent="qa")), empty)
        finally:
            shutil.rmtree(empty, ignore_errors=True)

    def test_blank_demand_rejected(self):
        with self.assertRaises(ValueError):
            cr.route("   ", _StubMatcher(cr.Match(agent="qa")), self.root)

    def test_catalog_is_loaded_read_only(self):
        before = _tree_digest(self.agents_dir)
        cr.load_catalog(self.root)
        self.assertEqual(_tree_digest(self.agents_dir), before)

    def test_capability_router_is_isolated_and_read_only(self):
        import ast
        path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "solomon_harness", "capability_router.py"))
        with open(path, "r", encoding="utf-8") as f:
            content = f.read()
            tree = ast.parse(content)
        allowed_roots = {"os", "dataclasses", "typing", "solomon_harness", "sys", "Union", "List", "Optional", "Callable", "Tuple"}
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    root = alias.name.split(".")[0]
                    self.assertIn(root, allowed_roots, f"Import of module '{alias.name}' is forbidden in capability_router")
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    root = node.module.split(".")[0]
                    self.assertIn(root, allowed_roots, f"Import from module '{node.module}' is forbidden in capability_router")
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                if isinstance(node.func, ast.Name) and node.func.id == "open":
                    if len(node.args) >= 2:
                        mode_node = node.args[1]
                        if isinstance(mode_node, ast.Constant):
                            mode = mode_node.value
                            self.assertNotIn(mode, {"w", "wb", "a", "ab", "w+", "wb+", "a+", "ab+"}, f"Opening file with mode '{mode}' is forbidden")
                    for kw in node.keywords:
                        if kw.arg == "mode" and isinstance(kw.value, ast.Constant):
                            mode = kw.value.value
                            self.assertNotIn(mode, {"w", "wb", "a", "ab", "w+", "wb+", "a+", "ab+"}, f"Opening file with mode '{mode}' is forbidden")
                if isinstance(node.func, ast.Attribute) and node.func.attr == "write":
                    self.fail("Calling .write() is forbidden in capability_router")



if __name__ == "__main__":
    unittest.main()
