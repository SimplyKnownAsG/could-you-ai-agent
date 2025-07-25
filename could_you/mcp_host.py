from contextlib import AsyncExitStack
from typing import Optional, List, Dict, Tuple

from mcp import ClientSession, Tool

from .config import Config
from .mcp_server import MCPServer, MCPTool
from .message_history import MessageHistory
from .llm import create_llm, BaseLLM
from .logging_config import LOGGER


class MCPHost:
    def __init__(self, *, config: Config, message_history: MessageHistory):
        # Initialize session and client objects
        self.servers: List[MCPServer] = config.servers
        self.session: Optional[ClientSession] = None
        self.exit_stack = AsyncExitStack()
        self.config = config
        self.tools: Dict[str, Tuple[MCPServer, MCPTool]] = {}
        self.message_history = message_history
        self.llm: Optional[BaseLLM] = None

    async def __aenter__(self):
        # TODO: should this use asyncio.create_task or TaskGroup?
        for s in self.servers:
            await s.connect(exit_stack=self.exit_stack)

            for t in s.tools:
                # Only register enabled tools
                if not t.enabled:
                    continue

                old_server, old_tool = self.tools.get(t.name, (None, None))

                if old_server and old_tool:
                    LOGGER.warning(
                        f"Duplicate {t.name} tool found, using {s.name} version instead of {old_server.name}."
                    )

                self.tools[t.name] = (s, t)

        self.llm = create_llm(self.config, self.message_history, self.tools)
        return self

    async def __aexit__(self, *args):
        """Clean up resources"""
        await self.exit_stack.aclose()

    async def process_query(self, query: str):
        """Run an interactive chat loop"""
        try:
            await self.llm.process_query(query)
        except Exception as e:
            LOGGER.error(f"Error: {str(e)}")
