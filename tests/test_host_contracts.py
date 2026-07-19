import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from solomon_harness.adapter_ownership import (
    AdapterOwnershipError,
    TEXT_END,
    TEXT_START,
    TOML_END,
    TOML_START,
    managed_adapter_digest,
)
from solomon_harness.host_hooks import (
    HookVerdict,
    analyze_shell_command,
    extract_patch_paths,
    extract_shell_write_paths,
    normalize_hook_input,
    serialize_hook_verdict,
    serialize_session_context,
)
from solomon_harness.install_layout import immutable_managed_paths


def test_patch_path_extraction_normalizes_diff_prefixes_and_duplicates():
    patch = (
        "--- a/src/app.py\told\n"
        "+++ b/src/app.py\tnew\n"
        "*** Move to: src/moved.py\n"
        "--- /dev/null\n"
        "not a header\n"
    )

    assert extract_patch_paths(patch) == ("src/app.py", "src/moved.py")


def test_normalizer_accepts_list_commands_nested_paths_and_other_tools():
    shell = normalize_hook_input(
        "codex",
        {
            "sessionId": "s",
            "tool": "shell",
            "input": {"command": ["touch", "src/new.py"]},
        },
    )
    other = normalize_hook_input(
        "agy",
        {
            "conversationId": "s",
            "toolCall": {
                "name": "custom",
                "args": {"nested": [{"path": "src/one.py"}, {"path": "src/one.py"}]},
            },
        },
    )

    assert (shell.tool_kind, shell.command) == ("shell", "touch src/new.py")
    assert (other.tool_kind, other.target_paths) == ("other", ("src/one.py",))


@pytest.mark.parametrize(
    ("host", "payload", "error"),
    [
        ("unknown", {}, ValueError),
        ("claude", [], TypeError),
    ],
)
def test_normalizer_rejects_unknown_hosts_and_non_objects(host, payload, error):
    with pytest.raises(error):
        normalize_hook_input(host, payload)


def test_shell_extractor_fails_closed_for_dynamic_targets_and_covers_safe_edges():
    with pytest.raises(ValueError, match="dynamic"):
        extract_shell_write_paths("rm $TARGET")
    with pytest.raises(ValueError, match="assignment"):
        extract_shell_write_paths('cmd=rm; "$cmd" .env')
    python = analyze_shell_command(
        "python -c \"p='.'+'env';open(p,'w').write('x')\""
    )
    ruby = analyze_shell_command("ruby -e \"File.write('.'+'env','x')\"")
    assert [request.scope for request in python.capability_requests] == ["dev:execute"]
    assert [request.scope for request in ruby.capability_requests] == ["dev:execute"]

    with pytest.raises(ValueError, match="cd"):
        extract_shell_write_paths("cd - && printf safe")
    with pytest.raises(ValueError, match="assignment"):
        extract_shell_write_paths("FOO=bar")
    assert extract_shell_write_paths("dd if=input skip=1") == ()
    assert extract_shell_write_paths("git status -- .env") == ()
    assert extract_shell_write_paths("bash -c 'touch .env'") == (".env",)
    assert extract_shell_write_paths("find .env -delete") == (".env",)
    assert extract_shell_write_paths("unlink .env") == (".env",)
    assert extract_shell_write_paths(
        "curl -o .env https://example.invalid"
    ) == (".env",)
    assert extract_shell_write_paths(
        "cp --target-directory=.agents/solomon/config project.json"
    ) == (".agents/solomon/config", "project.json")


