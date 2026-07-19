"""Normalize native lifecycle-hook payloads into one Solomon contract."""

from __future__ import annotations

import ast
import json
import os
import posixpath
import re
import shlex
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping, Optional


HOOK_HOSTS = ("agy", "claude", "codex")
_SHELL_TOOLS = {"bash", "command", "run_command", "shell"}
_PATCH_TOOLS = {"apply_patch", "patch"}
_WRITE_TOOLS = {
    "edit",
    "multiedit",
    "notebookedit",
    "replace_file_content",
    "multi_replace_file_content",
    "write",
    "write_to_file",
}
_PATH_KEYS = (
    "TargetFile",
    "targetFile",
    "target_file",
    "file_path",
    "notebook_path",
    "path",
)
_PATCH_PATH_RE = re.compile(
    r"^(?:\*\*\* (?:Add|Delete|Update) File:|\*\*\* Move to:|---|\+\+\+)\s+(.+?)\s*$"
)
_SHELL_MUTATORS = {
    "chmod",
    "chown",
    "cp",
    "dd",
    "install",
    "ln",
    "mkdir",
    "mkfifo",
    "mknod",
    "mv",
    "patch",
    "rm",
    "rmdir",
    "sed",
    "tee",
    "touch",
    "truncate",
    "unlink",
}
_SHELL_SPECIAL_MUTATORS = {"curl", "find", "openssl", "rsync", "tar", "wget"}
_SHELL_INTERPRETERS = {
    "awk",
    "bash",
    "node",
    "perl",
    "php",
    "python",
    "ruby",
    "sh",
    "zsh",
}
_SHELL_WRAPPERS = {"busybox", "command", "env", "nice"}
_SHELL_ALWAYS_OPAQUE = {"eval", "sudo", "xargs"}
_SHELL_READ_ONLY = {
    "basename",
    "cat",
    "cmp",
    "cut",
    "date",
    "dirname",
    "du",
    "echo",
    "file",
    "grep",
    "head",
    "id",
    "jq",
    "ls",
    "printf",
    "pwd",
    "readlink",
    "realpath",
    "rg",
    "stat",
    "tail",
    "test",
    "tree",
    "true",
    "false",
    "uname",
    "wc",
    "which",
    "whoami",
}
_GIT_READ_ONLY_SUBCOMMANDS = {
    "annotate",
    "blame",
    "describe",
    "diff",
    "grep",
    "log",
    "ls-files",
    "ls-remote",
    "ls-tree",
    "merge-base",
    "name-rev",
    "rev-list",
    "rev-parse",
    "shortlog",
    "show",
    "show-ref",
    "status",
}
_GIT_CAPABILITY_OPERATIONS = {
    "add",
    "branch",
    "checkout",
    "commit",
    "fetch",
    "push",
    "switch",
    "worktree",
}
_GIT_ALWAYS_DENIED = {
    "apply",
    "cherry-pick",
    "clean",
    "config",
    "merge",
    "mv",
    "pull",
    "rebase",
    "reset",
    "restore",
    "rm",
    "tag",
}
_GIT_GLOBAL_OPTIONS_WITH_VALUES = {"-C"}
_SAFE_BRANCH_PREFIXES = (
    "chore/",
    "docs/",
    "feature/",
    "fix/",
    "refactor/",
    "test/",
)
_HARNESS_STAGES = {
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
}
_HARNESS_MODULES = {
    "solomon_harness.cli",
    "solomon_harness.github",
    "solomon_harness.release",
    "solomon_harness.review_roster",
}
_HARNESS_SCRIPTS = {
    ".agents/solomon/scripts/check-adr-gate.py",
    ".agents/solomon/scripts/spec-lint.py",
    "scripts/check-adr-gate.py",
    "scripts/spec-lint.py",
}
_SHELL_CONTROL = {"\n", "&", "&&", "(", ")", ";", "|", "||", "{", "}"}
_SHELL_REDIRECT_RE = re.compile(r"^[<>]+$")
_TARGET_DIRECTORY_OPTIONS = {"-t", "--target-directory"}


@dataclass(frozen=True)
class NormalizedHookInput:
    """Host-independent facts used by the loop guard."""

    host: str
    session_id: str
    tool_kind: str
    command: str = ""
    target_paths: tuple[str, ...] = ()


@dataclass(frozen=True)
class HookVerdict:
    """Portable policy decision before host-specific serialization."""

    allow: bool
    reason: str = ""


@dataclass(frozen=True)
class HookExecution:
    """Bytes and status a hook command writes back to its host."""

    exit_code: int
    stdout: str = ""
    stderr: str = ""


@dataclass(frozen=True)
class ShellCapabilityRequest:
    """One privileged shell action that a trusted run must authorize."""

    scope: str
    branch: str = ""
    cwd: str = "."
    target_path: str = ""


@dataclass(frozen=True)
class ShellCommandAnalysis:
    """Statically classified writes and capability checks for one command."""

    write_paths: tuple[str, ...] = ()
    capability_requests: tuple[ShellCapabilityRequest, ...] = ()


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _text(value: Any) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, (list, tuple)) and all(isinstance(item, str) for item in value):
        return " ".join(value)
    return ""


def _deduplicate(values: Iterable[str]) -> tuple[str, ...]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        clean = value.strip().strip('"\'')
        if clean.startswith("a/") or clean.startswith("b/"):
            clean = clean[2:]
        if not clean or clean == "/dev/null" or clean in seen:
            continue
        seen.add(clean)
        result.append(clean)
    return tuple(result)


def _nested_paths(value: Any) -> Iterable[str]:
    if isinstance(value, Mapping):
        for key, child in value.items():
            if key in _PATH_KEYS and isinstance(child, str):
                yield child
            elif isinstance(child, (Mapping, list, tuple)):
                yield from _nested_paths(child)
    elif isinstance(value, (list, tuple)):
        for child in value:
            yield from _nested_paths(child)


def extract_patch_paths(patch: str) -> tuple[str, ...]:
    """Extract every target named by apply_patch or unified-diff text."""

    values: list[str] = []
    for line in patch.splitlines():
        match = _PATCH_PATH_RE.match(line)
        if not match:
            continue
        path = match.group(1)
        # Unified diffs may suffix a timestamp after a tab.
        values.append(path.split("\t", 1)[0])
    return _deduplicate(values)


