import json

import openai
from openai.types.chat import ChatCompletionToolParam

from ..cy_error import CYError, FaultOwner
from ..logging_config import LOGGER
from ..message import Content, Message, ToolUse
from .base_llm import BaseLLM


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
        openai_msgs = []
        if self.config.system_prompt:
            openai_msgs.append(dict(role="system", content=self.config.system_prompt))
        for msg in self.message_history.messages:
            for content in msg.content:
                if content.text:
                    openai_msgs.append({"role": msg.role, "content": content.text})
                elif content.tool_use:
                    tool_call = dict(
                        id=content.tool_use.tool_use_id,
                        type="function",
                        function=dict(
                            name=content.tool_use.name,
                            arguments=json.dumps(content.tool_use.input),
                        ),
                    )
                    prev = openai_msgs[-1] if openai_msgs else None
                    if prev and prev.get("tool_calls"):
                        prev["tool_calls"].append(tool_call)
                    else:
                        openai_msgs.append(
                            dict(
                                role="assistant",
                                tool_calls=[tool_call],
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
                        message="I don't know what to do with " + json.dumps(content),
                        retriable=False,
                        fault_owner=FaultOwner.INTERNAL,
                    )
        return openai_msgs

    def _convert_tools(self) -> list[ChatCompletionToolParam]:
        converted_tools = []
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
