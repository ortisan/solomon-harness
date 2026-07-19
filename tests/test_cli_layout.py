import importlib.util
import io
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from solomon_harness import cli
from solomon_harness.loop_lock import LoopLock
from solomon_harness.loop_policy import LoopPolicy


ROOT = Path(__file__).resolve().parents[1]
GENERATOR = ROOT / "scripts" / "generate-integrations.py"


def _load_generator():
    spec = importlib.util.spec_from_file_location("generate_integrations_cli_test", GENERATOR)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_parser_exposes_compile_uninstall_and_native_host_hooks():
    parser = cli.build_parser()

    compile_args = parser.parse_args(["compile"])
    uninstall_args = parser.parse_args(["uninstall", "--dry-run"])
    hook_args = parser.parse_args(
        ["host-hook", "pre-tool-use", "--host", "codex"]
    )

    assert compile_args.command == "compile"
    assert uninstall_args.command == "uninstall"
    assert uninstall_args.dry_run is True
    assert hook_args.event == "pre-tool-use"
    assert hook_args.host == "codex"


def test_compile_exits_nonzero_when_user_conflicts_are_preserved(tmp_path, capsys):
    result = SimpleNamespace(conflicts=("AGENTS.md",))

    with patch(
        "solomon_harness.host_adapters.compile_adapters",
        return_value=result,
    ), pytest.raises(SystemExit) as raised:
        cli.main(harness_dir=str(tmp_path), argv=["compile"])

    assert raised.value.code == 1
    assert "AGENTS.md" in capsys.readouterr().err


def test_dev_parser_and_dispatch_select_each_supported_engine(tmp_path):
    parser = cli.build_parser()
    parsed = parser.parse_args(["dev", "--engine", "codex", "idea", "one", "two"])
    assert parsed.engine == "codex"
    assert parsed.stage == "idea"
    assert parsed.dev_args == ["one", "two"]

    with (
        patch("solomon_harness.workflows.run_stage", return_value=0) as run_stage,
        pytest.raises(SystemExit) as stopped,
    ):
        cli.main(
            harness_dir=str(tmp_path),
            argv=["dev", "--engine", "agy", "issue", "new", "feature"],
        )

    assert stopped.value.code == 0
    run_stage.assert_called_once_with(
        str(tmp_path),
        "issue",
        ["new", "feature"],
        engine="agy",
    )


def test_compile_reconciles_an_installed_consumer_transactionally(tmp_path):
    manifest = tmp_path / ".agents" / "solomon" / "manifest.json"
    manifest.parent.mkdir(parents=True)
    manifest.write_text("{}\n", encoding="utf-8")
    result = SimpleNamespace(changed=True, conflicts=(), managed_paths=("AGENTS.md",))
    with (
        patch(
            "solomon_harness.install_layout.compile_project_adapters",
            return_value=result,
        ) as compile_project,
        patch("solomon_harness.host_adapters.compile_adapters") as compile_,
        pytest.raises(SystemExit) as raised,
    ):
        cli.main(harness_dir=str(tmp_path), argv=["compile"])

    assert raised.value.code == 0
    compile_project.assert_called_once_with(str(tmp_path))
    compile_.assert_not_called()


def test_compile_uses_adapter_compiler_directly_in_source_checkout(tmp_path):
    result = SimpleNamespace(changed=True, conflicts=(), managed_paths=("AGENTS.md",))
    with (
        patch("solomon_harness.install_layout.install_project") as install,
        patch(
            "solomon_harness.host_adapters.compile_adapters", return_value=result
        ) as compile_,
        pytest.raises(SystemExit) as raised,
    ):
        cli.main(harness_dir=str(tmp_path), argv=["compile"])

    assert raised.value.code == 0
    install.assert_not_called()
    compile_.assert_called_once_with(str(tmp_path))


def test_cli_finds_non_git_consumer_root_from_inside_installed_package(tmp_path):
    nested = tmp_path / ".agents" / "solomon" / "solomon_harness"
    nested.mkdir(parents=True)
    (tmp_path / ".agents" / "solomon" / "manifest.json").write_text(
        "{}\n", encoding="utf-8"
    )
    result = SimpleNamespace(changed=False, conflicts=(), managed_paths=())

    with (
        patch(
            "solomon_harness.install_layout.compile_project_adapters",
            return_value=result,
        ) as compile_project,
        patch("solomon_harness.host_adapters.compile_adapters") as compile_,
        pytest.raises(SystemExit) as raised,
    ):
        cli.main(harness_dir=str(nested), argv=["compile"])

    assert raised.value.code == 0
    compile_project.assert_called_once_with(str(tmp_path))
    compile_.assert_not_called()