def _shell_path(raw: str, cwd: str) -> str:
    clean = raw.strip().strip("\"'")
    if not clean:
        return ""
    if (
        clean.startswith(("~", "`", "<(", ">("))
        or "$" in clean
        or any(character in clean for character in "*?[")
    ):
        raise ValueError("Cannot safely resolve dynamic shell mutation target")
    if os.path.isabs(clean) or cwd in {"", "."}:
        return clean
    return posixpath.normpath(posixpath.join(cwd, clean))


def _shell_segments(tokens: list[str]) -> Iterable[list[str]]:
    segment: list[str] = []
    for token in tokens:
        if token in _SHELL_CONTROL:
            if segment:
                yield segment
                segment = []
            continue
        segment.append(token)
    if segment:
        yield segment


def _shell_command_index(segment: list[str]) -> int:
    index = 0
    while index < len(segment) and "=" in segment[index] and not segment[index].startswith("="):
        name, _, _ = segment[index].partition("=")
        if not name.replace("_", "a").isalnum():
            break
        index += 1
    while index < len(segment):
        executable = os.path.basename(segment[index])
        if executable not in _SHELL_WRAPPERS:
            return index
        index += 1
        if executable == "busybox":
            while index < len(segment) and segment[index].startswith("-"):
                index += 1
            return index
        if executable == "env":
            while index < len(segment):
                argument = segment[index]
                if argument == "--":
                    index += 1
                    break
                if argument in {"-C", "--chdir", "-S", "--split-string", "-u", "--unset"}:
                    if argument in {"-C", "--chdir", "-S", "--split-string"}:
                        raise ValueError(f"Cannot safely classify env wrapper option {argument}")
                    index += 2
                    continue
                if argument.startswith("-") or (
                    "=" in argument and not argument.startswith("=")
                ):
                    index += 1
                    continue
                break
        elif executable == "sudo":
            while index < len(segment):
                argument = segment[index]
                if argument == "--":
                    index += 1
                    break
                if argument in {
                    "-C",
                    "-D",
                    "-R",
                    "-T",
                    "-g",
                    "-h",
                    "-p",
                    "-r",
                    "-t",
                    "-u",
                }:
                    if argument in {"-C", "-D", "-R"}:
                        raise ValueError(f"Cannot safely classify sudo wrapper option {argument}")
                    index += 2
                    continue
                if argument.startswith("-"):
                    index += 1
                    continue
                break
        elif executable == "nice":
            if index < len(segment) and segment[index] in {"-n", "--adjustment"}:
                index += 2
            elif index < len(segment) and re.fullmatch(r"-\d+", segment[index]):
                index += 1
        else:  # command
            while index < len(segment) and segment[index].startswith("-"):
                index += 1
    return index


def _mutator_paths(executable: str, arguments: list[str], cwd: str) -> list[str]:
    """Return conservative targets for a direct filesystem mutator."""

    paths: list[str] = []
    skip_next = False
    for index, token in enumerate(arguments):
        if skip_next:
            skip_next = False
            continue
        if token in _TARGET_DIRECTORY_OPTIONS:
            if index + 1 >= len(arguments):
                raise ValueError(f"Missing target directory for {executable}")
            paths.append(_shell_path(arguments[index + 1], cwd))
            skip_next = True
            continue
        target_prefix = "--target-directory="
        if token.startswith(target_prefix):
            paths.append(_shell_path(token[len(target_prefix) :], cwd))
            continue
        if token.startswith("-") or _SHELL_REDIRECT_RE.fullmatch(token):
            continue
        if executable == "dd" and "=" in token:
            option, _, value = token.partition("=")
            if option == "of":
                paths.append(_shell_path(value, cwd))
            continue
        paths.append(_shell_path(token, cwd))
    return paths


def _find_mutation_paths(arguments: list[str], cwd: str) -> list[str]:
    """Classify destructive find expressions without executing nested commands."""

    if any(token in {"-exec", "-execdir", "-ok", "-okdir"} for token in arguments):
        raise ValueError("Cannot safely classify dynamic find execution")
    output_options = {"-fls", "-fprint", "-fprint0", "-fprintf"}
    output_paths: list[str] = []
    for index, token in enumerate(arguments):
        if token not in output_options:
            continue
        if index + 1 >= len(arguments):
            raise ValueError(f"Missing find output target for {token}")
        output_paths.append(_shell_path(arguments[index + 1], cwd))
    if "-delete" not in arguments:
        return output_paths
    roots: list[str] = []
    for token in arguments:
        if token.startswith("-") or token in {"!", "("}:
            break
        roots.append(_shell_path(token, cwd))
    return output_paths + (roots or [_shell_path(".", cwd)])


def _download_paths(executable: str, arguments: list[str], cwd: str) -> list[str]:
    """Extract explicit curl/wget destinations and reject remote-derived names."""

    paths: list[str] = []
    config_options = {"-K", "--config"} if executable == "curl" else {"--config"}
    if any(
        argument in config_options
        or any(argument.startswith(option + "=") for option in config_options)
        or (executable == "curl" and argument.startswith("-K") and len(argument) > 2)
        for argument in arguments
    ):
        raise ValueError(f"{executable} config files can hide mutation targets")
    value_options = (
        {"-o", "--output"}
        if executable == "curl"
        else {"-O", "--output-document", "-P", "--directory-prefix"}
    )
    dynamic_options = (
        {"-O", "--remote-name", "--remote-header-name"}
        if executable == "curl"
        else set()
    )
    index = 0
    while index < len(arguments):
        token = arguments[index]
        if token in dynamic_options:
            raise ValueError("Cannot safely resolve a remote-derived download target")
        if token in value_options:
            if index + 1 >= len(arguments):
                raise ValueError(f"Missing output target for {executable}")
            target = arguments[index + 1]
            if target != "-":
                paths.append(_shell_path(target, cwd))
            index += 2
            continue
        long_prefixes = ("--output=", "--output-document=")
        matched = next((prefix for prefix in long_prefixes if token.startswith(prefix)), None)
        if matched is not None:
            paths.append(_shell_path(token[len(matched) :], cwd))
        elif executable == "curl" and token.startswith("-o") and len(token) > 2:
            paths.append(_shell_path(token[2:], cwd))
        index += 1
    if executable == "wget" and not paths:
        raise ValueError("wget requires an explicit local output destination")
    return paths


