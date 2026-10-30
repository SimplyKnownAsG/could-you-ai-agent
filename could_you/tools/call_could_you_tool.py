import json
from typing import Any

from mcp import Tool

from could_you.message import Message, TextContent, ToolResult, ToolResultContent, ToolResultInnerTextContent, ToolUse
from could_you.session import SessionManager
from could_you.subagent_jobs import SubagentJobs

from ..config import MCPServerProps
from ..cy_error import CYError, FaultOwner
from ..mcp_server import MCPServer, MCPTool


def _text_result(tool_use: ToolUse, text: str) -> ToolResultContent:
    return ToolResultContent(
        toolResult=ToolResult(
            toolUseId=tool_use.tool_use_id,
            content=[ToolResultInnerTextContent(text=text)],
            status="success",
        )
    )


class CallCouldYouTool(MCPTool):
    def __init__(self, session_manager: SessionManager, jobs: SubagentJobs | None = None):
        super().__init__(
            MCPServer(name="__self__", props=MCPServerProps(command="echo", args=["call tool"])),
            Tool(
                name="__call_could_you__",
                description="Call a sub-agent. Separate memory, same directory and Config. With async=true returns a job id to poll; otherwise returns only the final message.",
                input_schema={
                    "type": "object",
                    "properties": {
                        "message": {"type": "string", "description": "request to the sub-agent"},
                        "dialogue_name": {
                            "type": "string",
                            "description": "dialogue-name-used-as-suffix-short-snake-case",
                        },
                        "async": {"type": "boolean", "description": "Return a job id immediately instead of waiting"},
                    },
                    "required": ["message", "dialogue_name"],
                },
            ),
        )
        self.session_manager = session_manager
        self.jobs = jobs if jobs is not None else SubagentJobs()

    async def __call__(self, tool_use: ToolUse, tool_args: dict[str, Any]):
        if not isinstance(tool_args, dict):
            raise CYError(message="Expected sub-agent arguments object", retriable=False, fault_owner=FaultOwner.LLM)
        dialogue_name = tool_args.get("dialogue_name")
        message = tool_args.get("message")
        async_mode = tool_args.get("async", False)
        if not isinstance(dialogue_name, str) or not dialogue_name or not isinstance(message, str) or not message:
            raise CYError(
                message="__call_could_you__ expects nonempty string 'dialogue_name' and 'message'",
                retriable=False,
                fault_owner=FaultOwner.LLM,
            )
        if not isinstance(async_mode, bool):
            raise CYError(message="'async' must be a boolean", retriable=False, fault_owner=FaultOwner.LLM)

        if async_mode:
            job_id = self.jobs.start(self._run(dialogue_name, message))
            return _text_result(tool_use, json.dumps({"job_id": job_id}))
        return _text_result(tool_use, await self._run(dialogue_name, message))

    async def _run(self, dialogue_name: str, message: str) -> str:
        # Deferred import avoids circular dependency with Agent registering this tool.
        from could_you.agent import Agent  # noqa: PLC0415

        session = self.session_manager.load_session(None)
        session.config.dialogue.name = dialogue_name

        with session.dialogue() as dialogue:
            prior_count = len(dialogue.messages)
            async with Agent(
                session_manager=self.session_manager, config=session.config, dialogue=dialogue, jobs=self.jobs
            ) as agent:
                await agent.orchestrate(message)

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
            return "\n\n".join(texts)