@pytest.mark.parametrize("escaped_source", ["role", "workflow", "rules"])
def test_host_catalog_rejects_every_symlinked_canonical_source(
    tmp_path: Path, escaped_source: str
) -> None:
    from solomon_harness.host_adapter_common import _catalog

    core = tmp_path / ".agents" / "solomon"
    role = core / "agents" / "qa" / "agents" / "qa.md"
    workflow = core / "workflows" / "solomon-review.md"
    rules = core / "AGENTS.md"
    role.parent.mkdir(parents=True)
    workflow.parent.mkdir(parents=True)
    role.write_text("# QA\n", encoding="utf-8")
    workflow.write_text("# Review\n", encoding="utf-8")
    rules.write_text("# Rules\n", encoding="utf-8")

    target = {"role": role, "workflow": workflow, "rules": rules}[escaped_source]
    target.unlink()
    outside = tmp_path.parent / f"{tmp_path.name}-{escaped_source}-outside.md"
    outside.write_text("EXTERNAL_SECRET\n", encoding="utf-8")
    target.symlink_to(outside)
    try:
        with pytest.raises(ValueError, match="symlink"):
            _catalog(tmp_path)
    finally:
        outside.unlink(missing_ok=True)


def test_mandatory_core_trust_roots_do_not_depend_on_a_manifest(tmp_path: Path) -> None:
    protected = set(immutable_managed_paths(tmp_path))

    assert {
        ".agents/agents",
        ".agents/hooks.json",
        ".agents/plugins/solomon",
        ".agents/skills",
        ".agents/solomon/AGENTS.md",
        ".agents/solomon/agents",
        ".agents/solomon/conventions",
        ".agents/solomon/host-metadata",
        ".agents/solomon/pyproject.toml",
        ".agents/solomon/scripts",
        ".agents/solomon/solomon_harness",
        ".agents/solomon/state/.gitignore",
        ".agents/solomon/uv.lock",
        ".agents/solomon/workflows",
        ".claude/CLAUDE.md",
        ".claude/agents",
        ".claude/settings.json",
        ".claude/skills",
        ".codex/agents",
        ".codex/config.toml",
        ".codex/hooks.json",
        ".mcp.json",
        "AGENTS.md",
    } <= protected
    assert ".agents/solomon/state/handoffs" not in protected


def test_hook_serializers_cover_native_allow_deny_and_session_contracts():
    assert serialize_hook_verdict("claude", HookVerdict(True)).exit_code == 0
    denied = serialize_hook_verdict("codex", HookVerdict(False))
    assert denied.exit_code == 2
    assert denied.stderr == "Blocked by Solomon policy\n"
    agy = serialize_hook_verdict("agy", HookVerdict(False, "protected"))
    assert json.loads(agy.stdout) == {"decision": "deny", "reason": "protected"}

    assert json.loads(
        serialize_session_context("agy", "hidden", invocation_number=2).stdout
    ) == {"injectSteps": []}
    assert serialize_session_context("claude", "resume").stdout == "resume"

    with pytest.raises(ValueError):
        serialize_hook_verdict("unknown", HookVerdict(True))
    with pytest.raises(ValueError):
        serialize_session_context("unknown", "resume")


def test_managed_adapter_digest_fails_closed_for_ambiguous_and_invalid_inputs(tmp_path):
    marked = tmp_path / "AGENTS.md"
    marked.write_text(f"{TEXT_START}\none\n{TEXT_END}\n{TEXT_START}\ntwo\n{TEXT_END}\n")
    with pytest.raises(AdapterOwnershipError, match="ambiguous"):
        managed_adapter_digest(marked, "AGENTS.md")

    non_object = tmp_path / "settings.json"
    non_object.write_text("[]", encoding="utf-8")
    with pytest.raises(AdapterOwnershipError, match="not an object"):
        managed_adapter_digest(non_object, ".claude/settings.json")

    malformed = tmp_path / "malformed.json"
    malformed.write_text("{", encoding="utf-8")
    with pytest.raises(AdapterOwnershipError, match="Cannot inspect"):
        managed_adapter_digest(malformed, ".claude/settings.json")

    ordinary = tmp_path / "ordinary.txt"
    ordinary.write_text("product", encoding="utf-8")
    with pytest.raises(AdapterOwnershipError, match="not merge-managed"):
        managed_adapter_digest(ordinary, "src/product.txt")


