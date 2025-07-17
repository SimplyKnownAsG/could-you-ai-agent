from typing import Dict, List, Optional, Any
from mcp import ClientSession, StdioServerParameters, Tool
from contextlib import AsyncExitStack
from mcp.client.stdio import stdio_client


class MCPServer:
    tools: List[Tool]
    enabled: bool

    def __init__(
        self, *, name: str, command: str, args: List[str], env: Optional[Dict[str, str]] = None,
        enabled: bool = True
    ):
        """
        Initialize an MCPServer instance.

        Args:
            name (str): Name of the server.
            command (str): Command to execute the server.
            args (List[str]): List of arguments for the command.
            env (Optional[Dict[str, str]]): Environment variables for the process.
            enabled (bool): Option to enable/disable the server.
        """
        self.name = name
        self.command = command
        self.args = args
        self.env = env or {}
        self.enabled = enabled

    async def connect(self, *, exit_stack: AsyncExitStack) -> bool:
        if self.enabled:
            server_params = StdioServerParameters(command=self.command, args=self.args, env=self.env)
            the_client = await exit_stack.enter_async_context(stdio_client(server_params))
            stdio, write = the_client
            self.session = await exit_stack.enter_async_context(ClientSession(stdio, write))

            await self.session.initialize()

            # List available tools
            response = await self.session.list_tools()
            self.tools = response.tools
            print(f"Connected to {self.name} server with tools:")

            for tool in self.tools:
                print(f"    {tool.name}")
        else:
            print(f"Server {self.name} is not enabled.")
            self.tools = []

        return True

    async def call_tool(self, tool_name: str, tool_args: Dict[str, Any]):
        return await self.session.call_tool(tool_name, tool_args)
