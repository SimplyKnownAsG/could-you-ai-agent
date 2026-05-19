import boto3
from botocore.config import Config as BotoConfig
from cattrs import Converter

from ..cy_error import CYError, FaultOwner
from ..logging_config import LOGGER
from ..message import Message, MessageType, TextContent, TokenUsage, ToolResultContent, ToolUseContent
from .base_llm import BaseLLM

converter = Converter(use_alias=True, omit_if_default=True)


class Boto3LLM(BaseLLM):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        boto_config = BotoConfig(**self.config.llm.init)
        self.bedrock = boto3.client("bedrock-runtime", config=boto_config)
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
        kwargs = {
            **self._build_converse_payload(),
            **dict(self.config.llm.args),
        }

        try:
            response = self.bedrock.converse(**kwargs)
        except Exception as err:
            msg = f"Error while calling Bedrock: {err}"
            LOGGER.error(msg)
            raise CYError(message=msg, retriable=False, fault_owner=FaultOwner.LLM) from err

        # Convert Bedrock output message into our internal Message structure.
        output_message = converter.structure(response["output"]["message"], Message)

        # Determine message type based on whether it contains toolUse content
        has_tool_use = any(isinstance(content, ToolUseContent) for content in getattr(output_message, "content", []))
        output_message.type = MessageType.TOOL_CALL if has_tool_use else MessageType.NORMAL
        output_message.token_usage = self._extract_token_usage(response)

        return output_message

    def _extract_token_usage(self, response: dict) -> TokenUsage | None:
        usage = response.get("usage")
        token_limit = self.config.llm.token_limit

        if not usage and token_limit is None:
            return None

        return TokenUsage(
            inputTokens=usage.get("inputTokens") if usage else None,
            outputTokens=usage.get("outputTokens") if usage else None,
            totalTokens=usage.get("totalTokens") if usage else None,
            tokenLimit=token_limit,
        )

    def _build_converse_payload(self) -> dict:
        """Build the payload for the Bedrock Converse API.

        Mirrors the logic of OpenAILLM._convert_messages(), but targets the
        Bedrock Converse message format. We keep the richer internal
        Message/Content model in history and only project it down here.
        """
        system = [{"text": self.config.system_prompt}] if self.config.system_prompt else []
        messages: list[dict] = []

        def _format_text_message(role: str, content: TextContent) -> dict:
            """Format a plain text message preserving role."""
            return {"role": role, "content": [{"text": content.text}]}

        def _append_tool_use(msgs: list[dict], tool_use_content: ToolUseContent) -> None:
            """Append a toolUse block, grouping with previous assistant toolUse message if possible."""
            tool_use = tool_use_content.tool_use
            block = {
                "toolUse": {
                    "toolUseId": tool_use.tool_use_id,
                    "name": tool_use.name,
                    "input": tool_use.input,
                }
            }

            if msgs and msgs[-1]["role"] == "assistant" and all("toolUse" in c for c in msgs[-1].get("content", [])):
                msgs[-1]["content"].append(block)
            else:
                msgs.append({"role": "assistant", "content": [block]})

        def _append_tool_result(msgs: list[dict], tool_result_content: ToolResultContent) -> None:
            """Append a toolResult block, grouping with previous user toolResult message if possible."""
            tool_result = tool_result_content.tool_result
            inner_contents = [converter.unstructure(ic) for ic in tool_result.content]

            block = {
                "toolResult": {
                    "toolUseId": tool_result.tool_use_id,
                    "status": tool_result.status,
                    "content": inner_contents,
                }
            }

            if msgs and msgs[-1]["role"] == "user" and all("toolResult" in c for c in msgs[-1].get("content", [])):
                msgs[-1]["content"].append(block)
            else:
                msgs.append({"role": "user", "content": [block]})

        for msg in self.dialogue.messages:
            for content in msg.content:
                if isinstance(content, TextContent):
                    if msg.role == "system":
                        system.append({"text": content.text})
                    else:
                        messages.append(_format_text_message(msg.role, content))
                elif isinstance(content, ToolUseContent):
                    _append_tool_use(messages, content)
                elif isinstance(content, ToolResultContent):
                    _append_tool_result(messages, content)
                else:  # pragma: no cover - defensive fallback
                    raise CYError(
                        message="I don't know what to do with " + str(content),
                        retriable=False,
                        fault_owner=FaultOwner.INTERNAL,
                    )

        payload: dict = {"messages": messages}
        if system:
            payload["system"] = system
        if self.tool_specs:
            payload["toolConfig"] = {"tools": self.tool_specs}

        return payload
