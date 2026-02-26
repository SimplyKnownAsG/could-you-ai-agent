import json
from collections.abc import Callable
from typing import Any, Literal

from attrs import define, field
from cattrs import Converter

from .attrs_patch import AttrsAllowAliasKeyword

converter = Converter(use_alias=True, omit_if_default=True)


@define
class ToolUse(AttrsAllowAliasKeyword):
    tool_use_id: str = field(alias="toolUseId")
    name: str
    input: Any
    type: Literal["tool_use"] = field(default="tool_use")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)


@define
class ToolUseContent:
    tool_use: ToolUse = field(alias="toolUse")


@define
class ToolResultInnerContent:
    text: str | None = field(default=None)
    json: Any | None = field(default=None)


@define
class ToolResult(AttrsAllowAliasKeyword):
    status: Literal["success", "error"]
    tool_use_id: str = field(alias="toolUseId")
    content: list[ToolResultInnerContent]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)


@define
class ToolResultContent(AttrsAllowAliasKeyword):
    tool_result: ToolResult = field(alias="toolResult")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)


@define
class TextContent:
    text: str
    type: Literal["text"] = field(factory=lambda: "text")


Content = TextContent | ToolUseContent | ToolResultContent


@define
class Message:
    role: Literal["user", "assistant"]
    content: list[Content]

    def print(self, *, info=Callable[[str], None], debug=Callable[[str], None]):
        info(f"## {self.role}")
        for content in self.content:
            content_dict = converter.unstructure(content)

            for key, val in content_dict.items():
                if key == "text":
                    # Always print text content
                    info(f"* {key}:")
                    for line in val.splitlines():
                        info(f"   > {line}")
                elif isinstance(val, str):
                    for line in val.splitlines():
                        debug(f"> {line}")
                else:
                    json_lines = json.dumps(val, indent=2).splitlines()
                    debug("  ```json")
                    for line in json_lines:
                        debug(f"   {line}")
                    debug("  ```")
