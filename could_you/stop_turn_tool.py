from typing import Any

from mcp import Tool
from mcp.types import CallToolResult, TextContent

from .config import MCPServerProps
from .mcp_server import MCPServer, MCPTool


class StopTurnTool(Tool):
    async def __call__(self, tool_args: dict[str, Any]):  # noqa: ARG002
        return CallToolResult(content=[TextContent(tyoe="text", text="Stopping assistant turn")])


# XXX: this does not actually get used, the two __call__ methods short circuit the whole thing.
RESPONSE = '{"jsonrpc":"2.0","id":1,"result":{"tools":[{"name":"__stop_turn__","title":"stop turn","description":"Stop own turn. If you must call a tool, call this, and only this, to stopyour turn","inputSchema":{}}],"nextCursor":null}}'


class MCPStopTurnTool(MCPTool):
    def __init__(self):
        super().__init__(
            # XXX: this does not actually get used, the two __call__ methods short circuit the whole thing.
            MCPServer(name="__self__", props=MCPServerProps(command="echo", args=[RESPONSE])),
            StopTurnTool(
                name="__stop_turn__",
                description="Stop own turn. If you must call a tool, call this, and only this, to stop your turn",
                input_schema={},
            ),
        )

    async def __call__(self, tool_args: dict[str, Any]):  # noqa: ARG002
        return CallToolResult(content=[TextContent(tyoe="text", text="Stopping assistant turn")])
