import boto3
from botocore.config import Config as BotoConfig
from cattrs import Converter

from ..cy_error import CYError, FaultOwner
from ..logging_config import LOGGER
from ..message import Message, MessageType, ToolResultContent
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
        system = [{"text": self.config.system_prompt}] if self.config.system_prompt else []
        messages = self.message_history.to_dict()

        # Bedrock doesn't understand our internal message types, so we need to
        # map our messages (including tool calls and tool results) into the
        # structure expected by the Converse API.
        for m in messages:
            # Remove internal message-level type field if present
            m.pop("type", None)

            # Preserve the role, but map content types appropriately
            if m["role"] == "tool":
                # Tool results are represented as toolResult content in Bedrock
                m["role"] = "assistant"
                for c in m["content"]:
                    if isinstance(c, dict) and "toolResult" in c:
                        c["toolResult"]["status"] = c["toolResult"].get("status", "success")

            # Remove internal type field from content items if present
            for c in m["content"]:
                if isinstance(c, dict) and "type" in c:
                    del c["type"]

        kwargs = {
            **dict(system=system, messages=messages),
            **({"toolConfig": {"tools": self.tool_specs}} if self.tool_specs else {}),
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
        has_tool_use = any(isinstance(content, ToolResultContent) for content in getattr(output_message, "content", []))
        output_message.type = MessageType.TOOL_CALL if has_tool_use else MessageType.NORMAL

        return output_message
