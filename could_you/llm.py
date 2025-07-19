from abc import ABC, abstractmethod
from typing import Dict, Any, List, Iterable, Optional
import traceback
import openai
import os
import json

import boto3
from openai.types.chat import ChatCompletionToolParam
from mcp import Tool

from .message import Message, Content, ToolResult, ToolUse
from .config import Config
from .message_history import MessageHistory
from .mcp_server import MCPServer
from .logging_config import LOGGER



class BaseLLM(ABC):
    def __init__(
        self,
        config: Config,
        message_history: MessageHistory,
        tools: Dict[str, tuple[MCPServer, Tool]],
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

    async def process_query(self, query: str, verbose: bool = False) -> None:
        """
        Process a user query through the LLM and handle any tool calls.

        Args:
            query: The user's input query
            verbose: Whether to show verbose output including tool details
        """
        self.message_history.add(
            Message(role="user", content=[Content(text=query, type="text")]), verbose=verbose
        )
        should_continue = True

        while should_continue:
            should_continue = False
            output_message = await self.converse()
            self.message_history.add(output_message, verbose=verbose)

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
                self.message_history.add(tool_message, verbose=verbose)


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
        messages = self.message_history.to_dict()

        # why, oh why, are they not the same? claude via boto3 fails if "type" is specified
        for m in messages:
            for c in m["content"]:
                if "type" in c:
                    del c["type"]

        response = self.bedrock.converse(
            modelId=self.config.llm["model"],
            messages=messages,
            system=system,
            inferenceConfig={"topP": 0.1, "temperature": self.config.llm.get("temperature", 0.3)},
            toolConfig=self.converted_tools,
        )

        return Message(response["output"]["message"])


class OpenAILLM(BaseLLM):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.model = self.config.llm["model"]
        self._converted_tools = self._convert_tools()
        self.client = self._init_client()

    def _init_client(self):
        return openai.OpenAI(
            base_url=self.config.llm.get("base_url", "https://api.openai.com/v1"),
            api_key=self.config.llm.get("api_key", os.environ.get("OPENAI_API_KEY", None)),
        )

    async def converse(self) -> Message:
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                tools=self._converted_tools,
                messages=self.message_history.to_dict(),  # type: ignore
            )
            content = []

            for choice in response.choices:
                msg = choice.message

                if msg.content:
                    content.append(Content(text=msg.content))
                elif msg.tool_calls:
                    for tool_call in msg.tool_calls:
                        tool_use_id = tool_call.id
                        name = tool_call.function.name
                        input = json.loads(tool_call.function.arguments)
                        content.append(
                            Content(
                                tool_use=ToolUse(tool_use_id=tool_use_id, name=name, input=input)
                            )
                        )
                else:
                    raise NotImplementedError(f"Cannot handle response, sry... {response}")

            msg_result = Message(role="assistant", content=content)
            return msg_result

        except Exception as err:
            LOGGER.error(f"Error: {err}")
            LOGGER.debug(f"Error type: {type(err)}")
            LOGGER.debug(traceback.format_exc())
            raise err

    def convert_messages_for_openai(
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

    def _convert_tools(self) -> Iterable[ChatCompletionToolParam]:
        converted_tools: Iterable[ChatCompletionToolParam] = []
        for [_server, tool] in self.tools.values():
            converted_tools.append(
                {
                    "type": "function",
                    "function": {
                        "name": tool.name,
                        "description": str(tool.description),
                        "parameters": tool.inputSchema,
                    },
                }
            )
        return converted_tools


class OllamaLLM(OpenAILLM):
    """
    OllamaLLM is compliant with OpenAILLM [1].


    [1] https://ollama.com/blog/tool-support
    """

    def _init_client(self):
        return openai.OpenAI(
            api_key=self.config.llm.get("api_key", "ollama"),
            base_url=self.config.llm.get("base_url", "http://localhost:11434/v1"),
        )


def create_llm(
    config: Config, message_history: MessageHistory, tools: Dict[str, tuple[MCPServer, Tool]]
) -> BaseLLM:
    """Factory function to create the appropriate LLM instance based on configuration"""
    provider = config.llm["provider"]

    if provider == "boto3":
        return Boto3LLM(config, message_history, tools)
    elif provider == "ollama":
        return OllamaLLM(config, message_history, tools)
    elif provider == "openai":
        return OpenAILLM(config, message_history, tools)
    else:
        raise ValueError(f"Unsupported LLM provider: {provider}")