def test_agents_list_reads_the_canonical_catalog_without_host_adapters(
    tmp_path, capsys
):
    role = (
        tmp_path
        / ".agents"
        / "solomon"
        / "agents"
        / "qa"
        / "agents"
        / "qa.md"
    )
    role.parent.mkdir(parents=True)
    role.write_text("# QA Profile\n\nReviews delivery quality.\n", encoding="utf-8")

    cli.main(harness_dir=str(tmp_path), argv=["agents", "list"])

    output = capsys.readouterr().out
    assert "Available subagents:" in output
    assert "qa - Reviews delivery quality." in output
    assert not (tmp_path / ".claude" / "agents").exists()


def test_agents_show_reads_the_canonical_role_instead_of_a_claude_bridge(
    tmp_path, capsys
):
    role = (
        tmp_path
        / ".agents"
        / "solomon"
        / "agents"
        / "software_engineer"
        / "agents"
        / "software_engineer.md"
    )
    role.parent.mkdir(parents=True)
    role.write_text(
        "# Software Engineer Profile\n\nBuilds production code.\n",
        encoding="utf-8",
    )

    cli.main(
        harness_dir=str(tmp_path),
        argv=["agents", "show", "software_engineer"],
    )

    assert capsys.readouterr().out.endswith(
        "# Software Engineer Profile\n\nBuilds production code.\n\n"
    )
    assert not (tmp_path / ".claude" / "agents").exists()


def test_uninstall_dry_run_never_calls_the_mutating_operation(tmp_path, capsys):
    manifest = {
        "schema_version": 1,
        "entries": [
            {"path": ".agents/solomon/AGENTS.md"},
            {"path": ".agents/solomon/config/project.json"},
        ],
    }
    with (
        patch("solomon_harness.install_layout.load_manifest", return_value=manifest),
        patch("solomon_harness.install_layout.uninstall_project") as uninstall,
        pytest.raises(SystemExit) as stopped,
    ):
        cli.main(harness_dir=str(tmp_path), argv=["uninstall", "--dry-run"])

    assert stopped.value.code == 0
    uninstall.assert_not_called()
    assert "dry-run" in capsys.readouterr().out


@pytest.mark.parametrize(
    ("host", "payload"),
    [
        (
            "claude",
            {
                "session_id": "driver-1",
                "tool_name": "Write",
                "tool_input": {
                    "file_path": "tmp/../.agents/solomon/config/project.json"
                },
            },
        ),
        (
            "agy",
            {
                "conversationId": "driver-1",
                "toolCall": {
                    "name": "write_to_file",
                    "args": {
                        "TargetFile": "tmp/../.agents/solomon/config/project.json"
                    },
                },
            },
        ),
        (
            "codex",
            {
                "sessionId": "driver-1",
                "tool": "apply_patch",
                "input": {
                    "patch": (
                        "*** Begin Patch\n"
                        "*** Update File: tmp/../.agents/solomon/config/project.json\n"
                        "*** End Patch\n"
                    )
                },
            },
        ),
    ],
)
def test_pre_tool_hook_normalizes_every_host_and_applies_the_existing_policy(
    tmp_path, host, payload
):
    policy = LoopPolicy(
        str(tmp_path),
        denylist=[".agents/solomon/config/project.json"],
    )
    stdin = io.StringIO(json.dumps(payload))
    stdout = io.StringIO()
    stderr = io.StringIO()

    with patch.object(LoopPolicy, "from_config", return_value=policy):
        exit_code = cli.handle_host_hook(
            str(tmp_path),
            host,
            "pre-tool-use",
            stdin=stdin,
            stdout=stdout,
            stderr=stderr,
        )

    if host == "agy":
        assert exit_code == 0
        assert json.loads(stdout.getvalue())["decision"] == "deny"
    else:
        assert exit_code == 2
        assert "denylist" in stderr.getvalue().lower()


@pytest.mark.parametrize("host", ["claude", "agy", "codex"])
def test_malformed_pre_tool_payload_fails_closed_for_every_host(tmp_path, host):
    stdout = io.StringIO()
    stderr = io.StringIO()

    exit_code = cli.handle_host_hook(
        str(tmp_path),
        host,
        "pre-tool-use",
        stdin=io.StringIO("{not-json"),
        stdout=stdout,
        stderr=stderr,
    )

    if host == "agy":
        assert exit_code == 0
        assert json.loads(stdout.getvalue())["decision"] == "deny"
    else:
        assert exit_code == 2
        assert "invalid" in stderr.getvalue().lower()