def _rsync_paths(arguments: list[str], cwd: str) -> list[str]:
    """Return local rsync destinations and auxiliary output files."""

    paths: list[str] = []
    if "--remove-source-files" in arguments or "-e" in arguments or any(
        argument.startswith("--rsh=") for argument in arguments
    ):
        raise ValueError("rsync option has dynamic mutation or code-execution behavior")
    positional: list[str] = []
    value_options = {
        "--backup-dir",
        "--files-from",
        "--log-file",
        "--partial-dir",
        "--temp-dir",
        "-e",
    }
    output_options = {"--backup-dir", "--log-file", "--partial-dir", "--temp-dir"}
    index = 0
    while index < len(arguments):
        token = arguments[index]
        if token in value_options:
            if index + 1 >= len(arguments):
                raise ValueError(f"Missing rsync option value for {token}")
            if token in output_options:
                paths.append(_shell_path(arguments[index + 1], cwd))
            index += 2
            continue
        matched = next(
            (option for option in value_options if token.startswith(option + "=")),
            None,
        )
        if matched:
            if matched in output_options:
                paths.append(_shell_path(token.split("=", 1)[1], cwd))
        elif not token.startswith("-"):
            positional.append(token)
        index += 1
    if len(positional) < 2:
        raise ValueError("Cannot safely classify rsync without source and destination")
    destination = positional[-1]
    if ":" not in destination.split("/", 1)[0]:
        paths.append(_shell_path(destination, cwd))
    return paths


def _option_output_path(
    executable: str,
    arguments: list[str],
    cwd: str,
    options: set[str],
) -> list[str]:
    paths: list[str] = []
    index = 0
    while index < len(arguments):
        token = arguments[index]
        if token in options:
            if index + 1 >= len(arguments):
                raise ValueError(f"Missing output target for {executable} {token}")
            paths.append(_shell_path(arguments[index + 1], cwd))
            index += 2
            continue
        matched = next(
            (option for option in options if token.startswith(option + "=")),
            None,
        )
        if matched:
            paths.append(_shell_path(token.split("=", 1)[1], cwd))
        index += 1
    return paths


def _tar_paths(arguments: list[str], cwd: str) -> list[str]:
    if any(
        argument.startswith(("--checkpoint-action", "--use-compress-program"))
        for argument in arguments
    ):
        raise ValueError("tar option can execute an external program")
    archive_paths = _option_output_path("tar", arguments, cwd, {"--file", "-f"})
    option_words = [token.lstrip("-") for token in arguments if token.startswith("-")]
    modes = set("".join(option_words)) & {"c", "d", "r", "t", "u", "x"}
    if not modes and arguments:
        modes = set(arguments[0]) & {"c", "d", "r", "t", "u", "x"}
    if "t" in modes and not (modes & {"c", "d", "r", "u", "x"}):
        return []
    if "x" in modes:
        raise ValueError("tar extraction has archive-derived mutation targets")
    if modes & {"c", "d", "r", "u"}:
        if archive_paths:
            return archive_paths
        for index, token in enumerate(arguments):
            if "f" in token.lstrip("-"):
                if index + 1 >= len(arguments):
                    raise ValueError("Missing tar archive output")
                return [_shell_path(arguments[index + 1], cwd)]
    raise ValueError("Cannot safely classify tar operation")


def _sed_paths(arguments: list[str], cwd: str) -> list[str]:
    expressions = [
        arguments[index + 1]
        for index, argument in enumerate(arguments[:-1])
        if argument in {"-e", "--expression"}
    ]
    if not expressions:
        expressions = [argument for argument in arguments if not argument.startswith("-")][:1]
    if any(
        re.search(r"(?:^|[;\s])e(?:\s|$)", expression)
        or (expression.rstrip().endswith("e") and expression.lstrip().startswith("s"))
        for expression in expressions
    ):
        raise ValueError("sed expression can execute an external program")
    if not any(argument == "-i" or argument.startswith("-i") for argument in arguments):
        return []
    candidates = [argument for argument in arguments if not argument.startswith("-")]
    if len(candidates) < 2:
        raise ValueError("Cannot safely classify sed in-place targets")
    return [_shell_path(token, cwd) for token in candidates[1:]]


def _safe_branch(branch: str) -> str:
    normalized = branch.removeprefix("refs/heads/")
    if (
        not normalized
        or normalized in {"HEAD", "main", "master", "trunk", "develop", "development"}
        or normalized.startswith(("release/", "refs/", "-"))
        or ".." in normalized
        or "@{" in normalized
        or not normalized.startswith(_SAFE_BRANCH_PREFIXES)
    ):
        raise ValueError(f"Git branch is outside the autonomous delivery scope: {branch}")
    return normalized


def _git_command(
    arguments: list[str], cwd: str
) -> tuple[list[str], str, str]:
    """Return subcommand arguments, effective cwd, and subcommand."""

    index = 0
    git_cwd = cwd
    while index < len(arguments):
        argument = arguments[index]
        if argument == "-C":
            if index + 1 >= len(arguments):
                raise ValueError("Missing directory for git -C")
            git_cwd = _shell_path(arguments[index + 1], git_cwd)
            index += 2
            continue
        if argument in {
            "--config-env",
            "--exec-path",
            "--git-dir",
            "--namespace",
            "--super-prefix",
            "--work-tree",
            "-c",
        } or argument.startswith(
            (
                "--config-env=",
                "--exec-path=",
                "--git-dir=",
                "--namespace=",
                "--super-prefix=",
                "--work-tree=",
                "-c=",
            )
        ):
            raise ValueError("Git config, executable, and repository overrides are denied")
        if argument in _GIT_GLOBAL_OPTIONS_WITH_VALUES:
            if index + 1 >= len(arguments):
                raise ValueError(f"Missing value for Git option {argument}")
            index += 2
            continue
        if any(
            argument.startswith(option + "=")
            for option in _GIT_GLOBAL_OPTIONS_WITH_VALUES
        ):
            if argument.startswith("-C="):
                git_cwd = _shell_path(argument.split("=", 1)[1], git_cwd)
            index += 1
            continue
        if argument in {"--no-pager", "--literal-pathspecs", "--no-optional-locks"}:
            index += 1
            continue
        if argument.startswith("-"):
            raise ValueError(f"Unsupported Git global option: {argument}")
        return arguments[index + 1 :], git_cwd, argument
    raise ValueError("Git command is missing a subcommand")


