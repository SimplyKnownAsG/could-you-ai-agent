from contextlib import AsyncExitStack
from typing import Any

from mcp import ClientSession, StdioServerParameters, Tool
from mcp.client.stdio import stdio_client

from .config import MCPServerProps
from .logging_config import LOGGER


class MCPTool:
    """Wrapper for MCP Tool with enabled/disabled status awareness."""

    def __init__(self, server: "MCPServer", tool: Tool, *, enabled: bool = True):
        self.server = server
        self.tool = tool
        self.enabled = enabled

    async def __call__(self, tool_args: dict[str, Any]):
        return await self.server.call_tool(self.name, tool_args)

    def __getattr__(self, name):
        # Delegate any other attribute access to the underlying tool
        return getattr(self.tool, name)


class MCPServer:
    name: str
    props: MCPServerProps
    tools: list[MCPTool]

    def __init__(self, *, name: str, props: MCPServerProps):
        self.name = name
        self.props = props

    async def connect(self, *, exit_stack: AsyncExitStack) -> bool:
        if self.props.enabled:
            server_params = StdioServerParameters(command=self.props.command, args=self.props.args, env=self.props.env)
            the_client = await exit_stack.enter_async_context(stdio_client(server_params))
            stdio, write = the_client
            self.session = await exit_stack.enter_async_context(ClientSession(stdio, write))

            await self.session.initialize()

            # List available tools
            response = await self.session.list_tools()

            # Create MCPTool wrappers with enabled/disabled status
            self.tools = []
            for tool in response.tools:
                enabled = tool.name not in self.props.disabled_tools
                mcp_tool = MCPTool(self, tool, enabled=enabled)
                self.tools.append(mcp_tool)

            # Report enabled tools
            LOGGER.info(f"Connected to {self.name} server with tools:")
            for tool in self.tools:
                suffix = "" if tool.enabled else " (disabled)"
                LOGGER.info(f"    {tool.name}{suffix}")
        else:
            LOGGER.info(f"Server {self.name} is not enabled.")
            self.tools = []

        return True

    async def call_tool(self, tool_name: str, tool_args: dict[str, Any]):
        return await self.session.call_tool(tool_name, tool_args)
