from contextlib import AsyncExitStack
from typing import TYPE_CHECKING

from .config import Config
from .cy_error import CYError, FaultOwner
from .llm import BaseLLM, create_llm
from .logging_config import LOGGER
from .message import Content, Message, ToolResult
from .message_history import MessageHistory

if TYPE_CHECKING:
    from .mcp_server import MCPServer, MCPTool


class Agent:
    def __init__(self, *, config: Config, message_history: MessageHistory):
        # Initialize session and client objects
        self.servers: list[MCPServer] = config.servers
        self.exit_stack = AsyncExitStack()
        self.config = config
        self.message_history = message_history
        self.llm: BaseLLM | None = None
        self.tools: dict[str, MCPTool] = {}

    async def __aenter__(self):
        # TODO: should this use asyncio.create_task or TaskGroup?
        for s in self.servers:
            await s.connect(exit_stack=self.exit_stack)

            for t in s.tools:
                # Only register enabled tools
                if not t.enabled:
                    continue

                old_tool = self.tools.get(t.name, None)

                if old_tool:
                    LOGGER.warning(
                        f"Duplicate {t.name} tool found, using {s.name} version instead of {old_tool.server.name}."
                    )

                self.tools[t.name] = t

        self.llm = create_llm(self.config, self.message_history, self.tools)
        return self

    async def __aexit__(self, *args):
        """Clean up resources"""
        await self.exit_stack.aclose()

    async def orchestrate(self, query: str) -> None:
        """
        Process a user query through the LLM and handle any tool calls.

        Args:
            query: The user's input query
        """
        if not self.llm:
            raise CYError(message="Must __aenter__ to play!", retriable=False, fault_owner=FaultOwner.INTERNAL)

        self.message_history.add(Message(role="user", content=[Content(text=query, type="text")]))
        should_continue = True

        while should_continue:
            should_continue = False
            output_message = await self.llm.converse()
            self.message_history.add(output_message)

            for content in output_message.content:
                tool_use = content.tool_use

                if not tool_use:
                    continue

                should_continue = True
                tool_content: list[Content] = []

                if tool := self.tools.get(tool_use.name, None):
                    try:
                        tool_response = await tool(tool_use.input.to_dict())
                        tool_content.append(
                            Content(
                                toolResult=ToolResult(
                                    toolUseId=tool_use.tool_use_id,
                                    content=[dict(text=c.text) for c in tool_response.content],
                                    status="success",
                                )
                            )
                        )

                    except Exception as err:
                        tool_content.append(
                            Content(
                                toolResult=ToolResult(
                                    toolUseId=tool_use.tool_use_id,
                                    content=[Content(text=f"Error: {err!s}")],
                                    status="error",
                                )
                            )
                        )

                else:
                    LOGGER.warning(f"LLM attempted to call tool that is not registerd: {tool_use.name}")
                    tool_content.append(
                        Content(
                            toolResult=ToolResult(
                                toolUseId=tool_use.tool_use_id,
                                content=[Content(text=f'Error: No tool named "{tool_use.name}".')],
                                status="error",
                            )
                        )
                    )

                tool_message = Message(role="user", content=tool_content)
                self.message_history.add(tool_message)
