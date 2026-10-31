import json
from typing import Any

from mcp import Tool

from could_you.message import ToolUse
from could_you.session import SessionManager

from ..config import MCPServerProps
from ..cy_error import CYError, FaultOwner
from ..mcp_server import MCPServer, MCPTool
from .call_could_you_tool import _text_result


class PollCouldYouTool(MCPTool):
    def __init__(self, session_manager: SessionManager):
        super().__init__(
            MCPServer(name="__self__", props=MCPServerProps(command="echo", args=["poll tool"])),
            Tool(
                name="__poll_could_you__",
                description="Poll an async sub-agent job. Returns pending, succeeded with final text, or failed with error.",
                input_schema={
                    "type": "object",
                    "properties": {
                        "job_id": {"type": "string", "description": "Job id returned by __call_could_you__"}
                    },
                    "required": ["job_id"],
                },
            ),
        )
        self.session_manager = session_manager

    async def __call__(self, tool_use: ToolUse, tool_args: dict[str, Any]):
        if not isinstance(tool_args, dict):
            raise CYError(message="Expected polling arguments object", retriable=False, fault_owner=FaultOwner.LLM)
        return _text_result(tool_use, json.dumps(self.session_manager.jobs.poll(tool_args.get("job_id"))))
