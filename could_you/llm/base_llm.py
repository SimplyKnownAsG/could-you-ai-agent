from abc import ABC, abstractmethod

from ..config import Config
from ..dialogue import Dialogue
from ..mcp_server import MCPTool
from ..message import Message


class BaseLLM(ABC):
    def __init__(
        self,
        config: Config,
        dialogue: Dialogue,
        tools: dict[str, MCPTool],
    ):
        self.config = config
        self.dialogue = dialogue
        self.tools = tools

    @abstractmethod
    async def converse(self) -> Message:
        """
        Execute a conversation turn with the LLM.

        Returns:
            Message: The LLM's response as a Message object
        """
