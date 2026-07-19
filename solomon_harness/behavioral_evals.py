"""Offline behavioral evaluation contracts for generated subagents.

The active host owns every model invocation. This module only loads versioned
data, prepares local scratch fixtures, scores recorded evidence, and compares
normalized results.
"""

from __future__ import annotations

import argparse
import json
import hashlib
import os
import re
import secrets
import stat
import sys
from collections import Counter
from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path
from typing import Dict, List, Sequence, Tuple

from solomon_harness.secure_paths import (
    UnsafePathError,
    create_regular_at,
    open_directory_at,
    open_root_directory,
    read_regular_at,
    stat_at,
)


SUPPORTED_SCHEMA_VERSION = 1
MAX_MANIFEST_BYTES = 1_000_000
MAX_RECORDINGS_BYTES = 16_777_216
MAX_CASES = 64
MAX_RUNS = MAX_CASES * 6
MAX_AGENT_CONTENT_BYTES = 262_144
MAX_PATH_BYTES = 512
MAX_PATH_COMPONENT_BYTES = 128
MAX_PATH_DEPTH = 16
MAX_LIST_ITEMS = 64
MAX_STRING_BYTES = 16_384
MAX_JSON_DEPTH = 64
MAX_JSON_INTEGER_DIGITS = 19
MAX_SEED_ENTRIES = 4_096
MAX_SEED_DIRECTORIES = 1_024
MAX_PILOT_COPY_BYTES = 256 * 1_024 * 1_024
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
DIGEST_PATTERN = re.compile(r"^sha256:[0-9a-f]{64}$")
RECORDING_FIELDS = {"schema_version", "golden_set_version", "runs", "usage_records"}
RUN_FIELDS = {
    "case_id",
    "case_version",
    "arm",
    "repetition",
    "agent_content",
    "effective_policy",
    "host",
    "model",
    "effort",
    "duration_ms",
    "exit_code",
    "files",
    "actions",
    "containment",
}
HOST_FIELDS = {"name", "version", "provider"}
MODEL_FIELDS = {"name", "version"}
CONTAINMENT_FIELDS = {"scratch_only", "protected_state", "denied_actions"}
PROTECTED_STATE_FIELDS = {"resource", "before_digest", "after_digest"}
PROTECTED_RESOURCES = ("source_checkout", "project_memory", "github")
PROTECTED_ACTIONS = ("write_source", "write_memory", "write_github", "merge", "release")
USAGE_FIELDS = {
    "case_id",
    "arm",
    "repetition",
    "input_tokens",
    "output_tokens",
    "cache_tokens",
    "reported_cost_microusd",
}


class EvaluationError(ValueError):
    """Closed validation failure safe to expose through the local adapter."""

    def __init__(self, code: str, field: str) -> None:
        self.code = code
        self.field = field
        super().__init__(f"{code}: {field}")

    def to_data(self) -> Dict[str, object]:
        return {"error": {"code": self.code, "field": self.field}}


class IncompleteComparisonError(EvaluationError):
    """A case-arm pair does not contain the required repetition matrix."""

    def __init__(
        self,
        case_id: str,
        arm_id: str,
        observed_repetitions: Sequence[int],
        expected_repetition_count: int,
    ) -> None:
        self.case_id = case_id
        self.arm_id = arm_id
        self.observed_repetitions = tuple(sorted(observed_repetitions))
        self.observed_repetition_count = len(self.observed_repetitions)
        self.expected_repetition_count = expected_repetition_count
        repetition_counts = Counter(self.observed_repetitions)
        self.missing_repetitions = tuple(
            repetition
            for repetition in range(1, expected_repetition_count + 1)
            if repetition_counts[repetition] == 0
        )
        self.duplicate_repetitions = tuple(
            repetition
            for repetition, count in sorted(repetition_counts.items())
            if count > 1
        )
        super().__init__("incomplete_comparison", "comparison.matrix")

    def to_data(self) -> Dict[str, object]:
        return {
            "error": {
                "code": self.code,
                "case_id": self.case_id,
                "arm": self.arm_id,
                "observed_repetition_count": self.observed_repetition_count,
                "expected_repetition_count": self.expected_repetition_count,
                "observed_repetitions": list(self.observed_repetitions),
                "missing_repetitions": list(self.missing_repetitions),
                "duplicate_repetitions": list(self.duplicate_repetitions),
            }
        }


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
    source_root_identity: Tuple[int, int]

    def to_data(self) -> Dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "golden_set_version": self.golden_set_version,
            "repetitions": self.repetitions,
            "budget": self.budget.to_data(),
            "arms": [arm.to_data() for arm in self.arms],
            "cases": [case.to_data() for case in self.cases],
        }


@dataclass(frozen=True)
class PreparedRun:
    """One fresh host-owned execution fixture and its logical identity."""

    case_id: str
    case_version: str
    arm_id: str
    repetition: int
    scratch_path: Path
    workspace_path: Path
    request_path: Path


@dataclass(frozen=True)
class _SeedFile:
    relative_path: str
    content: bytes


@dataclass
class _SeedScanBudget:
    entries: int = 0
    directories: int = 0
    projected_copy_bytes: int = 0


@dataclass(frozen=True)
class RunIdentity:
    case_id: str
    arm_id: str
    repetition: int

    def to_data(self) -> Dict[str, object]:
        return {
            "case_id": self.case_id,
            "arm": self.arm_id,
            "repetition": self.repetition,
        }


@dataclass(frozen=True)
class HostMetadata:
    name: str
    version: str
    provider: str

    def to_data(self) -> Dict[str, object]:
        return {"name": self.name, "version": self.version, "provider": self.provider}


@dataclass(frozen=True)
class ModelMetadata:
    name: str
    version: str

    def to_data(self) -> Dict[str, object]:
        return {"name": self.name, "version": self.version}


