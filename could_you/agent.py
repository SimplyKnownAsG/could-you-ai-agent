from contextlib import AsyncExitStack
from typing import Optional, List, Dict

from mcp import ClientSession

from .config import Config
from .mcp_server import MCPServer, MCPTool
from .message_history import MessageHistory
from .llm import create_llm, BaseLLM
from .logging_config import LOGGER


class Agent:
    def __init__(self, *, config: Config, message_history: MessageHistory):
        # Initialize session and client objects
        self.servers: List[MCPServer] = config.servers
        self.session: Optional[ClientSession] = None
        self.exit_stack = AsyncExitStack()
        self.config = config
        self.message_history = message_history
        self.llm: Optional[BaseLLM] = None

    async def __aenter__(self):
        # TODO: should this use asyncio.create_task or TaskGroup?
        tools: Dict[str, MCPTool] = {}

        for s in self.servers:
            await s.connect(exit_stack=self.exit_stack)

            for t in s.tools:
                # Only register enabled tools
                if not t.enabled:
                    continue

                old_tool = tools.get(t.name, None)

                if old_tool:
                    LOGGER.warning(
                        f"Duplicate {t.name} tool found, using {s.name} version instead of {old_tool.server.name}."
                    )

                tools[t.name] = t

        self.llm = create_llm(self.config, self.message_history, tools)
        return self

    async def __aexit__(self, *args):
        """Clean up resources"""
        await self.exit_stack.aclose()

    async def process_query(self, query: str):
        """Run an interactive chat loop"""
        if not self.llm:
            raise Exception("Must __aenter__ to query!")

        try:
            await self.llm.process_query(query)
        except Exception as e:
            LOGGER.error(f"Error: {str(e)}")
