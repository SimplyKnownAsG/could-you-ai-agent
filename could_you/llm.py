from abc import ABC, abstractmethod
from typing import Dict, Any, List
import openai
import os

import boto3
import httpx

from .message import Message, Content, ToolResult
from .config import Config
from .message_history import MessageHistory
from .mcp_server import MCPServer


class BaseLLM(ABC):
    def __init__(
        self,
        config: Config,
        message_history: MessageHistory,
        tools: Dict[str, tuple[MCPServer, Any]],
    ):
        self.config = config
        self.message_history = message_history
        self.tools = tools

    @abstractmethod
    async def converse(self) -> Message:
        """
        Execute a conversation turn with the LLM.

        Args:
            messages: List of message dictionaries in the format expected by the specific LLM
            system_prompt: Optional system prompt to include

        Returns:
            Message: The LLM's response as a Message object
        """
        pass

    async def process_query(self, query: str) -> None:
        """
        Process a user query through the LLM and handle any tool calls.

        Args:
            query: The user's input query
        """
        self.message_history.add(Message(role="user", content=[Content(text=query)]))

        should_continue = True
        while should_continue:
            should_continue = False

            output_message = await self.converse()
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


class Boto3LLM(BaseLLM):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.bedrock = boto3.client("bedrock-runtime")
        converted_tools = []

        for server, tool in self.tools.values():
            converted_tools.append(
                {
                    "toolSpec": {
                        "name": tool.name,
                        "description": tool.description,
                        "inputSchema": {"json": tool.inputSchema},
                    }
                }
            )

        self.converted_tools = {"tools": converted_tools}

    async def converse(self) -> Message:
        system = [{"text": self.config.prompt}] if self.config.prompt else []

        response = self.bedrock.converse(
            modelId=self.config.llm["model"],
            messages=self.message_history.to_dict(),
            system=system,
            inferenceConfig={"topP": 0.1, "temperature": 0.3},
            toolConfig=self.converted_tools,
        )

        return Message(response["output"]["message"])


class OpenAILLM(BaseLLM):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.client = openai.OpenAI(
            base_url=self.config.llm.get("base_url", "https://api.openai.com/v1"),
            api_key=self.config.llm.get("api_key", os.environ.get("OPENAI_API_KEY", None)),
        )

    async def converse(self) -> Message:
        # openai.base_url = "http://localhost:11434/v1"
        # openai.api_key = "ollama"

        # response = openai.chat.completions.create(
        #     model="llama3.1",
        #     messages=messages,
        #     tools=tools,
        # )

        try:
            timeout = httpx.Timeout(300)
            async with httpx.AsyncClient(timeout=timeout) as client:
                response = await client.post(
                    f"{self.base_url}/api/chat",
                    json={"model": self.model, "messages": ollama_messages, "stream": False},
                )
                response.raise_for_status()
                response_data = response.json()

            return Message(
                role="assistant", content=[Content(text=response_data["message"]["content"])]
            )
        except Exception as err:
            print(err)
            print(type(err))
            raise err

    def convert_messages_for_ollama(
        self, messages: List[Message], system_prompt: str | None = None
    ) -> List[Dict[str, str]]:
        """Convert messages to Ollama's expected format"""
        ollama_messages = []

        # Add system prompt if provided
        if system_prompt:
            ollama_messages.append({"role": "system", "content": system_prompt})

        # Convert message history
        for msg in messages:
            for content in msg["content"]:
                if "text" in content:
                    ollama_messages.append({"role": msg["role"], "content": content["text"]})

        return ollama_messages


class OllamaLLM(OpenAILLM):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.api_key = self.api_key or "ollama"
        self.api_key = "ollama"
        self.base_url = self.config.llm.get("base_url", "http://localhost:11434")
        self.model = self.config.llm["model"]

    async def converse(self) -> Message:
        ollama_messages = self.convert_messages_for_ollama(messages, system_prompt)

        # openai.base_url = "http://localhost:11434/v1"
        # openai.api_key = "ollama"

        # response = openai.chat.completions.create(
        #     model="llama3.1",
        #     messages=messages,
        #     tools=tools,
        # )

        try:
            timeout = httpx.Timeout(300)
            async with httpx.AsyncClient(timeout=timeout) as client:
                response = await client.post(
                    f"{self.base_url}/api/chat",
                    json={"model": self.model, "messages": ollama_messages, "stream": False},
                )
                response.raise_for_status()
                response_data = response.json()

            return Message(
                role="assistant", content=[Content(text=response_data["message"]["content"])]
            )
        except Exception as err:
            print(err)
            print(type(err))
            raise err

    def convert_messages_for_ollama(
        self, messages: List[Message], system_prompt: str | None = None
    ) -> List[Dict[str, str]]:
        """Convert messages to Ollama's expected format"""
        ollama_messages = []

        # Add system prompt if provided
        if system_prompt:
            ollama_messages.append({"role": "system", "content": system_prompt})

        # Convert message history
        for msg in messages:
            for content in msg["content"]:
                if "text" in content:
                    ollama_messages.append({"role": msg["role"], "content": content["text"]})

        return ollama_messages


def create_llm(
    config: Config, message_history: MessageHistory, tools: Dict[str, tuple[MCPServer, Any]]
) -> BaseLLM:
    """Factory function to create the appropriate LLM instance based on configuration"""
    provider = config.llm["provider"]

    if provider == "boto3":
        return Boto3LLM(config, message_history, tools)
    elif provider == "ollama":
        return OllamaLLM(config, message_history, tools)
    else:
        raise ValueError(f"Unsupported LLM provider: {provider}")
