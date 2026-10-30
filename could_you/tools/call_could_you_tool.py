from typing import Any

from mcp import Tool

from could_you.message import Message, TextContent, ToolResult, ToolResultContent, ToolResultInnerTextContent, ToolUse
from could_you.session import SessionManager

from ..config import MCPServerProps
from ..cy_error import CYError, FaultOwner
from ..mcp_server import MCPServer, MCPTool


class CallCouldYouTool(MCPTool):
    def __init__(self, session_manager: SessionManager):
        super().__init__(
            # XXX: this does not actually get used, the two __call__ methods short circuit the whole thing.
            MCPServer(name="__self__", props=MCPServerProps(command="echo", args=["call tool"])),
            Tool(
                name="__call_could_you__",
                description="Call a sub-agent. Sub-agent will have separate memory, same directory, and same Config. Only final message is returned.",
                input_schema={
                    "type": "object",
                    "properties": {
                        "message": {"type": "string", "description": "request to the sub-agent"},
                        "dialogue_name": {
                            "type": "string",
                            "description": "dialogue-name-used-as-suffix-short-snake-case",
                        },
                    },
                    "required": ["message", "dialogue_name"],
                },
            ),
        )
        self.session_manager = session_manager

    async def __call__(self, tool_use: ToolUse, tool_args: dict[str, Any]):
        # oh, ye most evil in-method import! Why, why must you be here?
        # surely, I have not done such horrible wrongs as to require this!
        from could_you.agent import Agent  # noqa: PLC0415

        dialogue_name = tool_args["dialogue_name"]
        message = tool_args["message"]
        if not isinstance(dialogue_name, str) or not dialogue_name or not isinstance(message, str) or not message:
            raise CYError(
                message="__call_could_you__ expects nonempty string 'dialogue_name' and 'message'",
                retriable=False,
                fault_owner=FaultOwner.LLM,
            )

        session = self.session_manager.load_session(None)
        session.config.dialogue.name = dialogue_name

        with session.dialogue() as dialogue:
            prior_count = len(dialogue.messages)
            async with Agent(session_manager=self.session_manager, config=session.config, dialogue=dialogue) as agent:
                await agent.orchestrate(message)

            # A tool result must contain provider-compatible text, not a nested
            # Message. Only return an assistant answer produced by this invocation.
            final_message = dialogue.messages[-1] if len(dialogue.messages) > prior_count else None
            if not isinstance(final_message, Message) or final_message.role != "assistant":
                raise CYError(
                    message="Sub-agent ended without a final assistant message",
                    retriable=False,
                    fault_owner=FaultOwner.LLM,
                )
            texts = [content.text for content in final_message.content if isinstance(content, TextContent)]
            if not texts:
                raise CYError(
                    message="Sub-agent ended without a text response",
                    retriable=False,
                    fault_owner=FaultOwner.LLM,
                )
            return ToolResultContent(
                toolResult=ToolResult(
                    toolUseId=tool_use.tool_use_id,
                    content=[ToolResultInnerTextContent(text="\n\n".join(texts))],
                    status="success",
                )
            )
