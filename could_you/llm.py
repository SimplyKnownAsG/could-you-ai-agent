import json
from abc import ABC, abstractmethod
from collections.abc import Iterable

import boto3
import openai
from cattrs import Converter
from openai.types.chat import ChatCompletionToolParam

from .config import Config
from .cy_error import CYError, FaultOwner
from .logging_config import LOGGER
from .mcp_server import MCPTool
from .message import Content, Message, ToolUse
from .message_history import MessageHistory

converter = Converter(use_alias=True, omit_if_default=True)
# converter.register_structure_hook_factory(
#     attrs.has,
#     lambda cl: cattrs.gen.make_dict_structure_fn(cl, converter, _cattrs_use_alias=True)
# )


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


class Boto3LLM(BaseLLM):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.bedrock = boto3.client("bedrock-runtime")
        self.tool_specs = []

        for tool in self.tools.values():
            self.tool_specs.append(
                {
                    "toolSpec": {
                        "name": tool.name,
                        "description": tool.description,
                        "inputSchema": {"json": tool.inputSchema},
                    }
                }
            )

    async def converse(self) -> Message:
        system = [{"text": self.config.system_prompt}] if self.config.system_prompt else []
        messages = self.message_history.to_dict()

        # why, oh why, are they not the same? claude via boto3 fails if "type" is specified
        for m in messages:
            for c in m["content"]:
                if "type" in c:
                    del c["type"]

        kwargs = {
            **dict(system=system, messages=messages),
            **({"toolConfig": {"tools": self.tool_specs}} if self.tool_specs else {}),
            **dict(self.config.llm.args),
        }

        response = self.bedrock.converse(**kwargs)
        return converter.structure(response["output"]["message"], Message)


class OpenAILLM(BaseLLM):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._converted_tools = self._convert_tools()
        self.client = self._init_client()

    def _init_client(self):
        return openai.OpenAI(**self.config.llm.init)

    async def converse(self) -> Message:
        response = await self._call_client()
        return self._transform_response(response)

    async def _call_client(self) -> Message:
        try:
            return self.client.chat.completions.create(
                tools=self._converted_tools,
                messages=self._convert_messages(),  # type: ignore
                **(self.config.llm.args or {}),
            )
        except Exception as err:
            msg = f"Error while calling LLM: {err}"
            LOGGER.error(msg)
            raise CYError(message=msg, retriable=False, fault_owner=FaultOwner.LLM) from err

    def _transform_response(self, response) -> Message:
        content = []

        for choice in response.choices:
            msg = choice.message

            if msg.content:
                content.append(Content(text=msg.content, type="text"))
            elif msg.tool_calls:
                for tool_call in msg.tool_calls:
                    tool_use_id = tool_call.id
                    name = tool_call.function.name
                    tool_input = json.loads(tool_call.function.arguments)
                    content.append(Content(tool_use=ToolUse(tool_use_id=tool_use_id, name=name, input=tool_input)))
            else:
                raise CYError(
                    message=f"Cannot handle response, sry... {response}",
                    retriable=False,
                    fault_owner=FaultOwner.INTERNAL,
                )

        return Message(role="assistant", content=content)

    def _convert_messages(self) -> list[dict[str, str]]:
        """Convert messages to Ollama's expected format"""
        openai_msgs = []

        # Add system prompt if provided
        if self.config.system_prompt:
            openai_msgs.append(dict(role="system", content=self.config.system_prompt))

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
                    raise CYError(
                        message="I don't know what to do with " + json.dumps(content.to_dict()),
                        retriable=False,
                        fault_owner=FaultOwner.INTERNAL,
                    )

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
        return openai.OpenAI(**self.config.init)


def create_llm(config: Config, message_history: MessageHistory, tools: dict[str, MCPTool]) -> BaseLLM:
    """Factory function to create the appropriate LLM instance based on configuration"""
    provider = config.llm.provider
    providers = {
        "boto3": Boto3LLM,
        "ollama": OllamaLLM,
        "openai": OpenAILLM,
    }

    if provider in providers:
        LOGGER.debug(f"Initializing {providers[provider].__name__} from configuration {config.llm}")
        return providers[provider](config, message_history, tools)

    raise CYError(
        message=f"Unsupported LLM provider: {provider}",
        retriable=False,
        fault_owner=FaultOwner.USER,
    )
