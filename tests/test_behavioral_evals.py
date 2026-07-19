"""Contract tests for the offline behavioral-evaluation core (#369)."""

from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest

from solomon_harness.behavioral_evals import canonical_json, load_manifest


FIXTURE_ROOT = Path(__file__).parent / "fixtures" / "behavioral_evals"
MANIFEST_PATH = FIXTURE_ROOT / "manifest.json"


def test_manifest_loads_closed_versioned_contract() -> None:
    manifest = load_manifest(MANIFEST_PATH)

    assert manifest.schema_version == 1
    assert manifest.golden_set_version == "2026-07-18.1"
    assert tuple(arm.arm_id for arm in manifest.arms) == ("baseline", "candidate")
    assert manifest.repetitions == 3
    assert len(manifest.cases) == 9
    assert {case.role for case in manifest.cases} == {
        "planning",
        "implementation",
        "review",
    }
    assert canonical_json(manifest.to_data()) == canonical_json(manifest.to_data())
    with pytest.raises(FrozenInstanceError):
        setattr(manifest, "repetitions", 4)