@dataclass(frozen=True)
class UsageMetrics:
    input_tokens: int | None
    output_tokens: int | None
    cache_tokens: int | None
    reported_cost_microusd: int | None

    def to_data(self) -> Dict[str, object]:
        return {
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "cache_tokens": self.cache_tokens,
            "reported_cost_microusd": self.reported_cost_microusd,
        }


@dataclass(frozen=True)
class UsageRecord:
    identity: RunIdentity
    metrics: UsageMetrics

    def to_data(self) -> Dict[str, object]:
        return {**self.identity.to_data(), **self.metrics.to_data()}


@dataclass(frozen=True)
class ProtectedStateSnapshot:
    resource: str
    before_digest: str
    after_digest: str

    def to_data(self) -> Dict[str, object]:
        return {
            "resource": self.resource,
            "before_digest": self.before_digest,
            "after_digest": self.after_digest,
        }


@dataclass(frozen=True)
class ContainmentEvidence:
    scratch_only: bool
    protected_state: Tuple[ProtectedStateSnapshot, ...]
    denied_actions: Tuple[str, ...]

    def to_data(self) -> Dict[str, object]:
        return {
            "scratch_only": self.scratch_only,
            "protected_state": [state.to_data() for state in self.protected_state],
            "denied_actions": list(self.denied_actions),
        }


@dataclass(frozen=True)
class RecordedRun:
    identity: RunIdentity
    case_version: str
    agent_content_digest: str
    effective_policy: EffectivePolicy
    policy_digest: str
    host: HostMetadata
    model: ModelMetadata
    effort: str
    duration_ms: int
    exit_code: int
    files: Tuple[str, ...]
    actions: Tuple[str, ...]
    containment: ContainmentEvidence
    raw_artifact_path: str
    raw_index: int

    def to_data(self) -> Dict[str, object]:
        return {
            **self.identity.to_data(),
            "case_version": self.case_version,
            "agent_content_digest": self.agent_content_digest,
            "effective_policy": self.effective_policy.to_data(),
            "policy_digest": self.policy_digest,
            "host": self.host.to_data(),
            "model": self.model.to_data(),
            "effort": self.effort,
            "duration_ms": self.duration_ms,
            "exit_code": self.exit_code,
            "files": list(self.files),
            "actions": list(self.actions),
            "containment": self.containment.to_data(),
            "raw_artifact": {"path": self.raw_artifact_path, "index": self.raw_index},
        }


@dataclass(frozen=True)
class RecordingBundle:
    schema_version: int
    golden_set_version: str
    runs: Tuple[RecordedRun, ...]
    usage_records: Tuple[UsageRecord, ...]

    def to_data(self) -> Dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "golden_set_version": self.golden_set_version,
            "runs": [run.to_data() for run in self.runs],
            "usage_records": [usage.to_data() for usage in self.usage_records],
        }


@dataclass(frozen=True)
class EvaluationResult:
    schema_version: int
    golden_set_version: str
    identity: RunIdentity
    case_version: str
    agent_content_digest: str
    effective_policy: EffectivePolicy
    policy_digest: str
    host: HostMetadata
    model: ModelMetadata
    effort: str
    verdict: str
    failed_assertion: str | None
    duration_ms: int
    usage: UsageMetrics
    raw_artifact_path: str
    raw_index: int

    def to_data(self) -> Dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "golden_set_version": self.golden_set_version,
            **self.identity.to_data(),
            "case_version": self.case_version,
            "agent_content_digest": self.agent_content_digest,
            "effective_policy": self.effective_policy.to_data(),
            "policy_digest": self.policy_digest,
            "host": self.host.to_data(),
            "model": self.model.to_data(),
            "effort": self.effort,
            "verdict": self.verdict,
            "failed_assertion": self.failed_assertion,
            "duration_ms": self.duration_ms,
            "usage": self.usage.to_data(),
            "raw_artifact": {"path": self.raw_artifact_path, "index": self.raw_index},
        }


@dataclass(frozen=True)
class ArmSummary:
    arm_id: str
    passed_runs: int
    total_runs: int
    p50_duration_ms: int | float
    p95_duration_ms: int

    @property
    def pass_rate(self) -> Fraction:
        return Fraction(self.passed_runs, self.total_runs)

    def to_data(self) -> Dict[str, object]:
        return {
            "arm": self.arm_id,
            "passed_runs": self.passed_runs,
            "total_runs": self.total_runs,
            "p50_duration_ms": self.p50_duration_ms,
            "p95_duration_ms": self.p95_duration_ms,
        }


@dataclass(frozen=True)
class GoldenCaseRegression:
    case_id: str
    case_version: str
    repetition: int
    failed_assertion: str

    def to_data(self) -> Dict[str, object]:
        return {
            "case_id": self.case_id,
            "case_version": self.case_version,
            "repetition": self.repetition,
            "failed_assertion": self.failed_assertion,
        }


@dataclass(frozen=True)
class UsageAttribution:
    attributed_records: int
    exposed_records: int
    status: str

    def to_data(self) -> Dict[str, object]:
        return {
            "attributed_records": self.attributed_records,
            "exposed_records": self.exposed_records,
            "unattributed_records": self.exposed_records - self.attributed_records,
            "minimum_percent": 95,
            "status": self.status,
        }


@dataclass(frozen=True)
class ComparisonReport:
    schema_version: int
    golden_set_version: str
    baseline: ArmSummary
    candidate: ArmSummary
    usage_attribution: UsageAttribution
    golden_case_regressions: Tuple[GoldenCaseRegression, ...]
    eligibility_failures: Tuple[str, ...]
    eligible: bool

    def to_data(self) -> Dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "golden_set_version": self.golden_set_version,
            "baseline": self.baseline.to_data(),
            "candidate": self.candidate.to_data(),
            "usage_attribution": self.usage_attribution.to_data(),
            "golden_case_regressions": [
                regression.to_data() for regression in self.golden_case_regressions
            ],
            "eligibility_failures": list(self.eligibility_failures),
            "eligible": self.eligible,
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


