import json
from copy import deepcopy
from typing import Any
import re

from google import genai
from google.genai import types

from ..cy_error import CYError, FaultOwner
from ..logging_config import LOGGER
from ..message import Message, MessageMetadata, MessageType, TextContent, ToolResultContent, ToolUse, ToolUseContent
from .base_llm import BaseLLM

from typing import TypeVar, cast

T = TypeVar('T')


class VertexLLM(BaseLLM):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.client = self._init_client()
        self._converted_tools = self._convert_tools()

    def _init_client(self):
        init_kwargs = dict(self.config.llm.init or {})
        return genai.Client(vertexai=True, **init_kwargs)

    async def converse(self) -> Message:
        response = await self._call_client()
        return self._transform_response(response)

    async def _call_client(self):
        try:
            return self.client.models.generate_content(
                model=self._model_name(),
                contents=self._convert_messages(),
                config=self._build_generate_content_config(),
            )
        except Exception as err:
            msg = f"Error while calling Vertex AI: {err}"
            LOGGER.error(msg)
            raise CYError(message=msg, retriable=False, fault_owner=FaultOwner.LLM) from err

    def _model_name(self) -> str:
        model = (self.config.llm.args or {}).get("model")
        if not model:
            raise CYError(
                message="Vertex provider requires llm.args.model",
                retriable=False,
                fault_owner=FaultOwner.USER,
            )
        return model

    def _build_generate_content_config(self):
        args = dict(self.config.llm.args or {})
        args.pop("model", None)

        if self._converted_tools:
            args["tools"] = self._converted_tools

        if self.config.system_prompt:
            args["system_instruction"] = self.config.system_prompt

        return types.GenerateContentConfig(**args)

    def _transform_response(self, response) -> Message:
        content = []

        candidates = getattr(response, "candidates", None) or []
        for candidate in candidates:
            candidate_content = getattr(candidate, "content", None)
            parts = getattr(candidate_content, "parts", None) or []
            for part in parts:
                text = getattr(part, "text", None)
                if text:
                    content.append(TextContent(text=text, type="text"))
                    continue

                function_call = getattr(part, "function_call", None)
                if function_call:
                    tool_input = self._function_call_args(function_call)
                    content.append(
                        ToolUseContent(
                            tool_use=ToolUse(
                                tool_use_id=getattr(function_call, "id", None)
                                or getattr(function_call, "name", "tool-call"),
                                name=function_call.name,
                                input=tool_input,
                            )
                        )
                    )
                    continue

        if not content:
            text = getattr(response, "text", None)
            if text:
                content.append(TextContent(text=text, type="text"))

        if not content:
            raise CYError(
                message=f"Cannot handle Vertex response, sry... {response}",
                retriable=False,
                fault_owner=FaultOwner.INTERNAL,
            )

        message_type = (
            MessageType.TOOL_CALL if any(isinstance(c, ToolUseContent) for c in content) else MessageType.NORMAL
        )

        return Message(
            role="assistant",
            content=content,
            type=message_type,
            metadata=self._extract_token_usage(response),
        )

    def _extract_token_usage(self, response) -> MessageMetadata | None:
        usage = getattr(response, "usage_metadata", None)
        token_limit = self.config.llm.token_limit

        if not usage and token_limit is None:
            return None

        return MessageMetadata(
            inputTokens=getattr(usage, "prompt_token_count", None) if usage else None,
            outputTokens=getattr(usage, "candidates_token_count", None) if usage else None,
            totalTokens=getattr(usage, "total_token_count", None) if usage else None,
            tokenLimit=token_limit,
            provider=self.config.llm.provider,
            model=(self.config.llm.args or {}).get("model"),
        )

    def _convert_messages(self) -> list[types.Content]:
        contents: list[types.Content] = []

        for msg in self.dialogue.messages:
            for content in msg.content:
                if isinstance(content, TextContent):
                    role = "model" if msg.role == "assistant" else "user"
                    contents.append(types.Content(role=role, parts=[types.Part.from_text(text=content.text)]))
                elif isinstance(content, ToolUseContent):
                    tool_use = content.tool_use
                    contents.append(
                        types.Content(
                            role="model",
                            parts=[types.Part.from_function_call(name=tool_use.name, args=tool_use.input)],
                        )
                    )
                elif isinstance(content, ToolResultContent):
                    tool_result = content.tool_result
                    response_payload = self._tool_result_payload(tool_result)
                    contents.append(
                        types.Content(
                            role="user",
                            parts=[
                                types.Part.from_function_response(
                                    name=tool_result.tool_use_id, response=response_payload
                                )
                            ],
                        )
                    )
                else:
                    raise CYError(
                        message="I don't know what to do with " + json.dumps(content),
                        retriable=False,
                        fault_owner=FaultOwner.INTERNAL,
                    )

        return contents

    def _tool_result_payload(self, tool_result) -> dict[str, Any]:
        if len(tool_result.content) == 1 and hasattr(tool_result.content[0], "text"):
            payload: Any = tool_result.content[0].text
        else:
            payload = []
            for inner_content in tool_result.content:
                if hasattr(inner_content, "text"):
                    payload.append({"text": inner_content.text})
                elif hasattr(inner_content, "json"):
                    payload.append({"json": inner_content.json})

        return {"result": payload, "status": tool_result.status}

    def _convert_tools(self) -> list[types.Tool]:
        declarations = []
        for tool in self.tools.values():
            declarations.append(
                types.FunctionDeclaration(
                    name=tool.name,
                    description=str(tool.description),
                    parameters=types.Schema(**self._sanitize_schema(tool.inputSchema)),
                )
            )

        if not declarations:
            return []

        return [types.Tool(function_declarations=declarations)]

    def _sanitize_schema(self, value: T) -> T:
        """Remove provider-incompatible JSON Schema decoration.

        MCP tool schemas may carry extra metadata from zod/json-schema conversion
        such as `_def`, `~standard`, `$schema`, and other descriptive fields.
        Vertex function declarations are stricter and reject unknown keys, so
        strip obvious decoration recursively.
        """
        if isinstance(value, dict):
            d = {}

            for key, inner_value in value.items():
                if re.match('^[^a-zA-Z0-9]', str(key)):
                    continue

                d[key] = self._sanitize_schema(inner_value)

            return cast(T, d)
        elif isinstance(value, list):
            l = []

            for inner_value in value:
                l.append(self._sanitize_schema(inner_value))

            return cast(T, l)
        else:
            return value

    def _function_call_args(self, function_call) -> dict[str, Any]:
        args = getattr(function_call, "args", None)
        if args is None:
            return {}
        if isinstance(args, dict):
            return args
        if hasattr(args, "items"):
            return dict(args.items())
        return dict(args)
