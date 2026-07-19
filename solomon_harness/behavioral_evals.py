"""Offline behavioral evaluation contracts for generated subagents.

The active host owns every model invocation. This module only loads versioned
data, prepares local scratch fixtures, scores recorded evidence, and compares
normalized results.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Tuple


SUPPORTED_SCHEMA_VERSION = 1


def canonical_json(value: object) -> str:
    """Return the stable JSON representation used by digests and artifacts."""
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


@dataclass(frozen=True)
class EvaluationBudget:
    max_prompt_bytes: int
    max_files: int
    max_file_bytes: int
    max_total_bytes: int
    max_duration_seconds: float
    max_input_tokens: int
    max_output_tokens: int
    max_reported_cost_usd: float

    def to_data(self) -> Dict[str, object]:
        return {
            "max_prompt_bytes": self.max_prompt_bytes,
            "max_files": self.max_files,
            "max_file_bytes": self.max_file_bytes,
            "max_total_bytes": self.max_total_bytes,
            "max_duration_seconds": self.max_duration_seconds,
            "max_input_tokens": self.max_input_tokens,
            "max_output_tokens": self.max_output_tokens,
            "max_reported_cost_usd": self.max_reported_cost_usd,
        }


@dataclass(frozen=True)
class EffectivePolicy:
    tools: Tuple[str, ...]
    network_allowed: bool

    def to_data(self) -> Dict[str, object]:
        return {
            "tools": list(self.tools),
            "network_allowed": self.network_allowed,
        }


@dataclass(frozen=True)
class EvaluationArm:
    arm_id: str
    policy: EffectivePolicy

    def to_data(self) -> Dict[str, object]:
        return {"id": self.arm_id, "policy": self.policy.to_data()}


@dataclass(frozen=True)
class StructuralAssertions:
    required_files: Tuple[str, ...]
    forbidden_files: Tuple[str, ...]
    required_actions: Tuple[str, ...]
    forbidden_actions: Tuple[str, ...]
    expected_exit_code: int

    def to_data(self) -> Dict[str, object]:
        return {
            "required_files": list(self.required_files),
            "forbidden_files": list(self.forbidden_files),
            "required_actions": list(self.required_actions),
            "forbidden_actions": list(self.forbidden_actions),
            "expected_exit_code": self.expected_exit_code,
        }


@dataclass(frozen=True)
class EvaluationCase:
    case_id: str
    version: str
    role: str
    fixture_path: str
    prompt: str
    assertions: StructuralAssertions

    def to_data(self) -> Dict[str, object]:
        return {
            "id": self.case_id,
            "version": self.version,
            "role": self.role,
            "fixture_path": self.fixture_path,
            "prompt": self.prompt,
            "assertions": self.assertions.to_data(),
        }


@dataclass(frozen=True)
class EvaluationManifest:
    schema_version: int
    golden_set_version: str
    repetitions: int
    budget: EvaluationBudget
    arms: Tuple[EvaluationArm, ...]
    cases: Tuple[EvaluationCase, ...]
    source_root: Path

    def to_data(self) -> Dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "golden_set_version": self.golden_set_version,
            "repetitions": self.repetitions,
            "budget": self.budget.to_data(),
            "arms": [arm.to_data() for arm in self.arms],
            "cases": [case.to_data() for case in self.cases],
        }


def _load_policy(data: Dict[str, Any]) -> EffectivePolicy:
    return EffectivePolicy(
        tools=tuple(data["tools"]),
        network_allowed=data["network_allowed"],
    )


def _load_assertions(data: Dict[str, Any]) -> StructuralAssertions:
    return StructuralAssertions(
        required_files=tuple(data["required_files"]),
        forbidden_files=tuple(data["forbidden_files"]),
        required_actions=tuple(data["required_actions"]),
        forbidden_actions=tuple(data["forbidden_actions"]),
        expected_exit_code=data["expected_exit_code"],
    )


def load_manifest(path: Path) -> EvaluationManifest:
    """Load a behavioral manifest from a local JSON file."""
    with path.open("r", encoding="utf-8") as stream:
        data = json.load(stream)

    budget_data = data["budget"]
    budget = EvaluationBudget(
        max_prompt_bytes=budget_data["max_prompt_bytes"],
        max_files=budget_data["max_files"],
        max_file_bytes=budget_data["max_file_bytes"],
        max_total_bytes=budget_data["max_total_bytes"],
        max_duration_seconds=budget_data["max_duration_seconds"],
        max_input_tokens=budget_data["max_input_tokens"],
        max_output_tokens=budget_data["max_output_tokens"],
        max_reported_cost_usd=budget_data["max_reported_cost_usd"],
    )
    arms = tuple(
        EvaluationArm(arm_id=arm["id"], policy=_load_policy(arm["policy"]))
        for arm in data["arms"]
    )
    cases = tuple(
        EvaluationCase(
            case_id=case["id"],
            version=case["version"],
            role=case["role"],
            fixture_path=case["fixture_path"],
            prompt=case["prompt"],
            assertions=_load_assertions(case["assertions"]),
        )
        for case in data["cases"]
    )
    return EvaluationManifest(
        schema_version=data["schema_version"],
        golden_set_version=data["golden_set_version"],
        repetitions=data["repetitions"],
        budget=budget,
        arms=arms,
        cases=cases,
        source_root=path.parent.resolve(),
    )