def _git_push_branch(arguments: list[str]) -> str:
    unsafe = {
        "--all",
        "--delete",
        "--force",
        "--force-with-lease",
        "--mirror",
        "--prune",
        "--tags",
        "-d",
        "-f",
    }
    if any(
        token in unsafe or any(token.startswith(option + "=") for option in unsafe)
        for token in arguments
    ):
        raise ValueError("Force, delete, mirror, and bulk Git pushes are denied")
    positional = [token for token in arguments if not token.startswith("-")]
    if len(positional) != 2:
        raise ValueError("Autonomous Git push requires one remote and one explicit branch")
    remote, refspec = positional
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", remote) or "::" in remote:
        raise ValueError("Git push requires a named repository remote")
    if refspec.startswith(("+", ":")):
        raise ValueError("Force and delete refspecs are denied")
    if ":" in refspec:
        source, target = refspec.rsplit(":", 1)
        if not source or source.startswith("+"):
            raise ValueError("Force and delete refspecs are denied")
    else:
        source = target = refspec
    normalized_target = _safe_branch(target)
    normalized_source = source.removeprefix("refs/heads/")
    if normalized_source not in {"HEAD", normalized_target}:
        raise ValueError("Git push source must be HEAD or the scoped target branch")
    return normalized_target


def _git_analysis(arguments: list[str], cwd: str) -> ShellCommandAnalysis:
    subarguments, git_cwd, subcommand = _git_command(arguments, cwd)
    if subcommand in _GIT_READ_ONLY_SUBCOMMANDS:
        code_execution_options = {
            "--ext-diff",
            "--open-files-in-pager",
            "--textconv",
        }
        if any(
            argument in code_execution_options
            or any(argument.startswith(option + "=") for option in code_execution_options)
            for argument in subarguments
        ):
            raise ValueError("Git read command option can execute an external program")
        if subcommand == "ls-remote":
            positional = [part for part in subarguments if not part.startswith("-")]
            if positional and not re.fullmatch(
                r"[A-Za-z0-9][A-Za-z0-9._-]*", positional[0]
            ):
                raise ValueError("git ls-remote requires a named repository remote")
        output_paths = _option_output_path(
            f"git {subcommand}", subarguments, git_cwd, {"--output"}
        )
        return ShellCommandAnalysis(write_paths=_deduplicate(output_paths))
    if subcommand == "branch" and (
        not subarguments
        or subarguments == ["--show-current"]
        or subarguments == ["--list"]
        or subarguments == ["-l"]
        or subarguments == ["--all"]
        or subarguments == ["-a"]
        or subarguments == ["-r"]
    ):
        return ShellCommandAnalysis()
    if subcommand == "remote" and (
        not subarguments
        or subarguments[0] in {"get-url", "show", "-v"}
    ):
        return ShellCommandAnalysis()
    if subcommand in _GIT_ALWAYS_DENIED:
        raise ValueError(f"Git {subcommand} is denied by the autonomous shell policy")
    if subcommand not in _GIT_CAPABILITY_OPERATIONS:
        raise ValueError(f"Unclassified Git subcommand: {subcommand}")

    if subcommand == "commit" and "--amend" in subarguments:
        raise ValueError("Autonomous git commit --amend rewrites history")

    branch = ""
    if subcommand in {"add", "commit"}:
        branch = "@current"
    elif subcommand == "push":
        branch = _git_push_branch(subarguments)
    elif subcommand == "branch":
        if len(subarguments) != 1 or subarguments[0].startswith("-"):
            raise ValueError("Autonomous git branch only creates one explicit branch")
        branch = _safe_branch(subarguments[0])
    elif subcommand in {"checkout", "switch"}:
        create_option = "-b" if subcommand == "checkout" else "-c"
        if len(subarguments) != 2 or subarguments[0] != create_option:
            raise ValueError(f"Autonomous git {subcommand} must create a scoped branch")
        branch = _safe_branch(subarguments[1])
    elif subcommand == "worktree":
        if (
            len(subarguments) not in {4, 5}
            or subarguments[:2] != ["add", "-b"]
        ):
            raise ValueError("Only scoped git worktree add -b is allowed autonomously")
        branch = _safe_branch(subarguments[2])
        target_path = _shell_path(subarguments[3], git_cwd)
    elif subcommand == "fetch":
        positional = [part for part in subarguments if not part.startswith("-")]
        if (
            len(positional) != 1
            or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", positional[0])
            or "::" in positional[0]
            or any(part in {"--force", "--prune", "-f", "-p"} for part in subarguments)
        ):
            raise ValueError("Autonomous git fetch requires one named remote")

    return ShellCommandAnalysis(
        capability_requests=(
            ShellCapabilityRequest(
                f"git:{subcommand}",
                branch=branch,
                cwd=git_cwd,
                target_path=target_path if subcommand == "worktree" else "",
            ),
        )
    )


