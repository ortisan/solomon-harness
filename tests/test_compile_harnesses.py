import json
import os
import tempfile
import unittest

from solomon_harness.compiler import compile_harnesses


def _write(path, content):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)


def _read(path):
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


class TestCompileHarnesses(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = self._tmp.name

        self.agents_dir = os.path.join(self.root, "agents")
        self.build_dir = os.path.join(self.root, "build", "agents")
        templates = os.path.join(self.root, "templates", "harness")
        patterns = os.path.join(self.root, "templates", "patterns")

        # Shared rules
        _write(os.path.join(self.agents_dir, "AGENTS.md"), "# Global Rules\nShared project rules.")

        # Harness template (used only to scaffold genuinely missing files)
        _write(os.path.join(templates, "main.py"), "print('entrypoint')")
        _write(
            os.path.join(templates, ".agent", "config.json"),
            json.dumps({"agent_name": "{{AGENT_NAME}}", "timeout_seconds": 30}),
        )

        # Pattern files
        _write(os.path.join(patterns, "architecture", "hexagonal.md"), "# Hexagonal Architecture\nUse ports.")
        _write(os.path.join(patterns, "observability", "opentelemetry.md"), "# OpenTelemetry\nTrace it.")
        _write(os.path.join(patterns, "security", "secure_dev.md"), "# Secure Dev\nValidate input.")

        # Global config selecting all three patterns
        _write(
            os.path.join(self.root, ".agent", "config.json"),
            json.dumps(
                {
                    "architecture_pattern": "hexagonal",
                    "observability_pattern": "opentelemetry",
                    "security_pattern": "secure_dev",
                }
            ),
        )

        # Agent software_engineer: fully hand-authored source (persona + config + profile)
        self.se_profile = os.path.join(self.agents_dir, "software_engineer", "agents", "software_engineer.md")
        self.se_persona = os.path.join(self.agents_dir, "software_engineer", "persona.md")
        self.se_config = os.path.join(self.agents_dir, "software_engineer", ".agent", "config.json")
        _write(self.se_profile, "# Software Engineer\nImplement features.")
        _write(self.se_persona, "# Software Engineer Persona\nHand-authored persona, must survive.")
        _write(self.se_config, json.dumps({"agent_name": "software_engineer", "custom": True}))

        # Agent product_owner: profile only, no persona, no scaffolding yet
        self.po_profile = os.path.join(self.agents_dir, "product_owner", "agents", "product_owner.md")
        _write(self.po_profile, "# Product Owner\nOwn the backlog.")

    def tearDown(self):
        self._tmp.cleanup()

    def _build_path(self, name):
        return os.path.join(self.build_dir, name, f"{name}.md")

    def test_build_artifacts_are_created(self):
        compile_harnesses(self.root)
        self.assertTrue(os.path.isfile(self._build_path("software_engineer")))
        self.assertTrue(os.path.isfile(self._build_path("product_owner")))

    def test_patterns_land_in_build_not_source(self):
        compile_harnesses(self.root)

        se_build = _read(self._build_path("software_engineer"))
        self.assertIn("# Hexagonal Architecture", se_build)
        self.assertIn("# OpenTelemetry", se_build)
        self.assertIn("# Secure Dev", se_build)
        # Composed build also carries the shared rules and the persona.
        self.assertIn("# Global Rules", se_build)
        self.assertIn("Hand-authored persona", se_build)

        # The source profile must remain pattern-free.
        se_source = _read(self.se_profile)
        self.assertNotIn("# Hexagonal Architecture", se_source)
        self.assertNotIn("BEST_PRACTICES_APPENDED_START", se_source)

        # product_owner is not in any pattern set.
        po_build = _read(self._build_path("product_owner"))
        self.assertNotIn("# Hexagonal Architecture", po_build)
        self.assertNotIn("# OpenTelemetry", po_build)
        self.assertNotIn("# Secure Dev", po_build)

    def test_persona_is_not_clobbered(self):
        """Regression test for the critical data-loss bug: recompiling must never
        overwrite a hand-authored persona.md with a generic template."""
        before = _read(self.se_persona)
        compile_harnesses(self.root)
        compile_harnesses(self.root)  # twice, to catch any second-pass clobber
        self.assertEqual(_read(self.se_persona), before)
        self.assertIn("must survive", _read(self.se_persona))

    def test_existing_config_is_not_reset(self):
        before = _read(self.se_config)
        compile_harnesses(self.root)
        after = json.loads(_read(self.se_config))
        self.assertEqual(_read(self.se_config), before)
        self.assertTrue(after.get("custom"))
        self.assertEqual(after.get("agent_name"), "software_engineer")

    def test_missing_scaffolding_is_filled_in(self):
        # product_owner had no main.py or .agent/config.json.
        compile_harnesses(self.root)
        po_main = os.path.join(self.agents_dir, "product_owner", "main.py")
        po_config = os.path.join(self.agents_dir, "product_owner", ".agent", "config.json")
        self.assertTrue(os.path.isfile(po_main))
        self.assertTrue(os.path.isfile(po_config))
        cfg = json.loads(_read(po_config))
        self.assertEqual(cfg.get("agent_name"), "product_owner")

    def test_compile_does_not_modify_existing_source_files(self):
        # Snapshot the hand-authored source files before compiling.
        snapshot = {p: _read(p) for p in (self.se_profile, self.se_persona, self.se_config, self.po_profile)}
        compile_harnesses(self.root)
        for path, content in snapshot.items():
            self.assertEqual(_read(path), content, f"compile modified tracked source file {path}")

    def test_pattern_selection_per_agent(self):
        # observability gets only otel; qa gets arch+sec but not otel.
        _write(os.path.join(self.agents_dir, "observability", "agents", "observability.md"), "# Observability")
        _write(os.path.join(self.agents_dir, "qa", "agents", "qa.md"), "# QA")
        compile_harnesses(self.root)

        obs = _read(self._build_path("observability"))
        self.assertIn("# OpenTelemetry", obs)
        self.assertNotIn("# Hexagonal Architecture", obs)
        self.assertNotIn("# Secure Dev", obs)

        qa = _read(self._build_path("qa"))
        self.assertIn("# Hexagonal Architecture", qa)
        self.assertIn("# Secure Dev", qa)
        self.assertNotIn("# OpenTelemetry", qa)

    def test_patterns_removed_when_config_cleared(self):
        compile_harnesses(self.root)
        self.assertIn("# Hexagonal Architecture", _read(self._build_path("software_engineer")))

        _write(
            os.path.join(self.root, ".agent", "config.json"),
            json.dumps(
                {
                    "architecture_pattern": "none",
                    "observability_pattern": "none",
                    "security_pattern": "none",
                }
            ),
        )
        compile_harnesses(self.root)
        se_build = _read(self._build_path("software_engineer"))
        self.assertNotIn("# Hexagonal Architecture", se_build)
        self.assertNotIn("# OpenTelemetry", se_build)
        self.assertNotIn("# Secure Dev", se_build)

    def test_no_double_append_on_recompile(self):
        compile_harnesses(self.root)
        compile_harnesses(self.root)
        se_build = _read(self._build_path("software_engineer"))
        self.assertEqual(se_build.count("# Hexagonal Architecture"), 1)
        self.assertEqual(se_build.count("# OpenTelemetry"), 1)
        self.assertEqual(se_build.count("# Secure Dev"), 1)

    def test_stray_marker_in_source_is_stripped_from_build(self):
        # A legacy source profile that still contains an appended block must not
        # leak a doubled block into the build.
        _write(
            self.se_profile,
            "# Software Engineer\nImplement features.\n\n"
            "<!-- BEST_PRACTICES_APPENDED_START -->\n\n# Stale Block\nOld text.",
        )
        compile_harnesses(self.root)
        se_build = _read(self._build_path("software_engineer"))
        self.assertNotIn("# Stale Block", se_build)
        self.assertEqual(se_build.count("BEST_PRACTICES_APPENDED_START"), 1)

    def test_path_traversal_pattern_is_rejected(self):
        _write(
            os.path.join(self.root, ".agent", "config.json"),
            json.dumps({"architecture_pattern": "../../../etc/passwd"}),
        )
        with self.assertRaises(SystemExit):
            compile_harnesses(self.root)


if __name__ == "__main__":
    unittest.main()