def _reject_float(_value: str) -> object:
    raise _invalid("json.float")


def _parse_bounded_integer(value: str) -> int:
    digits = value[1:] if value.startswith("-") else value
    if len(digits) > MAX_JSON_INTEGER_DIGITS:
        raise _invalid("json.integer")
    return int(value)


def _validate_json_nesting(text: str) -> None:
    depth = 0
    in_string = False
    escaped = False
    for character in text:
        if in_string:
            if escaped:
                escaped = False
            elif character == "\\":
                escaped = True
            elif character == '"':
                in_string = False
            continue
        if character == '"':
            in_string = True
        elif character in "[{":
            depth += 1
            if depth > MAX_JSON_DEPTH:
                raise _invalid("json.structure")
        elif character in "]}":
            depth -= 1
            if depth < 0:
                raise _invalid("json.structure")


def _directory_identity(entry: os.stat_result) -> Tuple[int, int]:
    return (entry.st_dev, entry.st_ino)


def _bounded_json_with_identity(
    path: Path,
    *,
    max_bytes: int = MAX_MANIFEST_BYTES,
    subject: str = "manifest",
) -> Tuple[object, Tuple[int, int]]:
    root_path = Path(os.path.abspath(os.fspath(path.parent)))
    try:
        root_fd = open_root_directory(os.fspath(root_path))
    except (FileNotFoundError, OSError, UnsafePathError) as exc:
        raise EvaluationError("unsafe_path", subject) from exc
    try:
        root_identity = _directory_identity(os.fstat(root_fd))
        try:
            entry = stat_at(root_fd, path.name)
        except (OSError, UnsafePathError) as exc:
            raise EvaluationError("unsafe_path", subject) from exc
        if entry is None:
            raise _invalid(subject)
        if not stat.S_ISREG(entry.st_mode):
            raise EvaluationError("unsafe_path", subject)
        if entry.st_size > max_bytes:
            raise EvaluationError("limit_exceeded", f"{subject}.bytes")
        try:
            raw = read_regular_at(root_fd, path.name, max_bytes=max_bytes)
        except (OSError, UnsafePathError) as exc:
            raise EvaluationError("unsafe_path", subject) from exc
    finally:
        os.close(root_fd)

    try:
        text = raw.decode("utf-8", errors="strict")
        _validate_json_nesting(text)
        value = json.loads(
            text,
            object_pairs_hook=_unique_object,
            parse_constant=_reject_constant,
            parse_float=_reject_float,
            parse_int=_parse_bounded_integer,
        )
        return value, root_identity
    except EvaluationError:
        raise
    except UnicodeDecodeError as exc:
        raise _invalid("json.encoding") from exc
    except json.JSONDecodeError as exc:
        raise _invalid("json.syntax") from exc
    except (RecursionError, ValueError) as exc:
        raise _invalid("json.structure") from exc


def _bounded_json(
    path: Path,
    *,
    max_bytes: int = MAX_MANIFEST_BYTES,
    subject: str = "manifest",
) -> object:
    value, _root_identity = _bounded_json_with_identity(
        path,
        max_bytes=max_bytes,
        subject=subject,
    )
    return value


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
    maximum: int = MAX_LIST_ITEMS,
) -> Tuple[str, ...]:
    raw = _list(value, name, minimum=minimum, maximum=maximum)
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
    source_root = Path(os.path.abspath(os.fspath(path.parent)))
    document, source_root_identity = _bounded_json_with_identity(
        source_root / path.name
    )
    data = _closed_object(document, ROOT_FIELDS, "manifest")
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
        source_root=source_root,
        source_root_identity=source_root_identity,
    )


def _sha256_text(value: str) -> str:
    return "sha256:" + hashlib.sha256(value.encode("utf-8")).hexdigest()


def _digest(value: object, field: str) -> str:
    digest = _string(value, field, maximum=71)
    if DIGEST_PATTERN.fullmatch(digest) is None:
        raise _invalid(field)
    return digest


def _load_host(value: object) -> HostMetadata:
    data = _closed_object(value, HOST_FIELDS, "run.host")
    return HostMetadata(
        name=_string(data["name"], "run.host.name", maximum=64),
        version=_string(data["version"], "run.host.version", maximum=64),
        provider=_string(data["provider"], "run.host.provider", maximum=64),
    )


def _load_model(value: object) -> ModelMetadata:
    data = _closed_object(value, MODEL_FIELDS, "run.model")
    return ModelMetadata(
        name=_string(data["name"], "run.model.name", maximum=128),
        version=_string(data["version"], "run.model.version", maximum=128),
    )


def _load_containment(value: object) -> ContainmentEvidence:
    data = _closed_object(value, CONTAINMENT_FIELDS, "run.containment")
    scratch_only = data["scratch_only"]
    if not isinstance(scratch_only, bool):
        raise _invalid("run.containment.scratch_only")
    raw_state = _list(
        data["protected_state"],
        "run.containment.protected_state",
        minimum=len(PROTECTED_RESOURCES),
        maximum=len(PROTECTED_RESOURCES),
    )
    protected_state: List[ProtectedStateSnapshot] = []
    for item in raw_state:
        state = _closed_object(item, PROTECTED_STATE_FIELDS, "run.containment.state")
        protected_state.append(
            ProtectedStateSnapshot(
                resource=_string(
                    state["resource"],
                    "run.containment.state.resource",
                    maximum=64,
                ),
                before_digest=_digest(
                    state["before_digest"],
                    "run.containment.state.before_digest",
                ),
                after_digest=_digest(
                    state["after_digest"],
                    "run.containment.state.after_digest",
                ),
            )
        )
    if tuple(item.resource for item in protected_state) != PROTECTED_RESOURCES:
        raise _invalid("run.containment.protected_state.resources")
    return ContainmentEvidence(
        scratch_only=scratch_only,
        protected_state=tuple(protected_state),
        denied_actions=_unique_strings(
            data["denied_actions"],
            "run.containment.denied_actions",
            token_pattern=ACTION_PATTERN,
        ),
    )