def _gh_analysis(arguments: list[str], cwd: str) -> ShellCommandAnalysis:
    words: list[str] = []
    index = 0
    value_options = {"--config", "--hostname", "--repo", "-R"}
    while index < len(arguments):
        token = arguments[index]
        if token in value_options:
            index += 2
            continue
        if any(token.startswith(option + "=") for option in value_options):
            index += 1
            continue
        if token.startswith("-"):
            index += 1
            continue
        words.append(token)
        index += 1
    if words[:2] == ["pr", "merge"]:
        return ShellCommandAnalysis(
            capability_requests=(ShellCapabilityRequest("human:merge", cwd=cwd),)
        )
    read_only = {
        ("auth", "status"),
        ("issue", "list"),
        ("issue", "status"),
        ("issue", "view"),
        ("pr", "checks"),
        ("pr", "diff"),
        ("pr", "list"),
        ("pr", "status"),
        ("pr", "view"),
        ("repo", "view"),
        ("run", "list"),
        ("run", "view"),
        ("run", "watch"),
    }
    if tuple(words[:2]) in read_only:
        return ShellCommandAnalysis()
    known_mutations = {
        ("issue", "close"),
        ("issue", "comment"),
        ("issue", "create"),
        ("issue", "edit"),
        ("issue", "reopen"),
        ("pr", "close"),
        ("pr", "comment"),
        ("pr", "create"),
        ("pr", "edit"),
        ("pr", "ready"),
        ("pr", "reopen"),
        ("pr", "review"),
    }
    if tuple(words[:2]) in known_mutations:
        return ShellCommandAnalysis(
            capability_requests=(ShellCapabilityRequest("gh:mutate", cwd=cwd),)
        )
    raise ValueError("Unclassified GitHub CLI command")


def _development_tool_analysis(
    executable: str, arguments: list[str], cwd: str
) -> ShellCommandAnalysis | None:
    command = executable
    tool_arguments = arguments
    if executable == "uv":
        if not arguments or arguments[0] != "run":
            return None
        index = 1
        project = ""
        while index < len(arguments) and arguments[index].startswith("-"):
            argument = arguments[index]
            if argument in {"--frozen", "--no-sync", "--offline"}:
                index += 1
                continue
            if argument == "--project":
                if index + 1 >= len(arguments):
                    return None
                project = arguments[index + 1]
                index += 2
                continue
            if argument.startswith("--project="):
                project = argument.split("=", 1)[1]
                index += 1
                continue
            return None
        if index >= len(arguments):
            return None
        if project and project != ".agents/solomon":
            return None
        command = os.path.basename(arguments[index])
        tool_arguments = arguments[index + 1 :]
    if command == "solomon-harness":
        if not tool_arguments:
            return None
        subcommand = tool_arguments[0]
        if subcommand == "dev":
            if len(tool_arguments) < 2 or tool_arguments[1] not in _HARNESS_STAGES:
                return None
        elif subcommand not in {
            "broker",
            "claim",
            "compile",
            "db-init",
            "github",
            "health",
            "log",
            "loop-lock",
            "loop-policy",
            "loop-stop",
            "memory-down",
            "memory-up",
            "reconcile",
            "release",
            "run",
            "wiki",
            "worktree",
        }:
            return None
        scope = (
            "harness:read"
            if subcommand in {"health", "log", "loop-policy"}
            else "dev:execute"
        )
        return ShellCommandAnalysis(
            capability_requests=(ShellCapabilityRequest(scope, cwd=cwd),)
        )
    if command in {"python", "python3"}:
        if tool_arguments[:2] == ["-I", "-m"] and len(tool_arguments) >= 3:
            module = tool_arguments[2]
            module_arguments = tool_arguments[3:]
            if module not in _HARNESS_MODULES:
                return None
            if module == "solomon_harness.cli":
                return _development_tool_analysis(
                    "solomon-harness",
                    module_arguments,
                    cwd,
                )
            if module == "solomon_harness.github":
                if module_arguments[:1] == ["merge"]:
                    return ShellCommandAnalysis(
                        capability_requests=(
                            ShellCapabilityRequest("human:merge", cwd=cwd),
                        )
                    )
                scope = (
                    "harness:read"
                    if module_arguments[:1] == ["list-open-issues"]
                    else "dev:execute"
                )
                return ShellCommandAnalysis(
                    capability_requests=(ShellCapabilityRequest(scope, cwd=cwd),)
                )
            if module == "solomon_harness.review_roster":
                return ShellCommandAnalysis(
                    capability_requests=(
                        ShellCapabilityRequest("harness:read", cwd=cwd),
                    )
                )
            return ShellCommandAnalysis(
                capability_requests=(ShellCapabilityRequest("dev:execute", cwd=cwd),)
            )
        if len(tool_arguments) >= 2 and tool_arguments[0] == "-I":
            script = tool_arguments[1]
            if script in _HARNESS_SCRIPTS:
                return ShellCommandAnalysis(
                    capability_requests=(
                        ShellCapabilityRequest("dev:execute", cwd=cwd),
                    )
                )
            if tool_arguments == ["-I", "-c", "import solomon_harness"]:
                return ShellCommandAnalysis(
                    capability_requests=(
                        ShellCapabilityRequest("harness:read", cwd=cwd),
                    )
                )
    safe = (
        command in {"pytest", "mypy"}
        or (command == "ruff" and tool_arguments and tool_arguments[0] == "check")
        or (command == "ruff" and tool_arguments[:2] == ["format", "--check"])
        or (command in {"cargo", "go"} and tool_arguments and tool_arguments[0] in {"check", "clippy", "test", "vet"})
        or (command in {"npm", "pnpm", "yarn"} and tool_arguments and tool_arguments[0] in {"test"})
    )
    if not safe:
        return None
    return ShellCommandAnalysis(
        capability_requests=(ShellCapabilityRequest("dev:execute", cwd=cwd),)
    )


def _python_string_value(
    node: ast.AST,
    bindings: Mapping[str, str],
    argv: list[str],
) -> str | None:
    """Resolve the deliberately small string subset used for mutation targets."""

    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.Name):
        return bindings.get(node.id)
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        left = _python_string_value(node.left, bindings, argv)
        right = _python_string_value(node.right, bindings, argv)
        if left is not None and right is not None:
            return left + right
        return None
    if isinstance(node, ast.JoinedStr):
        parts: list[str] = []
        for value in node.values:
            if not isinstance(value, ast.Constant) or not isinstance(value.value, str):
                return None
            parts.append(value.value)
        return "".join(parts)
    if (
        isinstance(node, ast.Subscript)
        and isinstance(node.value, ast.Attribute)
        and isinstance(node.value.value, ast.Name)
        and node.value.value.id == "sys"
        and node.value.attr == "argv"
        and isinstance(node.slice, ast.Constant)
        and isinstance(node.slice.value, int)
    ):
        index = node.slice.value
        if -len(argv) <= index < len(argv):
            return argv[index]
        return None
    if (
        isinstance(node, ast.Call)
        and isinstance(node.func, (ast.Name, ast.Attribute))
        and (
            (isinstance(node.func, ast.Name) and node.func.id == "Path")
            or (isinstance(node.func, ast.Attribute) and node.func.attr == "Path")
        )
        and node.args
    ):
        return _python_string_value(node.args[0], bindings, argv)
    return None


