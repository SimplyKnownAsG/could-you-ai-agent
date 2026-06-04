import json
import re
from typing import Any, TypeVar, cast

from google import genai
from google.api_core import exceptions as google_exceptions
from google.genai import types
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from ..cy_error import CYError, FaultOwner
from ..logging_config import LOGGER
from ..message import Message, MessageMetadata, MessageType, TextContent, ToolResultContent, ToolUse, ToolUseContent
from .base_llm import BaseLLM

T = TypeVar("T")


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

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=60),
        retry=retry_if_exception_type(google_exceptions.ResourceExhausted),
    )
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
        content: list[TextContent | ToolUseContent | ToolResultContent] = []
        should_raise = False

        # The top-level response can have a finish reason for the overall generation.
        # This is often where critical failures like invalid API keys are surfaced.
        top_level_finish_reason = getattr(response, "finish_reason", None)
        if top_level_finish_reason not in (None, "STOP", "MAX_TOKENS"):
            # This indicates a problem with the request itself, not the model's behavior.
            # It is not recoverable from the agent's perspective.
            should_raise = True

        candidates = getattr(response, "candidates", [])
        for candidate in candidates:
            # A candidate finish reason can indicate a problem with the model's output,
            # such as a malformed function call, which IS recoverable.
            finish_reason_str = str(getattr(candidate, "finish_reason", ""))

            if reason := next((r for r in RECOVERABLE_FINISH_REASONS if r.reason in finish_reason_str), None):
                finish_message = getattr(candidate, "finish_message", "An unknown error occurred.")
                content.append(
                    ToolResultContent.from_error(
                        tool_use_id=reason.tool_use_id(),
                        message=reason.message(finish_message),
                    )
                )
                continue

            # Handle non-recoverable but also non-successful finish reasons that were not handled above.
            if finish_reason_str and finish_reason_str not in ("FinishReason.STOP", "FinishReason.MAX_TOKENS"):
                error_text = f"Error: Model response could not be processed. Reason: {finish_reason_str}."
                content.append(TextContent(text=error_text, type="text"))
                continue

            candidate_content = getattr(candidate, "content", None)
            parts = getattr(candidate_content, "parts", [])
            for part in parts:
                if hasattr(part, "text") and part.text:
                    content.append(TextContent(text=part.text, type="text"))
                elif hasattr(part, "function_call"):
                    function_call = part.function_call
                    tool_input = self._function_call_args(function_call)
                    content.append(
                        ToolUseContent(
                            tool_use=ToolUse(
                                tool_use_id=getattr(function_call, "id", None) or function_call.name,
                                name=function_call.name,
                                input=tool_input,
                            )
                        )
                    )

        if not content or should_raise:
            # If there's no content or a fatal error occurred, raise a CYError.
            raise CYError(
                message=f"Cannot handle Vertex response: {response}",
                retriable=False,
                fault_owner=FaultOwner.INTERNAL,
            )

        # Determine the message type based on the content. A tool result indicates the end
        # of a tool-using turn, so it's a NORMAL assistant message.
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
                key_str = str(key)

                if re.match(r"^[^a-zA-Z0-9]", key_str):
                    continue

                if key_str in {
                    "additional_properties",
                    "additionalProperties",
                    "default",
                    "example",
                    "examples",
                    "property_ordering",
                    "propertyOrdering",
                }:
                    continue

                d[key] = self._sanitize_schema(inner_value)

            return cast("T", d)
        if isinstance(value, list):
            l = []

            for inner_value in value:
                l.append(self._sanitize_schema(inner_value))

            return cast("T", l)
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


class RecoverableFinishReason:
    def __init__(self, reason: str, base_tool_use_id: str, message_template: str):
        self.reason = reason
        self.base_tool_use_id = base_tool_use_id
        self.message_template = message_template

    def tool_use_id(self) -> str:
        return self.base_tool_use_id

    def message(self, finish_message: str) -> str:
        return self.message_template.format(finish_message)


RECOVERABLE_FINISH_REASONS = [
    RecoverableFinishReason(
        reason="MALFORMED_FUNCTION_CALL",
        base_tool_use_id="malformed-tool-call",
        message_template="The model generated a function call that was syntactically invalid. The API returned the following error: '{}'. Please correct the tool call and try again.",
    ),
    RecoverableFinishReason(
        reason="UNEXPECTED_TOOL_CALL",
        base_tool_use_id="unexpected-tool-call",
        message_template="The model generated a tool call when it was not expected. The API returned the following error: '{}'. Please review the conversation and try again.",
    ),
    RecoverableFinishReason(
        reason="SAFETY",
        base_tool_use_id="safety-violation",
        message_template="The model's response was blocked for safety reasons. The API returned the following error: '{}'. Please generate a different response.",
    ),
    RecoverableFinishReason(
        reason="RECITATION",
        base_tool_use_id="recitation-violation",
        message_template="The model's response was blocked due to potential copyright violations. The API returned the following error: '{}'. Please generate a different response.",
    ),
    RecoverableFinishReason(
        reason="BLOCKLIST",
        base_tool_use_id="blocklist-violation",
        message_template="The model's response was blocked because it contained a forbidden term. The API returned the following error: '{}'. Please generate a different response.",
    ),
    RecoverableFinishReason(
        reason="PROHIBITED_CONTENT",
        base_tool_use_id="prohibited-content-violation",
        message_template="The model's response was blocked for containing prohibited content. The API returned the following error: '{}'. Please generate a different response.",
    ),
    RecoverableFinishReason(
        reason="SPII",
        base_tool_use_id="spii-violation",
        message_template="The model's response was blocked because it may contain Sensitive Personally Identifiable Information (SPII). The API returned the following error: '{}'. Please generate a different response.",
    ),
    RecoverableFinishReason(
        reason="MODEL_ARMOR",
        base_tool_use_id="model-armor-blocked",
        message_template="The model's response was blocked by Model Armor. The API returned the following error: '{}'. Please generate a different response.",
    ),
    RecoverableFinishReason(
        reason="OTHER",
        base_tool_use_id="other-error",
        message_template="The model's response was stopped for an unspecified reason. The API returned the following error: '{}'. Please try a different approach.",
    ),
]
