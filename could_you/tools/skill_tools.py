"""Local model tools for Agent Skills."""

from typing import Any

from mcp import Tool

from ..config import MCPServerProps
from ..mcp_server import MCPServer, MCPTool
from ..message import ToolResult, ToolResultContent, ToolResultInnerTextContent, ToolUse
from ..skills import SkillError, SkillRegistry


def _result(tool_use: ToolUse, text: str, status: str = "success") -> ToolResultContent:
    return ToolResultContent(
        toolResult=ToolResult(
            toolUseId=tool_use.tool_use_id,
            content=[ToolResultInnerTextContent(text=text)],
            status=status,
        )
    )


class SkillTool(MCPTool):
    def __init__(self, registry: SkillRegistry, *, name: str, description: str, extra: dict, required: list[str]):
        self.registry = registry
        super().__init__(
            MCPServer(name="__self__", props=MCPServerProps(command="echo")),
            Tool(
                name=name,
                description=description,
                input_schema={
                    "type": "object",
                    "properties": {"skill_name": {"type": "string", "enum": sorted(registry.skills)}, **extra},
                    "required": ["skill_name", *required],
                },
            ),
        )

    def _arguments(self, args: Any, required: dict[str, type]) -> dict:
        if not isinstance(args, dict):
            raise SkillError("Tool arguments must be an object")
        if set(args) != {"skill_name", *required}:
            raise SkillError(f"Expected arguments: skill_name, {', '.join(required)}")
        if not isinstance(args["skill_name"], str):
            raise SkillError("skill_name must be a string")
        for key, expected in required.items():
            if not isinstance(args[key], expected):
                raise SkillError(f"{key} must be {expected.__name__}")
        return args


class LoadSkillTool(SkillTool):
    def __init__(self, registry: SkillRegistry):
        super().__init__(
            registry,
            name="load_skill",
            description=registry.load_skill_description(),
            extra={},
            required=[],
        )

    async def __call__(self, tool_use: ToolUse, tool_args: dict[str, Any]):
        try:
            args = self._arguments(tool_args, {})
            return _result(tool_use, self.registry.load_skill(args["skill_name"]))
        except (SkillError, OSError, UnicodeError) as exc:
            return _result(tool_use, f"Error: {exc}", "error")


class LoadSkillResourceTool(SkillTool):
    def __init__(self, registry: SkillRegistry):
        super().__init__(
            registry,
            name="load_skill_resource",
            description="Read a UTF-8 reference or asset file from a skill. path must start with references/ or assets/.",
            extra={"path": {"type": "string", "description": "Relative path such as references/guide.md"}},
            required=["path"],
        )

    async def __call__(self, tool_use: ToolUse, tool_args: dict[str, Any]):
        try:
            args = self._arguments(tool_args, {"path": str})
            return _result(tool_use, self.registry.load_resource(args["skill_name"], args["path"]))
        except (SkillError, OSError, UnicodeError) as exc:
            return _result(tool_use, f"Error: {exc}", "error")


class RunSkillScriptTool(SkillTool):
    def __init__(self, registry: SkillRegistry):
        super().__init__(
            registry,
            name="run_skill_script",
            description="Execute an executable script from scripts/ as the current OS user, without a shell. No sandbox.",
            extra={
                "script_name": {"type": "string", "description": "Relative path e.g. scripts/check.sh"},
                "args": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Argument vector, not a shell command",
                },
            },
            required=["script_name", "args"],
        )

    async def __call__(self, tool_use: ToolUse, tool_args: dict[str, Any]):
        try:
            args = self._arguments(tool_args, {"script_name": str, "args": list})
            return _result(
                tool_use,
                await self.registry.run_script(args["skill_name"], args["script_name"], args["args"]),
            )
        except (SkillError, OSError, UnicodeError, TimeoutError) as exc:
            return _result(tool_use, f"Error: {exc or 'Script timed out'}", "error")
