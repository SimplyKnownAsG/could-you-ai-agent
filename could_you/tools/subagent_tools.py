"""Sub-agent tools and in-process jobs shared by an agent and its descendants."""

from __future__ import annotations

import asyncio
import json
import uuid
from typing import TYPE_CHECKING, Any, Literal

from mcp import Tool

from ..config import Config, MCPServerProps, SubagentProps
from ..cy_error import CYError, FaultOwner
from ..logging_config import LOGGER
from ..mcp_server import MCPServer, MCPTool
from ..message import Message, TextContent, ToolResult, ToolResultContent, ToolResultInnerTextContent, ToolUse

if TYPE_CHECKING:
    from collections.abc import Awaitable

    from ..session import SessionManager


class SubagentServer:
    def __init__(self, subagent_props: SubagentProps, depth: int):
        self.props = subagent_props
        self.depth = depth
        self.tasks: dict[str, asyncio.Task[str]] = {}
        self.closed = False

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_value, traceback):
        await self.close()

    def create_tools(self, session_manager: SessionManager):
        if not self.props.enabled or self.depth >= self.props.max_depth:
            return []
        return [CallSubagentTool(self, session_manager), PollSubagentTool(self)]

    async def close(self):
        if self.closed:
            return

        self.closed = True
        # Cancelling a parent can start a descendant in its cancellation handler.
        # Repeat until every task in the shared registry has finished.
        while pending := [task for task in self.tasks.values() if not task.done()]:
            for task in pending:
                task.cancel()
            await asyncio.gather(*pending, return_exceptions=True)

        # Retrieve failures even when nobody polled the job.
        for job_id, task in self.tasks.items():
            if task.cancelled():
                continue
            error = task.exception()
            if error is not None:
                LOGGER.warning("Sub-agent job %s failed: %s", job_id, error)

    def start(self, work: Awaitable[str]) -> str:
        if self.closed:
            if hasattr(work, "close"):
                work.close()
            raise CYError(message="Sub-agent jobs are closing", retriable=False, fault_owner=FaultOwner.INTERNAL)
        job_id = uuid.uuid4().hex
        task = asyncio.create_task(work)
        self.tasks[job_id] = task
        return job_id

    def poll(self, job_id: str) -> str:
        if not isinstance(job_id, str) or not job_id:
            raise CYError(message="Expected nonempty string 'job_id'", retriable=False, fault_owner=FaultOwner.LLM)
        task = self.tasks.get(job_id)
        if task is None:
            return _format_response(status="failed", text=f"Unknown sub-agent job id: {job_id}")
        if not task.done():
            return _format_response(status="pending")
        try:
            return _format_response(status="success", text=task.result())
        except asyncio.CancelledError:
            return _format_response(status="failed", text="Sub-agent job was cancelled")
        except Exception as err:
            return _format_response(status="failed", text=str(err))


def _format_response(*, status: Literal["failed", "pending", "success"], text: str = ""):
    response = f"status: {status}"

    if text:
        if status == "failed":
            response += f"\nerror: {text}"
        else:
            response += f"\n\n{text}"

    return response


def _text_result(tool_use: ToolUse, text: str) -> ToolResultContent:
    return ToolResultContent(
        toolResult=ToolResult(
            toolUseId=tool_use.tool_use_id,
            content=[ToolResultInnerTextContent(text=text)],
            status="success",
        )
    )


class CallSubagentTool(MCPTool):
    def __init__(self, subagent_server: SubagentServer, session_manager: SessionManager):
        self.subagent_server = subagent_server
        self.session_manager = session_manager
        self.depth = subagent_server.depth
        super().__init__(
            MCPServer(name="__self__", props=MCPServerProps(command="echo", args=["call tool"])),
            Tool(
                name="__call_subagent__",
                description="Call a sub-agent. Separate memory, same directory and Config. With async=true returns a job id to poll; otherwise returns only the final message.",
                input_schema={
                    "type": "object",
                    "properties": {
                        "message": {"type": "string", "description": "request to the sub-agent"},
                        "dialogue_name": {
                            "type": "string",
                            "description": "dialogue-name-used-as-suffix-short-snake-case",
                        },
                        "dialogue_load": {
                            "type": "boolean",
                            "description": "Load previous conversation that used this same dialogue_name, if it exists. Default is True",
                        },
                        "async": {"type": "boolean", "description": "Return a job id immediately instead of waiting"},
                    },
                    "required": ["message", "dialogue_name"],
                },
            ),
            enabled=True,
        )

    async def __call__(self, tool_use: ToolUse, tool_args: dict[str, Any]):
        if not isinstance(tool_args, dict):
            raise CYError(message="Expected sub-agent arguments object", retriable=False, fault_owner=FaultOwner.LLM)

        dialogue_name = tool_args.get("dialogue_name")
        dialogue_load = tool_args.get("dialogue_load", True)
        message = tool_args.get("message")
        async_mode = tool_args.get("async", False)

        if not isinstance(dialogue_name, str) or not dialogue_name or not isinstance(message, str) or not message:
            raise CYError(
                message="__call_subagent__ expects nonempty string 'dialogue_name' and 'message'",
                retriable=False,
                fault_owner=FaultOwner.LLM,
            )

        if not isinstance(async_mode, bool):
            raise CYError(message="'async' must be a boolean", retriable=False, fault_owner=FaultOwner.LLM)

        if not isinstance(dialogue_load, bool):
            raise CYError(message="'dialogue_load' must be a boolean", retriable=False, fault_owner=FaultOwner.LLM)

        if async_mode:
            job_id = self.subagent_server.start(
                self._run(dialogue_name=dialogue_name, dialogue_load=dialogue_load, message=message)
            )
            return _text_result(tool_use, json.dumps({"job_id": job_id}))

        return _text_result(
            tool_use, await self._run(dialogue_name=dialogue_name, dialogue_load=dialogue_load, message=message)
        )

    async def _run(self, *, dialogue_name: str, dialogue_load: bool, message: str) -> str:
        # Deferred import avoids circular dependency with Agent registering this tool.
        from could_you.agent import Agent  # noqa: PLC0415

        def __override_config(config: Config):
            config.dialogue.name = dialogue_name
            config.dialogue.load = dialogue_load

        async with self.session_manager.load_session(None, __override_config, depth=self.depth + 1) as session:
            dialogue = session.dialogue
            prior_count = len(dialogue.messages)
            async with Agent(session_manager=self.session_manager, session=session) as agent:
                agent.dialogue = dialogue
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


class PollSubagentTool(MCPTool):
    def __init__(self, subagent_server: SubagentServer):
        self.subagent_server = subagent_server
        super().__init__(
            MCPServer(name="__self__", props=MCPServerProps(command="echo", args=["poll tool"])),
            Tool(
                name="__poll_subagent__",
                description="Poll an async sub-agent job. Returns pending, success with final text, or failed with error.",
                input_schema={
                    "type": "object",
                    "properties": {"job_id": {"type": "string", "description": "Job id returned by __call_subagent__"}},
                    "required": ["job_id"],
                },
            ),
            enabled=True,
        )

    async def __call__(self, tool_use: ToolUse, tool_args: dict[str, Any]):
        if not isinstance(tool_args, dict):
            raise CYError(message="Expected polling arguments object", retriable=False, fault_owner=FaultOwner.LLM)

        job_id = tool_args.get("job_id")

        if not job_id:
            raise CYError(
                message=f"Expected job_id to be truthy, got '{job_id}'", retriable=False, fault_owner=FaultOwner.LLM
            )

        return _text_result(tool_use, self.subagent_server.poll(job_id))