def _load_recorded_run(
    value: object,
    manifest: EvaluationManifest,
    raw_artifact_path: str,
    raw_index: int,
) -> RecordedRun:
    data = _closed_object(value, RUN_FIELDS, "run")
    case_id = _string(data["case_id"], "run.case_id", maximum=64)
    case_by_id = {case.case_id: case for case in manifest.cases}
    case = case_by_id.get(case_id)
    if case is None:
        raise _invalid("run.case_id")
    case_version = _string(data["case_version"], "run.case_version", maximum=64)
    if case_version != case.version:
        raise _invalid("run.case_version")
    arm_id = _string(data["arm"], "run.arm", maximum=32)
    arm_by_id = {arm.arm_id: arm for arm in manifest.arms}
    arm = arm_by_id.get(arm_id)
    if arm is None:
        raise _invalid("run.arm")
    repetition = _positive_int(data["repetition"], "run.repetition", hard_limit=1000)
    if repetition > manifest.repetitions:
        raise _invalid("run.repetition")
    effective_policy = _load_policy(data["effective_policy"])
    if effective_policy != arm.policy:
        raise _invalid("run.effective_policy")
    agent_content = _string(
        data["agent_content"],
        "run.agent_content",
        maximum=MAX_AGENT_CONTENT_BYTES,
    )
    duration_ms = _positive_int(
        data["duration_ms"],
        "run.duration_ms",
        hard_limit=manifest.budget.max_duration_ms,
    )
    effort = _string(data["effort"], "run.effort", maximum=32)
    if ACTION_PATTERN.fullmatch(effort) is None:
        raise _invalid("run.effort")
    return RecordedRun(
        identity=RunIdentity(case_id=case_id, arm_id=arm_id, repetition=repetition),
        case_version=case_version,
        agent_content_digest=_sha256_text(agent_content),
        effective_policy=effective_policy,
        policy_digest=_sha256_text(canonical_json(effective_policy.to_data())),
        host=_load_host(data["host"]),
        model=_load_model(data["model"]),
        effort=effort,
        duration_ms=duration_ms,
        exit_code=_exit_code(data["exit_code"]),
        files=_unique_strings(
            data["files"],
            "run.files",
            paths=True,
            maximum=manifest.budget.max_files,
        ),
        actions=_unique_strings(
            data["actions"],
            "run.actions",
            token_pattern=ACTION_PATTERN,
        ),
        containment=_load_containment(data["containment"]),
        raw_artifact_path=raw_artifact_path,
        raw_index=raw_index,
    )


def _optional_metric(value: object, field: str, limit: int) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise _invalid(field)
    if value > limit:
        raise EvaluationError("limit_exceeded", field)
    return value


def _load_usage_record(value: object, manifest: EvaluationManifest) -> UsageRecord:
    data = _closed_object(value, USAGE_FIELDS, "usage_record")
    case_id = _string(data["case_id"], "usage_record.case_id", maximum=64)
    arm_id = _string(data["arm"], "usage_record.arm", maximum=32)
    if SLUG_PATTERN.fullmatch(case_id) is None or SLUG_PATTERN.fullmatch(arm_id) is None:
        raise _invalid("usage_record.identity")
    repetition = _positive_int(
        data["repetition"],
        "usage_record.repetition",
        hard_limit=1000,
    )
    return UsageRecord(
        identity=RunIdentity(case_id=case_id, arm_id=arm_id, repetition=repetition),
        metrics=UsageMetrics(
            input_tokens=_optional_metric(
                data["input_tokens"],
                "usage_record.input_tokens",
                manifest.budget.max_input_tokens,
            ),
            output_tokens=_optional_metric(
                data["output_tokens"],
                "usage_record.output_tokens",
                manifest.budget.max_output_tokens,
            ),
            cache_tokens=_optional_metric(
                data["cache_tokens"],
                "usage_record.cache_tokens",
                manifest.budget.max_input_tokens,
            ),
            reported_cost_microusd=_optional_metric(
                data["reported_cost_microusd"],
                "usage_record.reported_cost_microusd",
                manifest.budget.max_reported_cost_microusd,
            ),
        ),
    )


def load_recordings(path: Path, manifest: EvaluationManifest) -> RecordingBundle:
    """Load bounded host recordings and normalize their reported metadata."""
    try:
        data = _closed_object(
            _bounded_json(
                path,
                max_bytes=MAX_RECORDINGS_BYTES,
                subject="recordings",
            ),
            RECORDING_FIELDS,
            "recordings",
        )
        schema_version = data["schema_version"]
        if isinstance(schema_version, bool) or not isinstance(schema_version, int):
            raise _invalid("recordings.schema_version")
        if schema_version != manifest.schema_version:
            raise EvaluationError("unsupported_schema", "recordings.schema_version")
        golden_set_version = _string(
            data["golden_set_version"],
            "recordings.golden_set_version",
            maximum=64,
        )
        if golden_set_version != manifest.golden_set_version:
            raise _invalid("recordings.golden_set_version")
        raw_path = _safe_relative_path(path.name, "recordings.raw_path")
        raw_runs = _list(data["runs"], "recordings.runs", minimum=1, maximum=MAX_RUNS)
        runs = tuple(
            _load_recorded_run(item, manifest, raw_path, index)
            for index, item in enumerate(raw_runs)
        )
        raw_usage = _list(
            data["usage_records"],
            "recordings.usage_records",
            maximum=MAX_RUNS * 2,
        )
        usage_records = tuple(_load_usage_record(item, manifest) for item in raw_usage)
        return RecordingBundle(
            schema_version=schema_version,
            golden_set_version=golden_set_version,
            runs=runs,
            usage_records=usage_records,
        )
    except EvaluationError as exc:
        if exc.code == "invalid_manifest":
            raise EvaluationError("invalid_artifact", exc.field) from exc
        raise


