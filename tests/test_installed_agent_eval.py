"""Behavioral contract for the host-neutral installed specialist evaluator."""

from __future__ import annotations

import io
import unittest
from pathlib import Path

import pytest

from solomon_harness.evals import build_agent_suite
from solomon_harness.install_layout import install_project
from solomon_harness.layout import HarnessPaths


SOURCE_ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.integration
def test_installed_specialist_passes_the_shared_eval_without_a_model_pin(
    tmp_path: Path,
) -> None:
    install_project(tmp_path, source_root=SOURCE_ROOT)
    installed_agent = HarnessPaths(tmp_path).agents / "qa"
    output = io.StringIO()

    result = unittest.TextTestRunner(stream=output, verbosity=0).run(
        build_agent_suite(str(installed_agent))
    )

    assert result.wasSuccessful(), output.getvalue()
