"""Regression guard for issue #41.

`dev` is a PEP 735 ``[dependency-groups]`` entry in ``pyproject.toml``, not a
``[project.optional-dependencies]`` extra. ``uv sync --extra dev`` therefore
fails with ``error: Extra 'dev' is not defined`` on every CI run, before any
test executes. CI must install the dev group with ``uv sync --group dev``
(or a bare ``uv sync``, which installs the default group). These tests keep the
wrong flag from coming back.
"""

import glob
import os
import unittest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WORKFLOW_DIR = os.path.join(REPO_ROOT, ".github", "workflows")


def _uv_sync_run_lines():
    """Return (file, lineno, text) for every non-comment line that invokes `uv sync`."""
    found = []
    patterns = (os.path.join(WORKFLOW_DIR, "*.yml"), os.path.join(WORKFLOW_DIR, "*.yaml"))
    for pattern in patterns:
        for path in sorted(glob.glob(pattern)):
            with open(path, encoding="utf-8") as fh:
                for lineno, line in enumerate(fh, 1):
                    if "uv sync" not in line:
                        continue
                    if line.lstrip().startswith("#"):  # a comment merely mentioning it
                        continue
                    found.append((os.path.basename(path), lineno, line.strip()))
    return found


class TestCiDevGroupSync(unittest.TestCase):
    def test_workflows_invoke_uv_sync(self):
        self.assertTrue(
            _uv_sync_run_lines(),
            "expected at least one `uv sync` invocation in .github/workflows",
        )

    def test_no_uv_sync_extra_dev(self):
        offenders = [loc for loc in _uv_sync_run_lines() if "--extra dev" in loc[2]]
        self.assertEqual(
            offenders,
            [],
            "`dev` is a [dependency-groups] entry, not an extra; "
            f"use `uv sync --group dev`. Offending lines: {offenders}",
        )

    def test_uv_sync_installs_dev_group(self):
        for fname, lineno, text in _uv_sync_run_lines():
            installs_dev = "--group dev" in text or text.endswith("uv sync")
            self.assertTrue(
                installs_dev,
                f"{fname}:{lineno} must install the dev group "
                f"(`uv sync --group dev` or bare `uv sync`): {text!r}",
            )


if __name__ == "__main__":
    unittest.main()