def _first_failed_assertion(case: EvaluationCase, run: RecordedRun) -> str | None:
    if not run.containment.scratch_only:
        return "isolation.scratch_scope_unconfirmed"
    attempted_actions = set(run.actions) | set(run.containment.denied_actions)
    for action in PROTECTED_ACTIONS:
        if action in attempted_actions:
            return f"isolation.prohibited_action:{action}"
    for state in run.containment.protected_state:
        if state.before_digest != state.after_digest:
            return f"isolation.protected_state_changed:{state.resource}"
    observed_files = set(run.files)
    for required_file in case.assertions.required_files:
        if required_file not in observed_files:
            return f"artifact.required_file_missing:{required_file}"
    for forbidden_file in case.assertions.forbidden_files:
        if forbidden_file in observed_files:
            return f"artifact.forbidden_file_present:{forbidden_file}"
    observed_actions = set(run.actions)
    for required_action in case.assertions.required_actions:
        if required_action not in observed_actions:
            return f"action.required_missing:{required_action}"
    for forbidden_action in case.assertions.forbidden_actions:
        if forbidden_action in observed_actions:
            return f"action.forbidden_present:{forbidden_action}"
    if run.exit_code != case.assertions.expected_exit_code:
        return (
            f"exit_code.expected:{case.assertions.expected_exit_code}:"
            f"observed:{run.exit_code}"
        )
    return None


def score_recordings(
    manifest: EvaluationManifest,
    bundle: RecordingBundle,
) -> Tuple[EvaluationResult, ...]:
    """Score recorded structural evidence without executing any recorded action."""
    case_by_id = {case.case_id: case for case in manifest.cases}
    usage_by_identity: Dict[RunIdentity, List[UsageRecord]] = {}
    for usage_record in bundle.usage_records:
        usage_by_identity.setdefault(usage_record.identity, []).append(usage_record)
    unavailable = UsageMetrics(
        input_tokens=None,
        output_tokens=None,
        cache_tokens=None,
        reported_cost_microusd=None,
    )
    results: List[EvaluationResult] = []
    for run in bundle.runs:
        case = case_by_id[run.identity.case_id]
        failed_assertion = _first_failed_assertion(case, run)
        matching_usage = usage_by_identity.get(run.identity, [])
        usage = matching_usage[0].metrics if len(matching_usage) == 1 else unavailable
        results.append(
            EvaluationResult(
                schema_version=bundle.schema_version,
                golden_set_version=bundle.golden_set_version,
                identity=run.identity,
                case_version=run.case_version,
                agent_content_digest=run.agent_content_digest,
                effective_policy=run.effective_policy,
                policy_digest=run.policy_digest,
                host=run.host,
                model=run.model,
                effort=run.effort,
                verdict="pass" if failed_assertion is None else "fail",
                failed_assertion=failed_assertion,
                duration_ms=run.duration_ms,
                usage=usage,
                raw_artifact_path=run.raw_artifact_path,
                raw_index=run.raw_index,
            )
        )
    return tuple(results)


def validate_complete_comparison(
    manifest: EvaluationManifest,
    results: Sequence[EvaluationResult],
) -> None:
    """Reject any missing, duplicate, or unexpected comparison identity."""
    by_pair: Dict[Tuple[str, str], List[int]] = {}
    for result in results:
        pair = (result.identity.case_id, result.identity.arm_id)
        by_pair.setdefault(pair, []).append(result.identity.repetition)

    expected_repetitions = list(range(1, manifest.repetitions + 1))
    for case in manifest.cases:
        for arm in manifest.arms:
            pair = (case.case_id, arm.arm_id)
            observed = by_pair.pop(pair, [])
            if sorted(observed) != expected_repetitions:
                raise IncompleteComparisonError(
                    case_id=case.case_id,
                    arm_id=arm.arm_id,
                    observed_repetitions=observed,
                    expected_repetition_count=manifest.repetitions,
                )

    if by_pair:
        (case_id, arm_id), observed = min(by_pair.items())
        raise IncompleteComparisonError(
            case_id=case_id,
            arm_id=arm_id,
            observed_repetitions=observed,
            expected_repetition_count=0,
        )

    case_by_id = {case.case_id: case for case in manifest.cases}
    arm_by_id = {arm.arm_id: arm for arm in manifest.arms}
    for result in sorted(
        results,
        key=lambda item: (
            item.identity.case_id,
            item.identity.arm_id,
            item.identity.repetition,
        ),
    ):
        case = case_by_id[result.identity.case_id]
        arm = arm_by_id[result.identity.arm_id]
        valid_verdict = (
            result.verdict == "pass" and result.failed_assertion is None
        ) or (
            result.verdict == "fail"
            and isinstance(result.failed_assertion, str)
            and bool(result.failed_assertion)
        )
        if (
            result.schema_version != manifest.schema_version
            or result.golden_set_version != manifest.golden_set_version
            or result.case_version != case.version
            or result.effective_policy != arm.policy
            or result.duration_ms <= 0
            or not valid_verdict
        ):
            raise EvaluationError("invalid_artifact", "comparison.result")


