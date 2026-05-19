from contextlib import AsyncExitStack

from cattrs import Converter

from .config import Config
from .cy_error import CYError, FaultOwner
from .dialogue import Dialogue
from .llm import BaseLLM, create_llm
from .logging_config import LOGGER
from .mcp_server import MCPServer, MCPTool
from .memory import current_token_percent_used, should_reject, should_warn
from .message import (
    Content,
    Message,
    MessageType,
    TextContent,
    ToolResult,
    ToolResultContent,
    ToolResultInnerJsonContent,
    ToolResultInnerTextContent,
    ToolUseContent,
)

converter = Converter(use_alias=True, omit_if_default=True)


class Agent:
    def __init__(self, *, config: Config, dialogue: Dialogue):
        # Initialize session and client objects
        self.servers: list[MCPServer] = [
            MCPServer(name=name, props=props) for name, props in config.mcp_servers.items()
        ]
        self.exit_stack = AsyncExitStack()
        self.config = config
        self.dialogue = dialogue
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

        self.llm = create_llm(self.config, self.dialogue, self.tools)
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

        pending_user_message = Message(
            role="user", content=[TextContent(text=query, type="text")], type=MessageType.NORMAL
        )
        added_user_message = False
        should_continue = True

        while should_continue:
            percent_used = current_token_percent_used(self.dialogue.messages)
            if should_reject(percent_used, self.config.memory):
                rejection_message = (
                    f"Memory token usage is {percent_used:.2f}%, at or above the "
                    f"{self.config.memory.rejection_threshold_percent:.2f}% rejection threshold. "
                    "Compact history before sending another query."
                )
                LOGGER.error(rejection_message)
                self.dialogue.add(
                    Message(
                        role="system",
                        content=[TextContent(text=rejection_message, type="text")],
                        type=MessageType.NORMAL,
                    )
                )
                return

            if should_warn(percent_used, self.config.memory):
                LOGGER.warning(
                    "Memory token usage is %.2f%%, at or above the %.2f%% warning threshold. "
                    "Consider compacting history soon.",
                    percent_used,
                    self.config.memory.warning_threshold_percent,
                )

            if not added_user_message:
                added_user_message = True
                self.dialogue.add(pending_user_message)

            llm_message = await self.llm.converse()

            # Determine message type based on content
            message_type = (
                MessageType.TOOL_CALL
                if any(isinstance(content, ToolUseContent) for content in llm_message.content)
                else MessageType.NORMAL
            )

            llm_message.type = message_type
            self.dialogue.add(llm_message)
            should_continue = await self.__use_tools(llm_message)

    async def __use_tools(self, llm_message: Message):
        tool_content: list[Content] = []

        for content in llm_message.content:
            if not isinstance(content, ToolUseContent):
                continue

            tool_use = content.tool_use

            if tool := self.tools.get(tool_use.name, None):
                try:
                    tool_response = await tool(converter.unstructure(tool_use.input))
                    # XXX: I'm not sure why this does not work.
                    # ccc = [converter.structure(c, ToolResultInnerContent) for c in tool_response.content]
                    ccc = []
                    for c in tool_response.content:
                        if hasattr(c, "text"):
                            ccc.append(ToolResultInnerTextContent(text=c.text))
                        elif hasattr(c, "json"):
                            ccc.append(ToolResultInnerJsonContent(json=c.json))
                        else:
                            raise CYError(  # noqa: TRY301
                                message=f"Do not know how to handle response: {c}",
                                retriable=False,
                                fault_owner=FaultOwner.INTERNAL,
                            )

                    tool_content.append(
                        ToolResultContent(
                            toolResult=ToolResult(
                                toolUseId=tool_use.tool_use_id,
                                content=ccc,
                                status="success",
                            )
                        )
                    )

                except CYError:
                    raise

                except Exception as err:
                    tool_content.append(
                        ToolResultContent(
                            toolResult=ToolResult(
                                toolUseId=tool_use.tool_use_id,
                                content=[ToolResultInnerTextContent(text=f"Error: {err!s}")],
                                status="error",
                            )
                        )
                    )

            else:
                LOGGER.warning(f"LLM attempted to call tool that is not registerd: {tool_use.name}")
                tool_content.append(
                    ToolResultContent(
                        toolResult=ToolResult(
                            toolUseId=tool_use.tool_use_id,
                            content=[ToolResultInnerTextContent(text=f'Error: No tool named "{tool_use.name}".')],
                            status="error",
                        )
                    )
                )

        if tool_content:
            tool_message = Message(role="tool", content=tool_content, type=MessageType.TOOL_RESULT)
            self.dialogue.add(tool_message)

        return bool(tool_content)
