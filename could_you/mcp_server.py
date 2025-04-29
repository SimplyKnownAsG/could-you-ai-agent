from typing import Dict, List, Optional
from mcp import ClientSession, StdioServerParameters, Tool
from contextlib import AsyncExitStack
from mcp.client.stdio import stdio_client


class MCPServer:
    tools: List[Tool]

    def __init__(
        self, *, name: str, command: str, args: List[str], env: Optional[Dict[str, str]] = None
    ):
        """
        Initialize an MCPServer instance.

        Args:
            name (str): Name of the server.
            command (str): Command to execute the server.
            args (List[str]): List of arguments for the command.
            env (Optional[Dict[str, str]]): Environment variables for the process.
        """
        self.name = name
        self.command = command
        self.args = args
        self.env = env or {}

    async def connect(self, *, exit_stack: AsyncExitStack) -> bool:
        server_params = StdioServerParameters(command=self.command, args=self.args, env=self.env)
        the_client = await exit_stack.enter_async_context(stdio_client(server_params))
        stdio, write = the_client
        self.session = await exit_stack.enter_async_context(ClientSession(stdio, write))

        await self.session.initialize()

        # List available tools
        response = await self.session.list_tools()
        self.tools = response.tools
        print(f"Connected to {self.name} server with tools:", [tool.name for tool in self.tools])
        return True
