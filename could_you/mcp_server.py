from typing import Dict, List, Optional, Any, Set
from mcp import ClientSession, StdioServerParameters, Tool
from contextlib import AsyncExitStack
from mcp.client.stdio import stdio_client
from .logging_config import LOGGER



class MCPTool:
    """Wrapper for MCP Tool with enabled/disabled status awareness."""

    def __init__(self, tool: Tool, enabled: bool = True):
        self.tool = tool
        self.enabled = enabled

    @property
    def name(self) -> str:
        return self.tool.name

    @property
    def description(self) -> str | None:
        return self.tool.description

    @property
    def inputSchema(self):
        return self.tool.inputSchema

    def __getattr__(self, name):
        # Delegate any other attribute access to the underlying tool
        return getattr(self.tool, name)


class MCPServer:
    tools: List[MCPTool]
    enabled: bool
    disabled_tools: Set[str]

    def __init__(
        self,
        *,
        name: str,
        command: str,
        args: List[str],
        env: Optional[Dict[str, str]] = None,
        enabled: bool = True,
        disabled_tools: Optional[List[str]] = None,
    ):
        """
        Initialize an MCPServer instance.

        Args:
            name (str): Name of the server.
            command (str): Command to execute the server.
            args (List[str]): List of arguments for the command.
            env (Optional[Dict[str, str]]): Environment variables for the process.
            enabled (bool): Option to enable/disable the server.
            disabled_tools (Optional[List[str]]): List of tool names to disable.
        """
        self.name = name
        self.command = command
        self.args = args
        self.env = env or {}
        self.enabled = enabled
        self.disabled_tools = set(disabled_tools or [])

    async def connect(self, *, exit_stack: AsyncExitStack) -> bool:
        if self.enabled:
            server_params = StdioServerParameters(
                command=self.command, args=self.args, env=self.env
            )
            the_client = await exit_stack.enter_async_context(stdio_client(server_params))
            stdio, write = the_client
            self.session = await exit_stack.enter_async_context(ClientSession(stdio, write))

            await self.session.initialize()

            # List available tools
            response = await self.session.list_tools()

            # Create MCPTool wrappers with enabled/disabled status
            self.tools = []
            for tool in response.tools:
                enabled = tool.name not in self.disabled_tools
                mcp_tool = MCPTool(tool, enabled=enabled)
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

    async def call_tool(self, tool_name: str, tool_args: Dict[str, Any]):
        return await self.session.call_tool(tool_name, tool_args)