@pytest.mark.parametrize(
    ("host", "payload"),
    [
        (
            "claude",
            {
                "session_id": "driver-1",
                "tool_name": "Bash",
                "tool_input": {
                    "command": "rm tmp/../.agents/solomon/config/project.json"
                },
            },
        ),
        (
            "agy",
            {
                "conversationId": "driver-1",
                "toolCall": {
                    "name": "run_command",
                    "args": {
                        "CommandLine": (
                            "rm tmp/../.agents/solomon/config/project.json"
                        )
                    },
                },
            },
        ),
        (
            "codex",
            {
                "sessionId": "driver-1",
                "tool": "Bash",
                "input": {
                    "command": "rm tmp/../.agents/solomon/config/project.json"
                },
            },
        ),
    ],
)
def test_shell_hook_blocks_mutation_of_protected_config_for_every_host(
    tmp_path, host, payload
):
    policy = LoopPolicy(
        str(tmp_path),
        denylist=[".agents/solomon/config/project.json"],
    )
    stdout = io.StringIO()
    stderr = io.StringIO()
    with patch.object(LoopPolicy, "from_config", return_value=policy):
        exit_code = cli.handle_host_hook(
            str(tmp_path),
            host,
            "pre-tool-use",
            stdin=io.StringIO(json.dumps(payload)),
            stdout=stdout,
            stderr=stderr,
        )

    if host == "agy":
        assert exit_code == 0
        assert json.loads(stdout.getvalue())["decision"] == "deny"
    else:
        assert exit_code == 2
        assert "denylist" in stderr.getvalue().lower()


def _shell_payload(host: str, command: str) -> dict[str, object]:
    if host == "claude":
        return {
            "session_id": "driver-1",
            "tool_name": "Bash",
            "tool_input": {"command": command},
        }
    if host == "agy":
        return {
            "conversationId": "driver-1",
            "toolCall": {
                "name": "run_command",
                "args": {"CommandLine": command},
            },
        }
    return {
        "sessionId": "driver-1",
        "tool": "Bash",
        "input": {"command": command},
    }


def _shell_payload_with_session(
    host: str, command: str, session_id: str
) -> dict[str, object]:
    payload = _shell_payload(host, command)
    if host == "agy":
        payload["conversationId"] = session_id
    elif host == "claude":
        payload["session_id"] = session_id
    else:
        payload["sessionId"] = session_id
    return payload


@pytest.mark.parametrize("host", ["claude", "agy", "codex"])
def test_subprocess_hook_requires_capability_in_addition_to_outer_driver_identity(
    tmp_path, host, monkeypatch
):
    lock = LoopLock(str(tmp_path), session_id="outer-driver")
    lock.acquire()
    try:
        monkeypatch.setenv("SOLOMON_SUBPROCESS", "1")
        monkeypatch.setenv("SOLOMON_SESSION_ID", "outer-driver")
        stdout = io.StringIO()

        exit_code = cli.handle_host_hook(
            str(tmp_path),
            host,
            "pre-tool-use",
            stdin=io.StringIO(
                    json.dumps(
                        _shell_payload_with_session(
                            host,
                            "git push origin feature/safe",
                            "host-driver",
                        )
                    )
            ),
            stdout=stdout,
            stderr=io.StringIO(),
        )

        if host == "agy":
            assert exit_code == 0
            output = json.loads(stdout.getvalue())
            assert output["decision"] == "deny"
            assert "capability" in output["reason"].lower()
        else:
            assert exit_code == 2
    finally:
        lock.release()


@pytest.mark.parametrize("host", ["claude", "agy", "codex"])
@pytest.mark.parametrize(
    "command",
    [
        "git push",
        "git -C . push",
        "git -c core.sshCommand=x push",
        "gh --repo org/repo pr merge 288",
    ],
)
def test_foreign_driver_lock_blocks_option_bearing_push_and_merge_commands(
    tmp_path, host, command, monkeypatch
):
    lock = LoopLock(str(tmp_path), session_id="outer-driver")
    lock.acquire()
    try:
        monkeypatch.delenv("SOLOMON_SUBPROCESS", raising=False)
        monkeypatch.delenv("SOLOMON_SESSION_ID", raising=False)
        stdout = io.StringIO()
        stderr = io.StringIO()

        exit_code = cli.handle_host_hook(
            str(tmp_path),
            host,
            "pre-tool-use",
            stdin=io.StringIO(
                json.dumps(
                    _shell_payload_with_session(host, command, "foreign-driver")
                )
            ),
            stdout=stdout,
            stderr=stderr,
        )

        if host == "agy":
            assert json.loads(stdout.getvalue())["decision"] == "deny"
        else:
            assert exit_code == 2
            assert "single-driver lock" in stderr.getvalue()
    finally:
        lock.release()


