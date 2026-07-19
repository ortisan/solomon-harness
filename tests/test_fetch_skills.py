import contextlib
import io
import os
import shutil
import tempfile
import unittest
from types import SimpleNamespace
from unittest import mock

WORKSPACE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _load_module():
    import solomon_harness.skills as skills
    return skills


class TestFetchSkills(unittest.TestCase):
    def setUp(self):
        self.mod = _load_module()
        self.tmp = tempfile.TemporaryDirectory()
        self.root = self.tmp.name

    def tearDown(self):
        self.tmp.cleanup()

    def test_discover_finds_skill_md_folders_and_skills_dir_files(self):
        os.makedirs(os.path.join(self.root, "cool-skill"))
        with open(os.path.join(self.root, "cool-skill", "SKILL.md"), "w", encoding="utf-8") as f:
            f.write("# Cool")
        os.makedirs(os.path.join(self.root, "pkg", "skills"))
        with open(os.path.join(self.root, "pkg", "skills", "oauth2.md"), "w", encoding="utf-8") as f:
            f.write("# OAuth2")

        found = self.mod.discover_skill_files(self.root)
        self.assertIn("cool-skill", found)
        self.assertIn("oauth2", found)

    def test_discover_ignores_git_dir(self):
        os.makedirs(os.path.join(self.root, ".git", "skills"))
        with open(os.path.join(self.root, ".git", "skills", "x.md"), "w", encoding="utf-8") as f:
            f.write("# x")
        self.assertNotIn("x", self.mod.discover_skill_files(self.root))

    def test_discover_is_deterministic_on_duplicate_stems(self):
        # Two different paths map to the same stem "dup".
        for top in ("b-dir", "a-dir"):
            os.makedirs(os.path.join(self.root, top, "skills"))
            with open(os.path.join(self.root, top, "skills", "dup.md"), "w", encoding="utf-8") as f:
                f.write(f"# {top}")

        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr):
            first = self.mod.discover_skill_files(self.root)
        second = self.mod.discover_skill_files(self.root)

        # Sorted traversal makes "a-dir" win deterministically across runs.
        self.assertEqual(first, second)
        self.assertEqual(first["dup"], os.path.join(self.root, "a-dir", "skills", "dup.md"))
        warning = stderr.getvalue()
        self.assertIn("dup", warning)
        self.assertIn(os.path.join("a-dir", "skills", "dup.md"), warning)
        self.assertIn(os.path.join("b-dir", "skills", "dup.md"), warning)

    def test_install_skill_md_folder_copies_siblings(self):
        pkg = os.path.join(self.root, "packaged-skill")
        os.makedirs(os.path.join(pkg, "assets"))
        with open(os.path.join(pkg, "SKILL.md"), "w", encoding="utf-8") as f:
            f.write("# Packaged")
        with open(os.path.join(pkg, "helper.py"), "w", encoding="utf-8") as f:
            f.write("print('hi')\n")
        with open(os.path.join(pkg, "assets", "data.txt"), "w", encoding="utf-8") as f:
            f.write("payload")

        skills_dir = os.path.join(self.root, "agents", "qa", "skills")
        target = self.mod.install_skill(os.path.join(pkg, "SKILL.md"), skills_dir, "packaged-skill")

        self.assertTrue(os.path.isdir(target))
        self.assertTrue(os.path.isfile(os.path.join(target, "SKILL.md")))
        self.assertTrue(os.path.isfile(os.path.join(target, "helper.py")))
        self.assertTrue(os.path.isfile(os.path.join(target, "assets", "data.txt")))

    def test_install_skill_copies_into_agent_dir(self):
        src = os.path.join(self.root, "src.md")
        with open(src, "w", encoding="utf-8") as f:
            f.write("# Imported skill")
        skills_dir = os.path.join(self.root, "agents", "qa", "skills")
        target = self.mod.install_skill(src, skills_dir, "social-login")
        self.assertTrue(os.path.isfile(target))
        self.assertTrue(target.endswith(os.path.join("skills", "social-login.md")))
        with open(target, "r", encoding="utf-8") as f:
            self.assertEqual(f.read(), "# Imported skill")

    def test_install_skill_rejects_symlinks_in_a_packaged_skill(self):
        package = os.path.join(self.root, "packaged-skill")
        outside = os.path.join(self.root, "outside.md")
        os.makedirs(package)
        with open(os.path.join(package, "SKILL.md"), "w", encoding="utf-8") as f:
            f.write("# Packaged\n")
        with open(outside, "w", encoding="utf-8") as f:
            f.write("outside content")
        os.symlink(outside, os.path.join(package, "leak.md"))
        skills_dir = os.path.join(self.root, "agents", "qa", "skills")

        with self.assertRaisesRegex(ValueError, "Symlinks"):
            self.mod.install_skill(
                os.path.join(package, "SKILL.md"),
                skills_dir,
                "packaged-skill",
                workspace_root=self.root,
            )

        self.assertFalse(os.path.exists(os.path.join(skills_dir, "packaged-skill")))

    def test_load_sources_reads_config(self):
        sources = self.mod.load_sources(WORKSPACE)
        self.assertIn("anthropic-skills", sources)
        self.assertIn("url", sources["anthropic-skills"])

    def test_load_sources_prefers_the_canonical_consumer_catalog(self):
        source_path = os.path.join(
            self.root, ".agents", "solomon", "skill-sources.json"
        )
        os.makedirs(os.path.dirname(source_path), exist_ok=True)
        with open(source_path, "w", encoding="utf-8") as f:
            f.write(
                '{"sources":[{"name":"canonical","url":"file:///skills"}]}'
            )
        with open(os.path.join(self.root, "skill-sources.json"), "w", encoding="utf-8") as f:
            f.write('{"sources":[{"name":"legacy","url":"file:///legacy"}]}')

        sources = self.mod.load_sources(self.root)

        self.assertEqual(set(sources), {"canonical"})

    def test_workspace_root_resolves_from_inside_the_installed_core(self):
        nested = os.path.join(
            self.root,
            ".agents",
            "solomon",
            "solomon_harness",
            "nested",
        )
        os.makedirs(nested)

        self.assertEqual(
            self.mod.get_workspace_root(nested), os.path.abspath(self.root)
        )

    def test_add_installs_canonically_and_reconciles_the_manifest_transaction(self):
        core = os.path.join(self.root, ".agents", "solomon")
        agent_dir = os.path.join(core, "agents", "qa")
        os.makedirs(os.path.join(agent_dir, "agents"), exist_ok=True)
        with open(
            os.path.join(agent_dir, "agents", "qa.md"), "w", encoding="utf-8"
        ) as f:
            f.write("# QA Profile\n")
        with open(os.path.join(core, "skill-sources.json"), "w", encoding="utf-8") as f:
            f.write(
                '{"sources":[{"name":"local","url":"file:///skills"}]}'
            )
        with open(os.path.join(core, "manifest.json"), "w", encoding="utf-8") as f:
            f.write("{}\n")

        def fake_clone(_source, destination):
            skills_dir = os.path.join(destination, "skills")
            os.makedirs(skills_dir)
            with open(
                os.path.join(skills_dir, "contract-check.md"),
                "w",
                encoding="utf-8",
            ) as f:
                f.write("# Contract check\n")

        result = SimpleNamespace(changed=True, conflicts=(), managed_paths=())
        with (
            mock.patch.object(self.mod, "_clone", side_effect=fake_clone),
            mock.patch(
                "solomon_harness.install_layout.compile_project_adapters",
                return_value=result,
            ) as compile_project,
            mock.patch(
                "solomon_harness.host_adapters.compile_adapters",
                return_value=result,
            ) as compile_,
        ):
            exit_code = self.mod.cmd_add(
                self.root, "local", "contract-check", "qa"
            )

        self.assertEqual(exit_code, 0)
        self.assertTrue(
            os.path.isfile(
                os.path.join(agent_dir, "skills", "contract-check.md")
            )
        )
        self.assertFalse(os.path.exists(os.path.join(self.root, "agents")))
        compile_project.assert_called_once_with(self.root)
        compile_.assert_not_called()

    def test_add_rejects_a_symlinked_canonical_agent_catalog(self):
        core = os.path.join(self.root, ".agents", "solomon")
        outside = tempfile.mkdtemp(prefix="skills-outside-")
        self.addCleanup(shutil.rmtree, outside, True)
        os.makedirs(core)
        os.makedirs(os.path.join(outside, "qa"))
        os.symlink(outside, os.path.join(core, "agents"))
        with open(os.path.join(core, "skill-sources.json"), "w", encoding="utf-8") as f:
            f.write('{"sources":[{"name":"local","url":"file:///skills"}]}')

        with mock.patch.object(self.mod, "_clone") as clone:
            exit_code = self.mod.cmd_add(self.root, "local", "contract-check", "qa")

        self.assertEqual(exit_code, 1)
        clone.assert_not_called()
        self.assertEqual(os.listdir(os.path.join(outside, "qa")), [])

    def test_add_does_not_execute_a_symlinked_document_skills_script(self):
        core = os.path.join(self.root, ".agents", "solomon")
        agent_dir = os.path.join(core, "agents", "qa")
        os.makedirs(agent_dir)
        with open(
            os.path.join(core, "skill-sources.json"), "w", encoding="utf-8"
        ) as f:
            f.write(
                '{"sources":[{"name":"local","url":"file:///skills"}]}'
            )
        scripts = os.path.join(core, "scripts")
        os.makedirs(scripts)
        outside = os.path.join(self.root, "outside-document-skills.py")
        with open(outside, "w", encoding="utf-8") as f:
            f.write("raise RuntimeError('must not execute')\n")
        os.symlink(outside, os.path.join(scripts, "document-skills.py"))

        def fake_clone(_source, destination):
            source_skills = os.path.join(destination, "skills")
            os.makedirs(source_skills)
            with open(
                os.path.join(source_skills, "contract-check.md"),
                "w",
                encoding="utf-8",
            ) as f:
                f.write("# Contract check\n")

        with (
            mock.patch.object(
                self.mod, "_clone", side_effect=fake_clone
            ) as clone,
            mock.patch.object(self.mod.subprocess, "run") as run,
            mock.patch.object(
                self.mod,
                "_reconcile_host_adapters",
                return_value=SimpleNamespace(conflicts=()),
            ),
            contextlib.redirect_stderr(io.StringIO()) as stderr,
        ):
            exit_code = self.mod.cmd_add(
                self.root, "local", "contract-check", "qa"
            )

        self.assertEqual(exit_code, 1)
        self.assertIn("symlink", stderr.getvalue())
        clone.assert_not_called()
        run.assert_not_called()
        self.assertFalse(
            os.path.exists(os.path.join(agent_dir, "skills", "contract-check.md"))
        )


if __name__ == "__main__":
    unittest.main()
