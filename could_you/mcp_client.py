from typing import Optional, List, Dict, Tuple
from contextlib import AsyncExitStack
import asyncio

from mcp import ClientSession, Tool

from anthropic import Anthropic
from .mcp_server import MCPServer


class MCPClient:
    def __init__(self, *, servers: List[MCPServer]):
        # Initialize session and client objects
        self.servers: List[MCPServer] = servers
        self.session: Optional[ClientSession] = None
        self.exit_stack = AsyncExitStack()
        self.anthropic = Anthropic()
        self.tools: Dict[str, Tuple[str, Tool]] = {}

    async def __aenter__(self):
        # TODO: should this use create_task or TaskGroup?
        for s in self.servers:
            await s.connect(exit_stack=self.exit_stack)

        tool_dict: Dict[str, Tuple[str, Tool]] = {}

        for s in self.servers:
            for t in s.tools:
                old_server_name, old_tool = tool_dict.get(t.name, (None, None))
                if old_server_name and old_tool:
                    print(
                        f"warning: duplicate {t.name} tool found. using {s.name} version instead of {old_server_name}"
                    )
                tool_dict[t.name] = (s.name, t)

        return self

    async def __aexit__(self, *args):
        """Clean up resources"""
        await self.exit_stack.aclose()

    async def process_query(self, query: str) -> str:
        """Process a query using Claude and available tools"""
        messages = [{"role": "user", "content": query}]

        # Initial Claude API call
        response = self.anthropic.messages.create(
            model="claude-3-5-sonnet-20241022",
            max_tokens=1000,
            messages=messages,
            tools=self.tools.values(),
        )

        # Process response and handle tool calls
        tool_results = []
        final_text = []

        for content in response.content:
            if content.type == "text":
                final_text.append(content.text)
            elif content.type == "tool_use":
                tool_name = content.name
                tool_args = content.input

                # Execute tool call
                result = await self.session.call_tool(tool_name, tool_args)
                tool_results.append({"call": tool_name, "result": result})
                final_text.append(f"[Calling tool {tool_name} with args {tool_args}]")

                # Continue conversation with tool results
                if hasattr(content, "text") and content.text:
                    messages.append({"role": "assistant", "content": content.text})
                messages.append({"role": "user", "content": result.content})

                # Get next response from Claude
                response = self.anthropic.messages.create(
                    model="claude-3-5-sonnet-20241022",
                    max_tokens=1000,
                    messages=messages,
                )

                final_text.append(response.content[0].text)

        return "\n".join(final_text)

    async def chat_loop(self, query: str):
        """Run an interactive chat loop"""
        try:
            response = await self.process_query(query)
            print("\n" + response)

        except Exception as e:
            print(f"\nError: {str(e)}")