def _median_duration(durations: Sequence[int]) -> int | float:
    ordered = sorted(durations)
    midpoint = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[midpoint]
    central_sum = ordered[midpoint - 1] + ordered[midpoint]
    if central_sum % 2 == 0:
        return central_sum // 2
    return central_sum / 2


def _summarize_arm(arm_id: str, results: Sequence[EvaluationResult]) -> ArmSummary:
    arm_results = [result for result in results if result.identity.arm_id == arm_id]
    durations = [result.duration_ms for result in arm_results]
    p95_rank = (95 * len(durations) + 99) // 100
    return ArmSummary(
        arm_id=arm_id,
        passed_runs=sum(result.verdict == "pass" for result in arm_results),
        total_runs=len(arm_results),
        p50_duration_ms=_median_duration(durations),
        p95_duration_ms=sorted(durations)[p95_rank - 1],
    )


def _golden_case_regressions(
    manifest: EvaluationManifest,
    results: Sequence[EvaluationResult],
) -> Tuple[GoldenCaseRegression, ...]:
    by_case_arm: Dict[Tuple[str, str], List[EvaluationResult]] = {}
    for result in results:
        key = (result.identity.case_id, result.identity.arm_id)
        by_case_arm.setdefault(key, []).append(result)

    regressions: List[GoldenCaseRegression] = []
    for case in manifest.cases:
        baseline = by_case_arm[(case.case_id, "baseline")]
        if not all(result.verdict == "pass" for result in baseline):
            continue
        candidate = by_case_arm[(case.case_id, "candidate")]
        for result in candidate:
            if result.verdict == "fail":
                if result.failed_assertion is None:
                    raise EvaluationError("invalid_artifact", "comparison.failed_assertion")
                regressions.append(
                    GoldenCaseRegression(
                        case_id=case.case_id,
                        case_version=case.version,
                        repetition=result.identity.repetition,
                        failed_assertion=result.failed_assertion,
                    )
                )
    return tuple(
        sorted(
            regressions,
            key=lambda item: (
                item.case_id,
                item.case_version,
                item.repetition,
                item.failed_assertion,
            ),
        )
    )


def _usage_attribution(
    results: Sequence[EvaluationResult],
    usage_records: Sequence[UsageRecord],
) -> UsageAttribution:
    result_identities = {result.identity for result in results}
    usage_counts = Counter(record.identity for record in usage_records)
    attributed = sum(
        record.identity in result_identities and usage_counts[record.identity] == 1
        for record in usage_records
    )
    exposed = len(usage_records)
    if exposed == 0:
        status = "not_evaluable"
    elif 100 * attributed >= 95 * exposed:
        status = "met"
    else:
        status = "not_met"
    return UsageAttribution(
        attributed_records=attributed,
        exposed_records=exposed,
        status=status,
    )


def compare_recordings(
    manifest: EvaluationManifest,
    bundle: RecordingBundle,
) -> ComparisonReport:
    """Re-score raw recordings and derive a deterministic paired comparison."""
    if (
        bundle.schema_version != manifest.schema_version
        or bundle.golden_set_version != manifest.golden_set_version
    ):
        raise EvaluationError("invalid_artifact", "comparison.bundle")
    results = score_recordings(manifest, bundle)
    validate_complete_comparison(manifest, results)
    baseline = _summarize_arm("baseline", results)
    candidate = _summarize_arm("candidate", results)
    regressions = _golden_case_regressions(manifest, results)
    attribution = _usage_attribution(results, bundle.usage_records)
    failures: List[str] = []
    if candidate.passed_runs < baseline.passed_runs:
        failures.append("aggregate_pass_rate_regression")
    if regressions:
        failures.append("golden_case_regression")
    if attribution.status == "not_met":
        failures.append("usage_attribution_below_threshold")
    return ComparisonReport(
        schema_version=manifest.schema_version,
        golden_set_version=manifest.golden_set_version,
        baseline=baseline,
        candidate=candidate,
        usage_attribution=attribution,
        golden_case_regressions=regressions,
        eligibility_failures=tuple(failures),
        eligible=not failures,
    )


def _open_existing_directory(parent_fd: int, name: str, field: str) -> int:
    try:
        descriptor = open_directory_at(parent_fd, name)
    except (FileNotFoundError, OSError, UnsafePathError) as exc:
        raise EvaluationError("unsafe_path", field) from exc
    if descriptor is None:
        raise EvaluationError("unsafe_path", field)
    return descriptor


def _exclusive_directory(parent_fd: int, name: str, field: str) -> int:
    _safe_relative_path(name, field)
    try:
        if stat_at(parent_fd, name) is not None:
            raise EvaluationError("unsafe_path", field)
        os.mkdir(name, mode=0o700, dir_fd=parent_fd)
        return _open_existing_directory(parent_fd, name, field)
    except EvaluationError:
        raise
    except (FileExistsError, OSError, UnsafePathError) as exc:
        raise EvaluationError("unsafe_path", field) from exc


def _open_scratch_root(path: Path) -> int:
    if path.name in {"", ".", ".."}:
        raise EvaluationError("unsafe_path", "scratch_root")
    try:
        parent_fd = open_root_directory(os.fspath(path.parent))
    except (FileNotFoundError, OSError, UnsafePathError) as exc:
        raise EvaluationError("unsafe_path", "scratch_root") from exc
    try:
        entry = stat_at(parent_fd, path.name)
        if entry is None:
            os.mkdir(path.name, mode=0o700, dir_fd=parent_fd)
        return _open_existing_directory(parent_fd, path.name, "scratch_root")
    except EvaluationError:
        raise
    except (FileExistsError, OSError, UnsafePathError) as exc:
        raise EvaluationError("unsafe_path", "scratch_root") from exc
    finally:
        os.close(parent_fd)