def _python_inline_write_paths(arguments: list[str], cwd: str) -> list[str]:
    """Extract explicit Python ``-c`` writes before granting opaque execution."""

    if "-c" not in arguments:
        return []
    code_index = arguments.index("-c") + 1
    if code_index >= len(arguments):
        raise ValueError("Missing Python inline command")
    code = arguments[code_index]
    try:
        tree = ast.parse(code)
    except SyntaxError as exc:
        raise ValueError("Cannot safely parse Python inline command") from exc

    # Under ``python -c``, sys.argv[0] is ``-c`` and user arguments start at 1.
    argv = ["-c", *arguments[code_index + 1 :]]
    bindings: dict[str, str] = {}
    assignments = [node for node in ast.walk(tree) if isinstance(node, ast.Assign)]
    for _ in range(len(assignments) + 1):
        changed = False
        for assignment in assignments:
            value = _python_string_value(assignment.value, bindings, argv)
            if value is None:
                continue
            for target in assignment.targets:
                if isinstance(target, ast.Name) and bindings.get(target.id) != value:
                    bindings[target.id] = value
                    changed = True
        if not changed:
            break

    paths: list[str] = []

    def require_path(node: ast.AST, operation: str) -> str:
        value = _python_string_value(node, bindings, argv)
        if value is None:
            raise ValueError(
                f"Cannot safely resolve Python {operation} mutation target"
            )
        return _shell_path(value, cwd)

    for call in (node for node in ast.walk(tree) if isinstance(node, ast.Call)):
        function = call.func
        if isinstance(function, ast.Name) and function.id == "open":
            if not call.args:
                raise ValueError("Python open mutation is missing its target")
            mode_node = call.args[1] if len(call.args) > 1 else None
            for keyword in call.keywords:
                if keyword.arg == "mode":
                    mode_node = keyword.value
            mode = (
                _python_string_value(mode_node, bindings, argv)
                if mode_node is not None
                else "r"
            )
            if mode is None:
                raise ValueError("Cannot safely resolve Python open mode")
            if any(flag in mode for flag in "wax+"):
                paths.append(require_path(call.args[0], "open"))
            continue

        if not isinstance(function, ast.Attribute):
            continue
        attribute = function.attr
        if (
            isinstance(function.value, ast.Name)
            and function.value.id in {"os", "shutil"}
        ):
            first_target = {
                "chmod",
                "chown",
                "makedirs",
                "mkdir",
                "remove",
                "removedirs",
                "rmdir",
                "rmtree",
                "truncate",
                "unlink",
            }
            two_targets = {"move", "rename", "renames", "replace"}
            destination_only = {"copy", "copy2", "copyfile", "copytree"}
            if attribute in first_target:
                if not call.args:
                    raise ValueError(f"Python {attribute} mutation is missing its target")
                paths.append(require_path(call.args[0], attribute))
            elif attribute in two_targets:
                if len(call.args) < 2:
                    raise ValueError(f"Python {attribute} mutation is missing a target")
                paths.extend(
                    (
                        require_path(call.args[0], attribute),
                        require_path(call.args[1], attribute),
                    )
                )
            elif attribute in destination_only:
                if len(call.args) < 2:
                    raise ValueError(f"Python {attribute} mutation is missing a target")
                paths.append(require_path(call.args[1], attribute))
            continue

        path_methods = {
            "chmod",
            "hardlink_to",
            "mkdir",
            "rename",
            "replace",
            "rmdir",
            "symlink_to",
            "touch",
            "unlink",
            "write_bytes",
            "write_text",
        }
        if attribute in path_methods:
            paths.append(require_path(function.value, f"Path.{attribute}"))
            if attribute in {"rename", "replace"}:
                if not call.args:
                    raise ValueError(
                        f"Python Path.{attribute} mutation is missing a target"
                    )
                paths.append(require_path(call.args[0], f"Path.{attribute}"))
        elif attribute == "open":
            mode_node = call.args[0] if call.args else None
            for keyword in call.keywords:
                if keyword.arg == "mode":
                    mode_node = keyword.value
            mode = (
                _python_string_value(mode_node, bindings, argv)
                if mode_node is not None
                else "r"
            )
            if mode is None:
                raise ValueError("Cannot safely resolve Python Path.open mode")
            if any(flag in mode for flag in "wax+"):
                paths.append(require_path(function.value, "Path.open"))
    return paths


_RUBY_STRING_EXPRESSION = (
    r"(?P<target>(?:'(?:[^'\\]|\\.)*'|\"(?:[^\"\\]|\\.)*\")"
    r"(?:\s*\+\s*(?:'(?:[^'\\]|\\.)*'|\"(?:[^\"\\]|\\.)*\"))*)"
)


def _constant_concat_value(expression: str) -> str | None:
    """Evaluate only quoted string literals joined with ``+``."""

    try:
        parsed = ast.parse(expression, mode="eval")
    except SyntaxError:
        return None
    return _python_string_value(parsed.body, {}, [])


def _ruby_inline_write_paths(arguments: list[str], cwd: str) -> list[str]:
    """Extract explicit Ruby ``-e`` File mutations, including literal concat."""

    if "-e" not in arguments:
        return []
    code_index = arguments.index("-e") + 1
    if code_index >= len(arguments):
        raise ValueError("Missing Ruby inline command")
    code = arguments[code_index]
    mutation = re.compile(
        rf"File\.(?:binwrite|delete|rename|truncate|unlink|write)\s*\(\s*"
        rf"{_RUBY_STRING_EXPRESSION}"
    )
    matches = list(mutation.finditer(code))
    if re.search(r"File\.(?:binwrite|delete|rename|truncate|unlink|write)\s*\(", code) and not matches:
        raise ValueError("Cannot safely resolve Ruby File mutation target")
    paths: list[str] = []
    for match in matches:
        value = _constant_concat_value(match.group("target"))
        if value is None:
            raise ValueError("Cannot safely resolve Ruby File mutation target")
        paths.append(_shell_path(value, cwd))
    return paths