def _write_payload(host: str, path: str) -> dict[str, object]:
    if host == "claude":
        return {
            "session_id": "driver-1",
            "tool_name": "Write",
            "tool_input": {"file_path": path},
        }
    if host == "agy":
        return {
            "conversationId": "driver-1",
            "toolCall": {
                "name": "write_to_file",
                "args": {"TargetFile": path},
            },
        }
    return {
        "sessionId": "driver-1",
        "tool": "Write",
        "input": {"file_path": path},
    }


def _patch_payload(host: str, path: str) -> dict[str, object]:
    patch_text = (
        "*** Begin Patch\n"
        f"*** Update File: {path}\n"
        "*** End Patch\n"
    )
    if host == "claude":
        return {
            "session_id": "driver-1",
            "tool_name": "apply_patch",
            "tool_input": {"patch": patch_text},
        }
    if host == "agy":
        return {
            "conversationId": "driver-1",
            "toolCall": {
                "name": "apply_patch",
                "args": {"patch": patch_text},
            },
        }
    return {
        "sessionId": "driver-1",
        "tool": "apply_patch",
        "input": {"patch": patch_text},
    }


def _write_install_manifest(root: Path) -> None:
    manifest = root / ".agents" / "solomon" / "manifest.json"
    manifest.parent.mkdir(parents=True)
    manifest.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "entries": [
                    {
                        "path": ".agents/solomon/solomon_harness/loop_policy.py",
                        "owner": "core",
                        "strategy": "replace",
                        "sha256": "0" * 64,
                        "mode": "0644",
                    },
                    {
                        "path": ".codex/config.toml",
                        "owner": "adapter",
                        "strategy": "toml-merge",
                        "sha256": "0" * 64,
                        "mode": "0644",
                    },
                ],
            }
        ),
        encoding="utf-8",
    )


@pytest.mark.parametrize("host", ["claude", "agy", "codex"])
@pytest.mark.parametrize(
    ("path", "payload_factory"),
    [
        (
            ".agents/solomon/solomon_harness/loop_policy.py",
            _write_payload,
        ),
        (".codex/config.toml", _patch_payload),
        (
            ".agents/solomon/manifest.json",
            lambda host, path: _shell_payload(host, f"rm {path}"),
        ),
        (
            ".agents/solomon/state/venv/lib/sitecustomize.py",
            _write_payload,
        ),
        (".agents/solomon/config/project.json", _write_payload),
        (".agent/config.json", _write_payload),
    ],
)
def test_pre_tool_hook_protects_installed_core_and_adapters(
    tmp_path, host, path, payload_factory
):
    _write_install_manifest(tmp_path)
    policy = LoopPolicy(str(tmp_path), denylist=[])
    stdout = io.StringIO()
    stderr = io.StringIO()

    with patch.object(LoopPolicy, "from_config", return_value=policy):
        exit_code = cli.handle_host_hook(
            str(tmp_path),
            host,
            "pre-tool-use",
            stdin=io.StringIO(json.dumps(payload_factory(host, path))),
            stdout=stdout,
            stderr=stderr,
        )

    if host == "agy":
        assert json.loads(stdout.getvalue())["decision"] == "deny"
    else:
        assert exit_code == 2


@pytest.mark.parametrize(
    ("host", "path"),
    [
        ("agy", ".agents/hooks.json"),
        ("claude", ".claude/settings.json"),
        ("codex", ".codex/config.toml"),
    ],
)
def test_pre_tool_hook_protects_each_native_guard_before_manifest(
    tmp_path, host, path
):
    policy = LoopPolicy(str(tmp_path), denylist=[])
    stdout = io.StringIO()

    with patch.object(LoopPolicy, "from_config", return_value=policy):
        exit_code = cli.handle_host_hook(
            str(tmp_path),
            host,
            "pre-tool-use",
            stdin=io.StringIO(json.dumps(_write_payload(host, path))),
            stdout=stdout,
            stderr=io.StringIO(),
        )

    if host == "agy":
        assert json.loads(stdout.getvalue())["decision"] == "deny"
    else:
        assert exit_code == 2


@pytest.mark.parametrize("host", ["claude", "agy", "codex"])
@pytest.mark.parametrize(
    "path",
    ["src/app.py", ".agents/solomon/state/handoffs/review-to-release.md"],
)
def test_pre_tool_hook_allows_unmanaged_product_and_state_files(tmp_path, host, path):
    _write_install_manifest(tmp_path)
    policy = LoopPolicy(str(tmp_path), denylist=[])
    stdout = io.StringIO()

    with patch.object(LoopPolicy, "from_config", return_value=policy):
        exit_code = cli.handle_host_hook(
            str(tmp_path),
            host,
            "pre-tool-use",
            stdin=io.StringIO(json.dumps(_write_payload(host, path))),
            stdout=stdout,
            stderr=io.StringIO(),
        )

    assert exit_code == 0
    if host == "agy":
        assert json.loads(stdout.getvalue())["decision"] == "allow"