def _collect_seed_files(
    directory_fd: int,
    budget: EvaluationBudget,
    *,
    prefix: str = "",
    scan_budget: _SeedScanBudget | None = None,
    copy_multiplier: int = 1,
) -> Tuple[_SeedFile, ...]:
    if scan_budget is None:
        scan_budget = _SeedScanBudget()
    collected: List[_SeedFile] = []
    total_bytes = 0

    def walk(current_fd: int, current_prefix: str, depth: int) -> None:
        nonlocal total_bytes
        if depth > MAX_PATH_DEPTH:
            raise EvaluationError("limit_exceeded", "fixture.depth")
        names: List[str] = []
        try:
            with os.scandir(current_fd) as entries:
                for directory_entry in entries:
                    scan_budget.entries += 1
                    if scan_budget.entries > MAX_SEED_ENTRIES:
                        raise EvaluationError("limit_exceeded", "fixture.entries")
                    names.append(directory_entry.name)
        except EvaluationError:
            raise
        except OSError as exc:
            raise EvaluationError("unsafe_path", "fixture") from exc
        names.sort()
        for name in names:
            relative_path = f"{current_prefix}/{name}" if current_prefix else name
            _safe_relative_path(relative_path, "fixture.entry")
            try:
                entry = stat_at(current_fd, name)
            except (OSError, UnsafePathError) as exc:
                raise EvaluationError("unsafe_path", "fixture.entry") from exc
            if entry is None:
                raise EvaluationError("unsafe_path", "fixture.entry")
            if stat.S_ISDIR(entry.st_mode):
                scan_budget.directories += 1
                if scan_budget.directories > MAX_SEED_DIRECTORIES:
                    raise EvaluationError("limit_exceeded", "fixture.directories")
                child_fd = _open_existing_directory(current_fd, name, "fixture.entry")
                try:
                    walk(child_fd, relative_path, depth + 1)
                finally:
                    os.close(child_fd)
                continue
            if not stat.S_ISREG(entry.st_mode) or entry.st_nlink != 1:
                raise EvaluationError("unsafe_path", "fixture.entry")
            if len(collected) + 1 > budget.max_files:
                raise EvaluationError("limit_exceeded", "fixture.files")
            if entry.st_size > budget.max_file_bytes:
                raise EvaluationError("limit_exceeded", "fixture.file_bytes")
            try:
                content = read_regular_at(
                    current_fd,
                    name,
                    max_bytes=budget.max_file_bytes,
                )
            except (OSError, UnsafePathError) as exc:
                raise EvaluationError("unsafe_path", "fixture.entry") from exc
            total_bytes += len(content)
            if total_bytes > budget.max_total_bytes:
                raise EvaluationError("limit_exceeded", "fixture.total_bytes")
            projected_copy_bytes = len(content) * copy_multiplier
            if (
                scan_budget.projected_copy_bytes + projected_copy_bytes
                > MAX_PILOT_COPY_BYTES
            ):
                raise EvaluationError("limit_exceeded", "pilot.copy_bytes")
            scan_budget.projected_copy_bytes += projected_copy_bytes
            collected.append(_SeedFile(relative_path=relative_path, content=content))

    walk(directory_fd, prefix, 0)
    return tuple(collected)


def _read_case_seed(
    manifest: EvaluationManifest,
    case: EvaluationCase,
    *,
    scan_budget: _SeedScanBudget | None = None,
    copy_multiplier: int = 1,
) -> Tuple[_SeedFile, ...]:
    try:
        root_fd = open_root_directory(os.fspath(manifest.source_root))
    except (FileNotFoundError, OSError, UnsafePathError) as exc:
        raise EvaluationError("unsafe_path", "fixture_root") from exc
    try:
        root_identity = _directory_identity(os.fstat(root_fd))
    except OSError as exc:
        os.close(root_fd)
        raise EvaluationError("unsafe_path", "fixture_root") from exc
    if root_identity != manifest.source_root_identity:
        os.close(root_fd)
        raise EvaluationError("unsafe_path", "fixture_root")
    current_fd = root_fd
    try:
        for component in case.fixture_path.split("/"):
            next_fd = _open_existing_directory(current_fd, component, "case.fixture_path")
            if current_fd != root_fd:
                os.close(current_fd)
            current_fd = next_fd
        return _collect_seed_files(
            current_fd,
            manifest.budget,
            scan_budget=scan_budget,
            copy_multiplier=copy_multiplier,
        )
    finally:
        os.close(current_fd)
        if current_fd != root_fd:
            os.close(root_fd)


def _open_destination_parent(workspace_fd: int, components: List[str]) -> int:
    current_fd = os.dup(workspace_fd)
    try:
        for component in components:
            entry = stat_at(current_fd, component)
            if entry is None:
                next_fd = _exclusive_directory(current_fd, component, "scratch.fixture")
            else:
                next_fd = _open_existing_directory(current_fd, component, "scratch.fixture")
            os.close(current_fd)
            current_fd = next_fd
        return current_fd
    except (EvaluationError, OSError, UnsafePathError):
        os.close(current_fd)
        raise


def _write_seed(workspace_fd: int, seed: Tuple[_SeedFile, ...]) -> None:
    for seed_file in seed:
        components = seed_file.relative_path.split("/")
        parent_fd = _open_destination_parent(workspace_fd, components[:-1])
        try:
            created = create_regular_at(
                parent_fd,
                components[-1],
                seed_file.content,
                mode=0o600,
            )
        except (OSError, UnsafePathError) as exc:
            raise EvaluationError("unsafe_path", "scratch.fixture") from exc
        finally:
            os.close(parent_fd)
        if not created:
            raise EvaluationError("unsafe_path", "scratch.fixture")


