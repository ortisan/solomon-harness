"""Tests for scripts/validate-workflows.py.

Covers the rewritten structural check (a real ``yaml.safe_load`` parse that
replaced the old character-by-character bracket scanner, which false-positived on
a ``[`` inside a quoted shell regex) and the security invariants (SHA-pinned
actions, explicit permissions, no emoji), plus an end-to-end run against the
repository's real workflows.
"""

import importlib.util
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "validate-workflows.py"


def _load():
    spec = importlib.util.spec_from_file_location("validate_workflows", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


vw = _load()

PINNED = "a" * 40
VALID = (
    "name: CI\n"
    "on:\n"
    "  pull_request:\n"
    "    branches: [main]\n"
    "permissions:\n"
    "  contents: read\n"
    "jobs:\n"
    "  build:\n"
    "    runs-on: ubuntu-latest\n"
    "    steps:\n"
    f"      - uses: actions/checkout@{PINNED}\n"
)

SOLOMON_WORKFLOWS = (
    "bug",
    "idea",
    "issue",
    "loop",
    "refine",
    "release",
    "review",
    "scan-arch",
    "scan-dedup",
    "start",
    "workflow",
)


def _write_solomon_workflows(root: Path) -> None:
    catalog = root / "solomon_harness" / "catalog" / "workflows"
    bridges = root / ".claude" / "commands"
    catalog.mkdir(parents=True)
    bridges.mkdir(parents=True)
    for name in SOLOMON_WORKFLOWS:
        metadata = (
            "---\n"
            f"description: Run the {name} workflow\n"
            f"argument-hint: [{name}-input]\n"
            "---\n"
        )
        source = catalog / f"solomon-{name}.md"
        source.write_text(
            metadata
            + "\n"
            + f"Run the host-neutral {name} lifecycle for {{{{arguments}}}}.\n",
            encoding="utf-8",
        )
        bridge = bridges / source.name
        bridge.write_text(
            metadata.removesuffix("---\n")
            + "allowed-tools: Read\n"
            + "---\n\n"
            + f"Read and follow `solomon_harness/catalog/workflows/{source.name}`.\n"
            + "Treat `$ARGUMENTS` as the value of `{{arguments}}` in that workflow.\n",
            encoding="utf-8",
        )


def test_real_workflows_validate():
    # End-to-end: the script hard-codes the two .github/workflows paths, so run it
    # from the repo root the way CI / a git hook would.
    result = subprocess.run(
        [sys.executable, str(SCRIPT)], cwd=ROOT, capture_output=True, text=True
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_real_solomon_catalog_and_claude_bridges_validate():
    assert vw.validate_solomon_workflow_catalog(ROOT) is True


def test_solomon_catalog_rejects_host_specific_protocols(tmp_path):
    _write_solomon_workflows(tmp_path)
    source = (
        tmp_path
        / "solomon_harness"
        / "catalog"
        / "workflows"
        / "solomon-review.md"
    )
    source.write_text(
        source.read_text(encoding="utf-8")
        + "Delegate through the Task tool in .claude/agents.\n",
        encoding="utf-8",
    )

    assert vw.validate_solomon_workflow_catalog(tmp_path) is False


def test_solomon_catalog_rejects_logic_duplicated_into_claude_bridge(tmp_path):
    _write_solomon_workflows(tmp_path)
    bridge = tmp_path / ".claude" / "commands" / "solomon-start.md"
    bridge.write_text(
        bridge.read_text(encoding="utf-8")
        + "\n## Implementation\nRun the complete TDD lifecycle here too.\n",
        encoding="utf-8",
    )

    assert vw.validate_solomon_workflow_catalog(tmp_path) is False


def test_solomon_catalog_rejects_missing_claude_capability_metadata(tmp_path):
    _write_solomon_workflows(tmp_path)
    source = (
        tmp_path
        / "solomon_harness"
        / "catalog"
        / "workflows"
        / "solomon-issue.md"
    )
    source.write_text(
        source.read_text(encoding="utf-8")
        + "Call `project-memory get_latest_activity`, then ask through the host's "
        + "native enumerable input mechanism.\n",
        encoding="utf-8",
    )

    assert vw.validate_solomon_workflow_catalog(tmp_path) is False


def test_valid_file_passes(tmp_path):
    f = tmp_path / "wf.yml"
    f.write_text(VALID, encoding="utf-8")
    assert vw.validate_workflow_file(str(f), "ci", ["name: CI"]) is True


def test_release_yaml_with_sed_regex_is_not_a_false_positive():
    # The exact shape that broke the old scanner lives in the real release.yml:
    # a `[` inside a quoted sed expression. The parser must accept it.
    content = (ROOT / ".github" / "workflows" / "release.yml").read_text(
        encoding="utf-8"
    )
    assert vw.validate_yaml_formatting(content, "release.yml") is True


def test_malformed_yaml_fails(tmp_path):
    # "mapping values are not allowed here" — a reliably-rejected construct.
    content = "name: CI\nfoo: bar: baz\n"
    f = tmp_path / "bad.yml"
    f.write_text(content, encoding="utf-8")
    assert vw.validate_yaml_formatting(content, str(f)) is False


def test_unpinned_action_fails(tmp_path):
    content = VALID.replace(f"actions/checkout@{PINNED}", "actions/checkout@v4")
    f = tmp_path / "wf.yml"
    f.write_text(content, encoding="utf-8")
    assert vw.validate_workflow_file(str(f), "ci", []) is False


def test_missing_permissions_fails(tmp_path):
    content = VALID.replace("permissions:\n  contents: read\n", "")
    f = tmp_path / "wf.yml"
    f.write_text(content, encoding="utf-8")
    assert vw.validate_workflow_file(str(f), "ci", []) is False


def test_emoji_fails(tmp_path):
    content = VALID + "    # ship it \U0001f680\n"
    f = tmp_path / "wf.yml"
    f.write_text(content, encoding="utf-8")
    assert vw.validate_workflow_file(str(f), "ci", []) is False