@pytest.mark.parametrize("host", ["claude", "agy", "codex"])
@pytest.mark.parametrize(
    ("command", "denylist"),
    [
        ("rm .env", [".env"]),
        ("printf secret > .env", [".env"]),
        (
            "cd .agents/solomon/config && rm project.json",
            [".agents/solomon/config/project.json"],
        ),
        ("python -c \"open('.env', 'w').write('secret')\"", [".env"]),
        ("sudo -u nobody rm .env", [".env"]),
        ("env MODE=x rm .env", [".env"]),
        (
            "python -c \"import sys; open(sys.argv[1], 'w').write('x')\" .env",
            [".env"],
        ),
        ("git checkout -- .env", [".env"]),
        ("eval 'rm .env'", [".env"]),
        ("dd if=/dev/zero of=.env", [".env"]),
        (
            "cd .agents/solomon/config\nrm project.json",
            [".agents/solomon/config/project.json"],
        ),
        ("(rm .env)", [".env"]),
        ("find .env -delete", [".env"]),
        ("unlink .env", [".env"]),
        ('cmd=rm; "$cmd" .env', [".env"]),
        (
            "python -c \"p='.'+'env';open(p,'w').write('x')\"",
            [".env"],
        ),
        ("ruby -e \"File.write('.'+'env','x')\"", [".env"]),
        ("curl -o .env https://example.invalid", [".env"]),
        (
            "cp --target-directory=.agents/solomon/config project.json",
            [],
        ),
    ],
)
def test_shell_hook_blocks_denylisted_mutation_without_slash_bypasses(
    tmp_path, host, command, denylist
):
    policy = LoopPolicy(str(tmp_path), denylist=denylist)
    stdout = io.StringIO()
    stderr = io.StringIO()

    with patch.object(LoopPolicy, "from_config", return_value=policy):
        exit_code = cli.handle_host_hook(
            str(tmp_path),
            host,
            "pre-tool-use",
            stdin=io.StringIO(json.dumps(_shell_payload(host, command))),
            stdout=stdout,
            stderr=stderr,
        )

    if host == "agy":
        assert exit_code == 0
        assert json.loads(stdout.getvalue())["decision"] == "deny"
    else:
        assert exit_code == 2
        assert "denylist" in stderr.getvalue().lower()


def test_agy_pre_invocation_uses_native_session_context_protocol(tmp_path):
    stdout = io.StringIO()
    with patch.object(cli, "_session_resume_context", return_value="resume facts"):
        exit_code = cli.handle_host_hook(
            str(tmp_path),
            "agy",
            "pre-invocation",
            stdin=io.StringIO('{"invocationNum": 0}'),
            stdout=stdout,
            stderr=io.StringIO(),
        )

    assert exit_code == 0
    assert json.loads(stdout.getvalue()) == {
        "injectSteps": [{"ephemeralMessage": "resume facts"}]
    }

    later = io.StringIO()
    with patch.object(cli, "_session_resume_context", return_value="must stay hidden"):
        cli.handle_host_hook(
            str(tmp_path),
            "agy",
            "pre-invocation",
            stdin=io.StringIO('{"invocationNum": 2}'),
            stdout=later,
            stderr=io.StringIO(),
        )
    assert json.loads(later.getvalue()) == {"injectSteps": []}


def test_legacy_generator_delegates_without_creating_gemini_output(tmp_path):
    generator = _load_generator()
    result = SimpleNamespace(changed=True, conflicts=(), managed_paths=("AGENTS.md",))

    with patch("solomon_harness.host_adapters.compile_adapters", return_value=result) as compile_:
        return_code = generator.generate(str(tmp_path))

    assert return_code == 0
    compile_.assert_called_once_with(str(tmp_path))
    assert not (tmp_path / ".gemini").exists()


def test_deprecated_gemini_generator_is_an_inert_compatibility_shim(tmp_path):
    generator = _load_generator()
    legacy = tmp_path / ".claude" / "commands"
    legacy.mkdir(parents=True)
    (legacy / "solomon-start.md").write_text("start", encoding="utf-8")

    assert generator.generate_gemini_commands(str(tmp_path)) == 0
    assert not (tmp_path / ".gemini").exists()
