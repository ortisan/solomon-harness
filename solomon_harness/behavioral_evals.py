"""Offline behavioral evaluation contracts for generated subagents.

The active host owns every model invocation. This module only loads versioned
data, prepares local scratch fixtures, scores recorded evidence, and compares
normalized results.
"""

from __future__ import annotations

import json
import os
import re
import stat
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Tuple

from solomon_harness.secure_paths import (
    UnsafePathError,
    open_root_directory,
    read_regular_at,
    stat_at,
)


SUPPORTED_SCHEMA_VERSION = 1
MAX_MANIFEST_BYTES = 1_000_000
MAX_CASES = 64
MAX_PATH_BYTES = 512
MAX_PATH_COMPONENT_BYTES = 128
MAX_PATH_DEPTH = 16
MAX_LIST_ITEMS = 64
MAX_STRING_BYTES = 16_384
HARD_BUDGET_LIMITS = {
    "max_prompt_bytes": 65_536,
    "max_files": 256,
    "max_file_bytes": 1_048_576,
    "max_total_bytes": 16_777_216,
    "max_duration_ms": 7_200_000,
    "max_input_tokens": 2_000_000,
    "max_output_tokens": 1_000_000,
    "max_reported_cost_microusd": 1_000_000_000,
}
ROOT_FIELDS = {
    "schema_version",
    "golden_set_version",
    "repetitions",
    "budget",
    "arms",
    "cases",
}
ARM_FIELDS = {"id", "policy"}
POLICY_FIELDS = {"tools", "network_allowed"}
CASE_FIELDS = {"id", "version", "role", "fixture_path", "prompt", "assertions"}
ASSERTION_FIELDS = {
    "required_files",
    "forbidden_files",
    "required_actions",
    "forbidden_actions",
    "expected_exit_code",
}
ROLES = {"planning", "implementation", "review"}
SCENARIOS = {"happy", "boundary", "failure"}
SLUG_PATTERN = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
TOKEN_PATTERN = re.compile(r"^[A-Za-z][A-Za-z0-9_-]*$")
ACTION_PATTERN = re.compile(r"^[a-z][a-z0-9_]*$")


class EvaluationError(ValueError):
    """Closed validation failure safe to expose through the local adapter."""

    def __init__(self, code: str, field: str) -> None:
        self.code = code
        self.field = field
        super().__init__(f"{code}: {field}")


def canonical_json(value: object) -> str:
    """Return the stable JSON representation used by digests and artifacts."""
    return json.dumps(
        value,
        allow_nan=False,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )


@dataclass(frozen=True)
class EvaluationBudget:
    max_prompt_bytes: int
    max_files: int
    max_file_bytes: int
    max_total_bytes: int
    max_duration_ms: int
    max_input_tokens: int
    max_output_tokens: int
    max_reported_cost_microusd: int

    def to_data(self) -> Dict[str, object]:
        return {
            "max_prompt_bytes": self.max_prompt_bytes,
            "max_files": self.max_files,
            "max_file_bytes": self.max_file_bytes,
            "max_total_bytes": self.max_total_bytes,
            "max_duration_ms": self.max_duration_ms,
            "max_input_tokens": self.max_input_tokens,
            "max_output_tokens": self.max_output_tokens,
            "max_reported_cost_microusd": self.max_reported_cost_microusd,
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


def _invalid(field: str) -> EvaluationError:
    return EvaluationError("invalid_manifest", field)


def _unique_object(pairs: List[Tuple[str, object]]) -> Dict[str, object]:
    result: Dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise _invalid("json.duplicate_key")
        result[key] = value
    return result


def _reject_constant(_value: str) -> object:
    raise _invalid("json.non_finite_number")


def _bounded_json(path: Path) -> object:
    try:
        root_fd = open_root_directory(os.fspath(path.parent))
    except (FileNotFoundError, OSError, UnsafePathError) as exc:
        raise EvaluationError("unsafe_path", "manifest") from exc
    try:
        try:
            entry = stat_at(root_fd, path.name)
        except (OSError, UnsafePathError) as exc:
            raise EvaluationError("unsafe_path", "manifest") from exc
        if entry is None:
            raise _invalid("manifest")
        if not stat.S_ISREG(entry.st_mode):
            raise EvaluationError("unsafe_path", "manifest")
        if entry.st_size > MAX_MANIFEST_BYTES:
            raise EvaluationError("limit_exceeded", "manifest.bytes")
        try:
            raw = read_regular_at(root_fd, path.name, max_bytes=MAX_MANIFEST_BYTES)
        except (OSError, UnsafePathError) as exc:
            raise EvaluationError("unsafe_path", "manifest") from exc
    finally:
        os.close(root_fd)

    try:
        text = raw.decode("utf-8", errors="strict")
        return json.loads(
            text,
            object_pairs_hook=_unique_object,
            parse_constant=_reject_constant,
        )
    except UnicodeDecodeError as exc:
        raise _invalid("json.encoding") from exc
    except json.JSONDecodeError as exc:
        raise _invalid("json.syntax") from exc


def _closed_object(value: object, fields: set[str], name: str) -> Dict[str, object]:
    if not isinstance(value, dict) or set(value) != fields:
        raise _invalid(f"{name}.fields")
    if not all(isinstance(key, str) for key in value):
        raise _invalid(f"{name}.fields")
    return {key: item for key, item in value.items()}


def _list(value: object, name: str, *, minimum: int = 0, maximum: int = MAX_LIST_ITEMS) -> List[object]:
    if not isinstance(value, list) or not minimum <= len(value) <= maximum:
        raise _invalid(name)
    return list(value)


def _string(value: object, name: str, *, maximum: int = MAX_STRING_BYTES) -> str:
    if not isinstance(value, str) or not value or "\x00" in value:
        raise _invalid(name)
    try:
        size = len(value.encode("utf-8", errors="strict"))
    except UnicodeEncodeError as exc:
        raise _invalid(name) from exc
    if size > maximum:
        raise EvaluationError("limit_exceeded", name)
    return value


def _positive_int(value: object, name: str, *, hard_limit: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise _invalid(name)
    if value > hard_limit:
        raise EvaluationError("limit_exceeded", name)
    return value


def _exit_code(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= 255:
        raise _invalid("case.assertions.expected_exit_code")
    return value


def _safe_relative_path(value: object, name: str) -> str:
    path = _string(value, name, maximum=MAX_PATH_BYTES)
    if path.startswith(("/", "\\")) or "\\" in path or re.match(r"^[A-Za-z]:", path):
        raise EvaluationError("unsafe_path", name)
    parts = path.split("/")
    if len(parts) > MAX_PATH_DEPTH:
        raise EvaluationError("limit_exceeded", name)
    if any(part in {"", ".", ".."} for part in parts):
        raise EvaluationError("unsafe_path", name)
    if any(len(part.encode("utf-8")) > MAX_PATH_COMPONENT_BYTES for part in parts):
        raise EvaluationError("limit_exceeded", name)
    return path


def _unique_strings(
    value: object,
    name: str,
    *,
    paths: bool = False,
    token_pattern: re.Pattern[str] | None = None,
    minimum: int = 0,
) -> Tuple[str, ...]:
    raw = _list(value, name, minimum=minimum)
    strings: List[str] = []
    for item in raw:
        text = _safe_relative_path(item, name) if paths else _string(item, name, maximum=128)
        if token_pattern is not None and token_pattern.fullmatch(text) is None:
            raise _invalid(name)
        strings.append(text)
    if len(set(strings)) != len(strings):
        raise _invalid(f"{name}.duplicate")
    return tuple(strings)


def _load_budget(value: object) -> EvaluationBudget:
    data = _closed_object(value, set(HARD_BUDGET_LIMITS), "budget")
    values = {
        name: _positive_int(data[name], f"budget.{name}", hard_limit=hard_limit)
        for name, hard_limit in HARD_BUDGET_LIMITS.items()
    }
    if values["max_file_bytes"] > values["max_total_bytes"]:
        raise _invalid("budget.file_bytes")
    return EvaluationBudget(**values)


def _load_policy(value: object) -> EffectivePolicy:
    data = _closed_object(value, POLICY_FIELDS, "arm.policy")
    network_allowed = data["network_allowed"]
    if not isinstance(network_allowed, bool):
        raise _invalid("arm.policy.network_allowed")
    return EffectivePolicy(
        tools=_unique_strings(
            data["tools"],
            "arm.policy.tools",
            token_pattern=TOKEN_PATTERN,
            minimum=1,
        ),
        network_allowed=network_allowed,
    )


def _load_arms(value: object) -> Tuple[EvaluationArm, ...]:
    raw = _list(value, "arms", minimum=2, maximum=2)
    arms: List[EvaluationArm] = []
    for item in raw:
        data = _closed_object(item, ARM_FIELDS, "arm")
        arm_id = _string(data["id"], "arm.id", maximum=32)
        arms.append(EvaluationArm(arm_id=arm_id, policy=_load_policy(data["policy"])))
    if tuple(arm.arm_id for arm in arms) != ("baseline", "candidate"):
        raise _invalid("arms.ids")
    return tuple(arms)


def _load_assertions(value: object) -> StructuralAssertions:
    data = _closed_object(value, ASSERTION_FIELDS, "case.assertions")
    return StructuralAssertions(
        required_files=_unique_strings(
            data["required_files"], "case.assertions.required_files", paths=True
        ),
        forbidden_files=_unique_strings(
            data["forbidden_files"], "case.assertions.forbidden_files", paths=True
        ),
        required_actions=_unique_strings(
            data["required_actions"],
            "case.assertions.required_actions",
            token_pattern=ACTION_PATTERN,
        ),
        forbidden_actions=_unique_strings(
            data["forbidden_actions"],
            "case.assertions.forbidden_actions",
            token_pattern=ACTION_PATTERN,
        ),
        expected_exit_code=_exit_code(data["expected_exit_code"]),
    )


def _load_cases(value: object, budget: EvaluationBudget) -> Tuple[EvaluationCase, ...]:
    raw = _list(value, "cases", minimum=9, maximum=MAX_CASES)
    cases: List[EvaluationCase] = []
    for item in raw:
        data = _closed_object(item, CASE_FIELDS, "case")
        case_id = _string(data["id"], "case.id", maximum=64)
        if SLUG_PATTERN.fullmatch(case_id) is None:
            raise _invalid("case.id")
        role = _string(data["role"], "case.role", maximum=32)
        if role not in ROLES:
            raise _invalid("case.role")
        prompt = _string(data["prompt"], "case.prompt", maximum=HARD_BUDGET_LIMITS["max_prompt_bytes"])
        if len(prompt.encode("utf-8")) > budget.max_prompt_bytes:
            raise EvaluationError("limit_exceeded", "case.prompt")
        cases.append(
            EvaluationCase(
                case_id=case_id,
                version=_string(data["version"], "case.version", maximum=64),
                role=role,
                fixture_path=_safe_relative_path(data["fixture_path"], "case.fixture_path"),
                prompt=prompt,
                assertions=_load_assertions(data["assertions"]),
            )
        )
    case_ids = [case.case_id for case in cases]
    if len(set(case_ids)) != len(case_ids):
        raise _invalid("cases.duplicate_id")
    covered = {
        (case.role, scenario)
        for case in cases
        for scenario in SCENARIOS
        if case.case_id.endswith(f"-{scenario}")
    }
    if covered != {(role, scenario) for role in ROLES for scenario in SCENARIOS}:
        raise _invalid("cases.role_scenario_coverage")
    return tuple(cases)


def load_manifest(path: Path) -> EvaluationManifest:
    """Load and strictly validate a bounded behavioral manifest."""
    data = _closed_object(_bounded_json(path), ROOT_FIELDS, "manifest")
    schema_version = data["schema_version"]
    if isinstance(schema_version, bool) or not isinstance(schema_version, int):
        raise _invalid("schema_version")
    if schema_version != SUPPORTED_SCHEMA_VERSION:
        raise EvaluationError("unsupported_schema", "schema_version")
    repetitions = _positive_int(data["repetitions"], "repetitions", hard_limit=3)
    if repetitions != 3:
        raise _invalid("repetitions")
    budget = _load_budget(data["budget"])
    arms = _load_arms(data["arms"])
    cases = _load_cases(data["cases"], budget)
    return EvaluationManifest(
        schema_version=schema_version,
        golden_set_version=_string(
            data["golden_set_version"], "golden_set_version", maximum=64
        ),
        repetitions=repetitions,
        budget=budget,
        arms=arms,
        cases=cases,
        source_root=path.parent,
    )
