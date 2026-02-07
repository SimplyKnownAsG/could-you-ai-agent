from abc import ABC, abstractmethod

from ..config import Config
from ..mcp_server import MCPTool
from ..message import Message
from ..message_history import MessageHistory


class BaseLLM(ABC):
    def __init__(
        self,
        config: Config,
        message_history: MessageHistory,
        tools: dict[str, MCPTool],
    ):
        self.config = config
        self.message_history = message_history
        self.tools = tools

    @abstractmethod
    async def converse(self) -> Message:
        """
        Execute a conversation turn with the LLM.

        Returns:
            Message: The LLM's response as a Message object
        """
