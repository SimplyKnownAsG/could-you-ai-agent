import boto3
from botocore.config import Config as BotoConfig
from cattrs import Converter

from ..cy_error import CYError, FaultOwner
from ..logging_config import LOGGER
from ..message import Message
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
        for m in messages:
            for c in m["content"]:
                if "type" in c:
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
            LOGGER.error("Error calling bedrock", err)
            raise CYError(message=msg, retriable=False, fault_owner=FaultOwner.LLM) from err
        return converter.structure(response["output"]["message"], Message)
