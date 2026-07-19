"""Claude-native rendering, merge, and capability inspection adapter."""

from typing import Any

from solomon_harness.host_adapter_common import (
    CAPABILITIES,
    HostCompileContext,
    HostInspectionContext,
    _Workflow,
    _frontmatter_value,
    _hook_handler,
    _instruction_is_valid,
    _merge_list_hooks,
    _merge_mcp_json,
    _read_text,
    _single_line,
    _skill_names,
    _specialist_markdown,
    _specialist_names,
    _valid_hooks,
    _valid_json_mcp,
    _workflow_skill,
    _write_marker_file,
)
from solomon_harness.host_adapter_contract import HostInspection


def _hook_specs(context: HostCompileContext | HostInspectionContext) -> dict[str, dict[str, Any]]:
    return {
        "SessionStart": {
            "hooks": [_hook_handler("claude", "session-start", context.runtime)]
        },
        "PreToolUse": {
            "hooks": [_hook_handler("claude", "pre-tool-use", context.runtime)],
            "matcher": "Bash|Edit|Write|MultiEdit|NotebookEdit",
        },
    }


def _allowed_tools(workflow: _Workflow, context: HostCompileContext) -> str:
    name = f"solomon-{workflow.name}.md"
    candidates = (
        context.paths.solomon / "host-metadata" / "claude" / "commands" / name,
        context.paths.legacy_workflows / name,
    )
    for candidate in candidates:
        text = _read_text(candidate)
        if text is None:
            continue
        value = _frontmatter_value(text, "allowed-tools")
        if value:
            return _single_line(value, "")
    return ""


class ClaudeAdapter:
    """Native Claude adapter behind the shared host port."""

    name = "claude"

    def compile(self, context: HostCompileContext) -> None:
        if not isinstance(context, HostCompileContext):
            raise TypeError("Claude compile context is invalid")

        _write_marker_file(
            context.recorder,
            context.paths.claude_instructions,
            f"@../{context.rules.relative_to(context.root).as_posix()}",
        )
        for specialist in context.specialists:
            context.recorder.write_generated(
                context.paths.claude_agents / f"{specialist.name}.md",
                _specialist_markdown(
                    specialist,
                    root=context.root,
                    rules=context.rules,
                ),
            )
        for workflow in context.workflows:
            directory = f"solomon-{workflow.name}"
            context.recorder.write_generated(
                context.paths.claude_skills / directory / "SKILL.md",
                _workflow_skill(
                    workflow,
                    context.root,
                    allowed_tools=_allowed_tools(workflow, context),
                ),
            )
        _merge_list_hooks(
            context.recorder,
            context.paths.claude_settings,
            self.name,
            _hook_specs(context),
        )
        _merge_mcp_json(
            context.recorder,
            context.paths.claude_mcp,
            context.runtime,
            context.mcp_command,
        )

    def inspect(self, context: HostInspectionContext) -> HostInspection:
        if not isinstance(context, HostInspectionContext):
            raise TypeError("Claude inspection context is invalid")

        specialists = _specialist_names(
            context.paths.claude_agents,
            self.name,
            context.agents_reference,
        )
        workflows = _skill_names(
            context.paths.claude_skills,
            context.workflow_references,
        )
        states = {capability: "unavailable" for capability in CAPABILITIES}
        states["headless"] = "active"
        if _instruction_is_valid(
            context.paths.claude_instructions,
            self.name,
            context.rules_reference,
        ):
            states["instructions"] = "active"
        if context.expected_specialists and specialists == context.expected_specialists:
            states["specialists"] = "active"
        if context.expected_workflows and workflows == context.expected_workflows:
            states["workflows"] = "active"
        if _valid_hooks(
            context.paths.claude_settings,
            self.name,
            _hook_specs(context),
        ):
            states["session_start"] = "configured"
            states["pre_tool_guard"] = "configured"
        if _valid_json_mcp(
            context.paths.claude_mcp,
            context.root,
            context.runtime,
            context.mcp_command,
        ):
            states["mcp"] = "configured"
        return HostInspection(states, specialists, workflows)


ADAPTER = ClaudeAdapter()
