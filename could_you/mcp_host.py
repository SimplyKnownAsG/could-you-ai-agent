from contextlib import AsyncExitStack
from typing import Optional, List, Dict, Tuple

import boto3
from mcp import ClientSession, Tool

from .config import Config
from .message import Content, Message, ToolUse, ToolResult
from .mcp_server import MCPServer
from .message_history import MessageHistory


class MCPHost:
    def __init__(self, *, config: Config, message_history: MessageHistory):
        # Initialize session and client objects
        self.servers: List[MCPServer] = config.servers
        self.session: Optional[ClientSession] = None
        self.exit_stack = AsyncExitStack()
        self.config = config
        self.tools: Dict[str, Tuple[MCPServer, Tool]] = {}
        self.message_history = message_history

    async def __aenter__(self):
        # TODO: should this use asyncio.create_task or TaskGroup?
        for s in self.servers:
            await s.connect(exit_stack=self.exit_stack)

            for t in s.tools:
                old_server, old_tool = self.tools.get(t.name, (None, None))
                if old_server and old_tool:
                    print(
                        f"warning: duplicate {t.name} tool found. using {s.name} version instead of {old_server.name}"
                    )
                self.tools[t.name] = (s, t)

        return self

    async def __aexit__(self, *args):
        """Clean up resources"""
        await self.exit_stack.aclose()

    async def process_query_aws(self, query: str):
        self.message_history.add(Message(role="user", content=[Content(text=query)]))
        bedrock = boto3.client("bedrock-runtime")
        # Prepare the request for Nova Pro model
        system = [{"text": self.config.prompt}]
        should_continue = True

        while should_continue:
            should_continue = False
            response = bedrock.converse(
                modelId=self.config.llm["model"],
                messages=self.message_history.to_dict(),
                system=system,
                inferenceConfig={"topP": 0.1, "temperature": 0.3},
                toolConfig=convert_tools_for_bedrock([t[1] for t in self.tools.values()]),
            )
            output_message = Message(response["output"]["message"])
            self.message_history.add(output_message)

            for content in output_message.content:
                tool_use = content.tool_use

                if not tool_use:
                    continue

                should_continue = True
                server = self.tools[tool_use.name][0]
                tool_content: List[Content] = []

                try:
                    tool_response = await server.call_tool(tool_use.name, tool_use.input.to_dict())
                    tool_content.append(
                        Content(
                            toolResult=ToolResult(
                                toolUseId=tool_use.tool_use_id,
                                # XXX: not always text!
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
                                content=[Content(text=f"Error: {str(err)}")],
                                status="error",
                            )
                        )
                    )

                tool_message = Message(role="user", content=tool_content)
                self.message_history.add(tool_message)

    async def chat_loop(self, query: str):
        """Run an interactive chat loop"""
        try:
            await self.process_query_aws(query)

        except Exception as e:
            print(f"\nError: {str(e)}")


def convert_tools_for_bedrock(tools: List[Tool]):
    converted_tools = []

    for tool in tools:
        converted_tool = {
            "toolSpec": {
                "name": tool.name,
                "description": tool.description,
                "inputSchema": {"json": tool.inputSchema},
            }
        }
        converted_tools.append(converted_tool)

    return {"tools": converted_tools}