def analyze_shell_command(command: str) -> ShellCommandAnalysis:
    """Classify every shell segment or reject the whole command.

    Explicit read-only forms and statically provable filesystem writes are
    classified directly. Unknown executables and interpreter code become a
    ``dev:execute`` capability request, which a Solomon subprocess must prove;
    native interactive hosts retain their own approval boundary. Shell wrappers
    and options that can conceal another command or mutation target still raise
    ``ValueError`` and are denied on every host.
    """

    if "$(" in command or "`" in command:
        raise ValueError("Cannot safely classify dynamic shell execution")
    lexer = shlex.shlex(command, posix=True, punctuation_chars=";&|<>(){}\n")
    lexer.whitespace = " \t\r"
    lexer.whitespace_split = True
    lexer.commenters = ""
    tokens = list(lexer)
    cwd = "."
    paths: list[str] = []
    requests: list[ShellCapabilityRequest] = []

    for segment in _shell_segments(tokens):
        command_index = _shell_command_index(segment)
        if command_index >= len(segment):
            if segment:
                raise ValueError("Shell assignment without an executable is denied")
            continue
        for prefix_part in segment[:command_index]:
            if "=" in prefix_part and not prefix_part.startswith("="):
                if prefix_part != (
                    "UV_PROJECT_ENVIRONMENT=.agents/solomon/state/venv"
                ):
                    raise ValueError("Shell environment assignments are denied")
        raw_executable = segment[command_index]
        if "/" in raw_executable:
            raise ValueError("Shell executables with explicit paths are denied")
        executable = os.path.basename(raw_executable)
        arguments = segment[command_index + 1 :]
        if executable.startswith(("$", "`")):
            raise ValueError("Cannot safely resolve dynamic shell executable")
        if executable == "cd":
            destination = next(
                (value for value in arguments if not value.startswith("-")), ""
            )
            if not destination:
                raise ValueError("cd requires one explicit workspace directory")
            cwd = _shell_path(destination, cwd)
            continue

        for index, token in enumerate(segment[:-1]):
            if ">" in token and _SHELL_REDIRECT_RE.fullmatch(token):
                target = segment[index + 1]
                if not target.startswith("&"):
                    paths.append(_shell_path(target, cwd))

        normalized_executable = re.sub(r"[0-9.]+$", "", executable)
        analysis: ShellCommandAnalysis | None = None
        if executable == "sed":
            paths.extend(_sed_paths(arguments, cwd))
        elif executable == "patch":
            raise ValueError("patch input carries dynamic mutation targets")
        elif executable in _SHELL_MUTATORS:
            paths.extend(_mutator_paths(executable, arguments, cwd))
        elif executable == "find":
            paths.extend(_find_mutation_paths(arguments, cwd))
        elif executable in {"curl", "wget"}:
            paths.extend(_download_paths(executable, arguments, cwd))
        elif executable == "rsync":
            paths.extend(_rsync_paths(arguments, cwd))
        elif executable == "tar":
            paths.extend(_tar_paths(arguments, cwd))
        elif executable == "openssl":
            openssl_paths = _option_output_path(
                "openssl", arguments, cwd, {"-out", "-keyout"}
            )
            if not openssl_paths:
                raise ValueError("Cannot safely classify openssl without an output target")
            paths.extend(openssl_paths)
        elif executable == "sort":
            paths.extend(_option_output_path("sort", arguments, cwd, {"-o", "--output"}))
        elif executable == "uniq":
            positional = [part for part in arguments if not part.startswith("-")]
            if len(positional) > 1:
                paths.append(_shell_path(positional[-1], cwd))
        elif executable == "diff":
            paths.extend(_option_output_path("diff", arguments, cwd, {"--output"}))
        elif executable == "tree":
            paths.extend(_option_output_path("tree", arguments, cwd, {"-o"}))
        elif executable == "yq":
            if any(part in {"-i", "--inplace"} for part in arguments):
                positional = [part for part in arguments if not part.startswith("-")]
                if not positional:
                    raise ValueError("Cannot resolve yq in-place mutation target")
                paths.append(_shell_path(positional[-1], cwd))
        elif executable == "git":
            analysis = _git_analysis(arguments, cwd)
        elif executable == "gh":
            analysis = _gh_analysis(arguments, cwd)
        elif normalized_executable in _SHELL_INTERPRETERS:
            trusted_harness = _development_tool_analysis(executable, arguments, cwd)
            if trusted_harness is not None:
                analysis = trusted_harness
                if analysis is not None:
                    paths.extend(analysis.write_paths)
                    requests.extend(analysis.capability_requests)
                continue
            if arguments in (["--version"], ["-V"]):
                continue
            if normalized_executable in {"bash", "sh", "zsh"} and "-c" in arguments:
                code_index = arguments.index("-c") + 1
                if code_index >= len(arguments):
                    raise ValueError("Missing shell interpreter command")
                nested = analyze_shell_command(arguments[code_index])
                paths.extend(_shell_path(path, cwd) for path in nested.write_paths)
                requests.extend(
                    ShellCapabilityRequest(
                        request.scope,
                        branch=request.branch,
                        cwd=_shell_path(request.cwd, cwd),
                        target_path=(
                            _shell_path(request.target_path, cwd)
                            if request.target_path
                            else ""
                        ),
                    )
                    for request in nested.capability_requests
                )
                continue
            if normalized_executable == "python":
                paths.extend(_python_inline_write_paths(arguments, cwd))
            elif normalized_executable == "ruby":
                paths.extend(_ruby_inline_write_paths(arguments, cwd))
            analysis = ShellCommandAnalysis(
                capability_requests=(
                    ShellCapabilityRequest("dev:execute", cwd=cwd),
                )
            )
        elif executable in _SHELL_ALWAYS_OPAQUE:
            raise ValueError(f"Cannot safely classify opaque shell executor: {executable}")
        elif executable in _SHELL_READ_ONLY:
            if executable == "rg" and any(
                argument == "--pre" or argument.startswith("--pre=")
                for argument in arguments
            ):
                raise ValueError("rg --pre can execute an external program")
        else:
            analysis = _development_tool_analysis(executable, arguments, cwd)
            if analysis is None:
                analysis = ShellCommandAnalysis(
                    capability_requests=(
                        ShellCapabilityRequest("dev:execute", cwd=cwd),
                    )
                )

        if analysis is not None:
            paths.extend(analysis.write_paths)
            requests.extend(analysis.capability_requests)

    return ShellCommandAnalysis(
        write_paths=_deduplicate(paths),
        capability_requests=tuple(requests),
    )