def test_managed_json_digest_ignores_non_hook_siblings_and_rejects_unknown_json(tmp_path):
    settings = tmp_path / "settings.json"
    settings.write_text(
        json.dumps(
            {
                "hooks": {
                    "Other": "not-a-list",
                    "PreToolUse": [
                        {"command": "product-hook"},
                        {
                            "command": (
                                "python -I -m solomon_harness.cli host-hook "
                                "pre-tool-use --host claude"
                            )
                        },
                    ],
                },
                "user": True,
            }
        ),
        encoding="utf-8",
    )

    assert len(managed_adapter_digest(settings, ".claude/settings.json")) == 64
    with pytest.raises(AdapterOwnershipError, match="not merge-managed"):
        managed_adapter_digest(settings, ".agents/unknown.json")


def test_managed_digest_supports_every_merge_strategy(tmp_path):
    instructions = tmp_path / "AGENTS.md"
    instructions.write_text(
        f"user\n{TEXT_START}\nmanaged\n{TEXT_END}\n",
        encoding="utf-8",
    )
    codex = tmp_path / "config.toml"
    codex.write_text(
        f"user = true\n{TOML_START}\nmanaged = true\n{TOML_END}\n",
        encoding="utf-8",
    )
    agy_hooks = tmp_path / "hooks.json"
    agy_hooks.write_text(
        json.dumps(
            {
                "product": {"keep": True},
                "solomon-loop-guard": {"command": "guard"},
                "solomon-session-resume": {"command": "resume"},
            }
        ),
        encoding="utf-8",
    )
    mcp = tmp_path / "mcp.json"
    mcp.write_text(
        json.dumps(
            {
                "mcpServers": {
                    "product": {"command": "product"},
                    "solomon-memory": {"command": "uv"},
                }
            }
        ),
        encoding="utf-8",
    )

    for path, relative in (
        (instructions, "AGENTS.md"),
        (codex, ".codex/config.toml"),
        (agy_hooks, ".agents/hooks.json"),
        (mcp, ".mcp.json"),
    ):
        assert len(managed_adapter_digest(path, relative)) == 64


def test_isolated_python_ignores_consumer_sitecustomize_and_shadow_package(tmp_path):
    consumer = tmp_path / "consumer"
    malicious = consumer / "solomon_harness"
    malicious.mkdir(parents=True)
    (malicious / "__init__.py").write_text(
        "import os, pathlib\n"
        "pathlib.Path(os.environ['MALICIOUS_SENTINEL']).write_text('malicious')\n",
        encoding="utf-8",
    )
    (consumer / "sitecustomize.py").write_text(
        "import os, pathlib\n"
        "pathlib.Path(os.environ['SITE_SENTINEL']).write_text('sitecustomize')\n",
        encoding="utf-8",
    )

    canonical_sentinel = tmp_path / "canonical.txt"
    malicious_sentinel = tmp_path / "malicious.txt"
    site_sentinel = tmp_path / "site.txt"
    process_environment = dict(os.environ)
    process_environment.update(
        {
            "CANONICAL_SENTINEL": os.fspath(canonical_sentinel),
            "MALICIOUS_SENTINEL": os.fspath(malicious_sentinel),
            "SITE_SENTINEL": os.fspath(site_sentinel),
            "PYTHONPATH": os.fspath(consumer),
        }
    )

    completed = subprocess.run(
        [
            sys.executable,
            "-I",
            "-c",
            (
                "import os, pathlib, solomon_harness; "
                "pathlib.Path(os.environ['CANONICAL_SENTINEL']).write_text("
                "str(solomon_harness.__file__))"
            ),
        ],
        cwd=consumer,
        env=process_environment,
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0, completed.stderr
    imported = Path(canonical_sentinel.read_text(encoding="utf-8")).resolve()
    assert imported.name == "__init__.py"
    assert consumer.resolve() not in imported.parents
    assert not malicious_sentinel.exists()
    assert not site_sentinel.exists()
