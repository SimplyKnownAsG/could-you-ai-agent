from abc import ABC, abstractmethod
from typing import Dict, List, Iterable
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
from .mcp_server import MCPServer, MCPTool
from .logging_config import LOGGER


class BaseLLM(ABC):
    def __init__(
        self,
        config: Config,
        message_history: MessageHistory,
        tools: Dict[str, MCPTool],
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
        pass

    async def process_query(self, query: str) -> None:
        """
        Process a user query through the LLM and handle any tool calls.

        Args:
            query: The user's input query
        """
        self.message_history.add(Message(role="user", content=[Content(text=query, type="text")]))
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
                tool_content: List[Content] = []

                if tool := self.tools.get(tool_use.name, None):
                    try:
                        tool_response = await tool(tool_use.input.to_dict())
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

                else:
                    LOGGER.warning(
                        f"LLM attempted to call tool that is not registerd: {tool_use.name}"
                    )
                    tool_content.append(
                        Content(
                            toolResult=ToolResult(
                                toolUseId=tool_use.tool_use_id,
                                content=[Content(text=f'Error: No tool named "{tool_use.name}".')],
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

        for tool in self.tools.values():
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
                messages=self._convert_messages(),  # type: ignore
            )
            content = []

            for choice in response.choices:
                msg = choice.message

                if msg.content:
                    content.append(Content(text=msg.content, type="text"))
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

    def _convert_messages(self) -> List[Dict[str, str]]:
        """Convert messages to Ollama's expected format"""
        openai_msgs = []

        # Add system prompt if provided
        if self.config.prompt:
            openai_msgs.append(dict(role="system", content=self.config.prompt))

        # Convert message history
        for msg in self.message_history.messages:
            for content in msg.content:
                if content.text:
                    openai_msgs.append({"role": msg.role, "content": content.text})
                elif content.tool_use:
                    # this is ... not ideal
                    tool_call = dict(
                        id=content.tool_use.tool_use_id,
                        type="function",
                        function=dict(
                            name=content.tool_use.name,
                            arguments=json.dumps(content.tool_use.input.to_dict()),
                        ),
                    )
                    prev = openai_msgs[-1]
                    if prev and prev.get("tool_calls"):
                        prev["tool_calls"].append(tool_call)
                    else:
                        openai_msgs.append(
                            dict(
                                role="assistant",
                                tool_calls=[
                                    dict(
                                        id=content.tool_use.tool_use_id,
                                        type="function",
                                        function=dict(
                                            name=content.tool_use.name,
                                            arguments=json.dumps(content.tool_use.input.to_dict()),
                                        ),
                                    )
                                ],
                            )
                        )
                elif content.tool_result:
                    openai_msgs.append(
                        dict(
                            role="tool",
                            tool_call_id=content.tool_result.tool_use_id,
                            content=content.tool_result.content[0].text,
                        )
                    )
                else:
                    raise Exception("I don't know what to do with " + json.dumps(content.to_dict()))

        return openai_msgs

    def _convert_tools(self) -> Iterable[ChatCompletionToolParam]:
        converted_tools: Iterable[ChatCompletionToolParam] = []
        for tool in self.tools.values():
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
    config: Config, message_history: MessageHistory, tools: Dict[str, MCPTool]
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