def extract_shell_write_paths(command: str) -> tuple[str, ...]:
    """Return statically proven targets, rejecting every unclassified segment."""

    return analyze_shell_command(command).write_paths


def _git_directory(start: Path) -> Path | None:
    current = start.resolve(strict=False)
    for candidate in (current, *current.parents):
        marker = candidate / ".git"
        if marker.is_dir():
            return marker.resolve()
        if marker.is_file():
            try:
                prefix, value = marker.read_text(encoding="utf-8").strip().split(":", 1)
            except (OSError, ValueError):
                return None
            if prefix != "gitdir":
                return None
            git_directory = Path(value.strip())
            if not git_directory.is_absolute():
                git_directory = marker.parent / git_directory
            return git_directory.resolve(strict=False)
    return None


def _git_common_directory(git_directory: Path) -> Path:
    common_marker = git_directory / "commondir"
    if common_marker.is_file():
        try:
            common = Path(common_marker.read_text(encoding="utf-8").strip())
        except OSError:
            return git_directory
        if not common.is_absolute():
            common = git_directory / common
        return common.resolve(strict=False)
    return git_directory.resolve(strict=False)


def current_git_branch(workspace_root: str, cwd: str) -> str:
    """Read the current branch only when ``cwd`` belongs to this repository."""

    root = Path(workspace_root).resolve()
    working_directory = Path(cwd)
    if not working_directory.is_absolute():
        working_directory = root / working_directory
    root_git = _git_directory(root)
    cwd_git = _git_directory(working_directory)
    if root_git is None or cwd_git is None:
        raise ValueError("Git capability requires a repository worktree")
    if _git_common_directory(root_git) != _git_common_directory(cwd_git):
        raise ValueError("Git capability cannot cross the repository boundary")
    try:
        head = (cwd_git / "HEAD").read_text(encoding="utf-8").strip()
    except OSError as exc:
        raise ValueError("Cannot resolve the Git branch for the capability") from exc
    prefix = "ref: refs/heads/"
    if not head.startswith(prefix):
        raise ValueError("Detached HEAD is outside the autonomous Git capability")
    return _safe_branch(head[len(prefix) :])


def normalize_hook_input(host: str, payload: Mapping[str, Any]) -> NormalizedHookInput:
    """Translate a Claude, AGY, or Codex PreToolUse payload.

    Missing optional fields are represented by empty strings/tuples.  An
    unsupported host or non-object payload is rejected instead of being
    silently treated as an allow decision by downstream policy code.
    """

    normalized_host = host.strip().lower()
    if normalized_host not in HOOK_HOSTS:
        choices = ", ".join(HOOK_HOSTS)
        raise ValueError(f"unknown hook host {host!r}; expected one of: {choices}")
    if not isinstance(payload, Mapping):
        raise TypeError("hook payload must be an object")

    if normalized_host == "agy":
        call = _mapping(payload.get("toolCall"))
        tool_name = _text(call.get("name"))
        tool_input = _mapping(call.get("args"))
        session_id = _text(payload.get("conversationId"))
    else:
        tool_name = _text(payload.get("tool_name") or payload.get("tool"))
        tool_input = _mapping(payload.get("tool_input") or payload.get("input"))
        session_id = _text(payload.get("session_id") or payload.get("sessionId"))

    lowered_tool = tool_name.lower()
    command = ""
    paths: tuple[str, ...] = ()
    if lowered_tool in _SHELL_TOOLS:
        tool_kind = "shell"
        command = _text(
            tool_input.get("command")
            or tool_input.get("CommandLine")
            or tool_input.get("command_line")
        )
    elif lowered_tool in _PATCH_TOOLS:
        tool_kind = "patch"
        command = _text(
            tool_input.get("command")
            or tool_input.get("patch")
            or tool_input.get("input")
        )
        paths = extract_patch_paths(command)
    elif lowered_tool in _WRITE_TOOLS:
        tool_kind = "write"
        paths = _deduplicate(_nested_paths(tool_input))
    else:
        tool_kind = "other"
        paths = _deduplicate(_nested_paths(tool_input))

    return NormalizedHookInput(
        host=normalized_host,
        session_id=session_id,
        tool_kind=tool_kind,
        command=command,
        target_paths=paths,
    )


def serialize_hook_verdict(host: str, verdict: HookVerdict) -> HookExecution:
    """Serialize one policy verdict using a host's native hook protocol."""

    normalized_host = host.strip().lower()
    if normalized_host not in HOOK_HOSTS:
        raise ValueError(f"unknown hook host {host!r}")
    reason = verdict.reason.strip()
    if normalized_host == "agy":
        payload = {
            "decision": "allow" if verdict.allow else "deny",
            "reason": reason,
        }
        return HookExecution(exit_code=0, stdout=json.dumps(payload, sort_keys=True) + "\n")
    if verdict.allow:
        return HookExecution(exit_code=0)
    return HookExecution(exit_code=2, stderr=(reason or "Blocked by Solomon policy") + "\n")


def serialize_session_context(
    host: str,
    context: str,
    *,
    invocation_number: Optional[int] = None,
) -> HookExecution:
    """Serialize session-resume context for the three lifecycle protocols."""

    normalized_host = host.strip().lower()
    if normalized_host not in HOOK_HOSTS:
        raise ValueError(f"unknown hook host {host!r}")
    if normalized_host == "agy":
        steps = []
        if invocation_number in (None, 0) and context:
            steps.append({"ephemeralMessage": context})
        return HookExecution(
            exit_code=0,
            stdout=json.dumps({"injectSteps": steps}, sort_keys=True) + "\n",
        )
    return HookExecution(exit_code=0, stdout=context)