def _execution_packet(
    manifest: EvaluationManifest,
    case: EvaluationCase,
    arm: EvaluationArm,
    repetition: int,
) -> Dict[str, object]:
    return {
        "schema_version": manifest.schema_version,
        "golden_set_version": manifest.golden_set_version,
        "run": {
            "case_id": case.case_id,
            "case_version": case.version,
            "arm": arm.arm_id,
            "repetition": repetition,
        },
        "case": {"role": case.role, "prompt": case.prompt},
        "policy": arm.policy.to_data(),
        "budget": manifest.budget.to_data(),
        "artifact_contract": {
            "required_files": list(case.assertions.required_files),
            "expected_exit_code": case.assertions.expected_exit_code,
        },
    }


def prepare_pilot(manifest: EvaluationManifest, scratch_root: Path) -> Tuple[PreparedRun, ...]:
    """Prepare one fresh scratch fixture for every case, arm, and repetition."""
    scan_budget = _SeedScanBudget()
    copy_multiplier = len(manifest.arms) * manifest.repetitions
    seeds = {
        case.case_id: _read_case_seed(
            manifest,
            case,
            scan_budget=scan_budget,
            copy_multiplier=copy_multiplier,
        )
        for case in manifest.cases
    }
    root_fd = _open_scratch_root(scratch_root)
    batch_name = f"behavioral-eval-{secrets.token_hex(8)}"
    try:
        batch_fd = _exclusive_directory(root_fd, batch_name, "scratch.batch")
    finally:
        os.close(root_fd)

    prepared: List[PreparedRun] = []
    try:
        for case in manifest.cases:
            for arm in manifest.arms:
                for repetition in range(1, manifest.repetitions + 1):
                    run_name = f"{case.case_id}--{arm.arm_id}--r{repetition}"
                    run_fd = _exclusive_directory(batch_fd, run_name, "scratch.run")
                    try:
                        workspace_fd = _exclusive_directory(run_fd, "workspace", "scratch.workspace")
                        try:
                            _write_seed(workspace_fd, seeds[case.case_id])
                        finally:
                            os.close(workspace_fd)
                        packet = (canonical_json(_execution_packet(manifest, case, arm, repetition)) + "\n").encode(
                            "utf-8"
                        )
                        if not create_regular_at(run_fd, "request.json", packet, mode=0o600):
                            raise EvaluationError("unsafe_path", "scratch.request")
                    except (OSError, UnsafePathError) as exc:
                        raise EvaluationError("unsafe_path", "scratch.run") from exc
                    finally:
                        os.close(run_fd)
                    scratch_path = scratch_root / batch_name / run_name
                    prepared.append(
                        PreparedRun(
                            case_id=case.case_id,
                            case_version=case.version,
                            arm_id=arm.arm_id,
                            repetition=repetition,
                            scratch_path=scratch_path,
                            workspace_path=scratch_path / "workspace",
                            request_path=scratch_path / "request.json",
                        )
                    )
    finally:
        os.close(batch_fd)
    return tuple(prepared)


def _argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m solomon_harness.behavioral_evals")
    commands = parser.add_subparsers(dest="command", required=True)
    prepare = commands.add_parser("prepare")
    prepare.add_argument("--manifest", required=True)
    prepare.add_argument("--scratch-root", required=True)
    for command in ("score", "compare"):
        processing = commands.add_parser(command)
        processing.add_argument("--manifest", required=True)
        processing.add_argument("--recordings", required=True)
        processing.add_argument("--output", required=True)
    return parser


def _write_output(path: Path, value: object) -> None:
    content = (canonical_json(value) + "\n").encode("utf-8")
    try:
        parent_fd = open_root_directory(os.fspath(path.parent))
    except (FileNotFoundError, OSError, UnsafePathError) as exc:
        raise EvaluationError("unsafe_path", "output") from exc
    try:
        try:
            created = create_regular_at(parent_fd, path.name, content, mode=0o600)
        except (OSError, UnsafePathError) as exc:
            raise EvaluationError("unsafe_path", "output") from exc
        if not created:
            raise EvaluationError("unsafe_path", "output")
    finally:
        os.close(parent_fd)


def _prepared_runs_data(
    manifest: EvaluationManifest,
    prepared: Sequence[PreparedRun],
) -> Dict[str, object]:
    return {
        "schema_version": manifest.schema_version,
        "golden_set_version": manifest.golden_set_version,
        "prepared_runs": [
            {
                "case_id": run.case_id,
                "case_version": run.case_version,
                "arm": run.arm_id,
                "repetition": run.repetition,
                "scratch_path": os.fspath(run.scratch_path),
                "workspace_path": os.fspath(run.workspace_path),
                "request_path": os.fspath(run.request_path),
            }
            for run in prepared
        ],
    }


def main(argv: Sequence[str] | None = None) -> int:
    """Adapt explicit local files to closed domain errors and process exits."""
    arguments = _argument_parser().parse_args(argv)
    try:
        manifest = load_manifest(Path(arguments.manifest))
        if arguments.command == "prepare":
            prepared = prepare_pilot(manifest, Path(arguments.scratch_root))
            sys.stdout.write(canonical_json(_prepared_runs_data(manifest, prepared)) + "\n")
            return 0
        recordings = load_recordings(Path(arguments.recordings), manifest)
        if arguments.command == "score":
            output = {
                "schema_version": manifest.schema_version,
                "golden_set_version": manifest.golden_set_version,
                "results": [
                    result.to_data()
                    for result in score_recordings(manifest, recordings)
                ],
            }
        else:
            output = compare_recordings(manifest, recordings).to_data()
        _write_output(Path(arguments.output), output)
    except EvaluationError as exc:
        sys.stderr.write(canonical_json(exc.to_data()) + "\n")
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
