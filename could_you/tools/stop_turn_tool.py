from typing import Any

from mcp import Tool
from mcp.types import CallToolResult
from mcp.types import TextContent as MCPTextContent

from ..config import MCPServerProps
from ..cy_error import CYError, FaultOwner
from ..mcp_server import MCPServer, MCPTool
from ..message import Message, MessageType, TextContent, ToolUseContent


class StopTurnTool(Tool):
    async def __call__(self, tool_args: dict[str, Any]):  # noqa: ARG002
        return CallToolResult(content=[MCPTextContent(type="text", text="Stopping assistant turn")])


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
                input_schema={
                    "type": "object",
                    "properties": {"message": {"type": "string", "description": "final turn message"}},
                },
            ),
        )

    @staticmethod
    def transform_response(response: Message) -> tuple[bool, Message | None]:
        """Replace a stop call with assistant text, or drop it when no text exists.

        Use ordinary response text and optional tool message, deduplicating only
        exact matches. A stop call must be the only tool call; apply this before
        storing or executing any tool calls.
        """
        stop_calls = [
            content
            for content in response.content
            if isinstance(content, ToolUseContent) and content.tool_use.name == "__stop_turn__"
        ]
        if not stop_calls:
            return False, None

        if len(stop_calls) != 1 or any(
            isinstance(content, ToolUseContent) and content is not stop_calls[0] for content in response.content
        ):
            raise CYError(
                message="__stop_turn__ must be the only tool call in an assistant response",
                retriable=False,
                fault_owner=FaultOwner.LLM,
            )

        tool_input = stop_calls[0].tool_use.input
        if not isinstance(tool_input, dict) or any(key != "message" for key in tool_input):
            raise CYError(
                message="__stop_turn__ expects an optional string 'message'",
                retriable=False,
                fault_owner=FaultOwner.LLM,
            )
        message = tool_input.get("message")
        if message is not None and not isinstance(message, str):
            raise CYError(
                message="__stop_turn__ expects an optional string 'message'",
                retriable=False,
                fault_owner=FaultOwner.LLM,
            )

        # Keep text in response order. Only suppress an identical tool message;
        # don't guess whether similar text is redundant or part of the answer.
        texts = [content.text for content in response.content if isinstance(content, TextContent) and content.text]
        if message and message not in texts:
            texts.append(message)
        if not texts:
            return True, None
        return True, Message(
            role="assistant",
            content=[TextContent(text=text) for text in texts],
            type=MessageType.NORMAL,
            metadata=response.metadata,
        )

    async def __call__(self, tool_args: dict[str, Any]):  # noqa: ARG002
        return CallToolResult(content=[MCPTextContent(type="text", text="Stopping assistant turn")])
