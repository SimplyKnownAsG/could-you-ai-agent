import json
from collections.abc import Callable
from typing import Any, Literal

from .dynamic import Dynamic


class ToolUse(Dynamic):
    tool_use_id: str
    name: str
    input: Any


class ToolResultContent(Dynamic):
    text: str
    json: Any


class ToolResult(Dynamic):
    tool_use_id: str
    content: list[ToolResultContent]
    status: Literal["success", "error"]


class Content(Dynamic):
    type: Literal["text"]
    text: str | None
    # image: Optional[Image]
    # document: Optional[Document]
    # video: Optional[Video]
    tool_use: ToolUse | None
    tool_result: ToolResult | None
    # guard_content: Optional[GuardContent]
    # cache_point: Optional[CachePoint]
    # reasoning_content: Optional[ReasoningContent]


class Message(Dynamic):
    role: Literal["user", "assistant"]
    content: list[Content]

    def print(self, *, info=Callable[[str], None], debug=Callable[[str], None]):
        info(f"## {self.role}")
        for content in self.content:
            for key, val in vars(content).items():
                if key == "text":
                    # Always print text content
                    info(f"* {key}:")
                    for line in val.splitlines():
                        info(f"   > {line}")
                else:
                    suffix = f" {val.name}" if key == "toolUse" and isinstance(val, Dynamic) else ""
                    info(f"* {key}:{suffix}")

                    if isinstance(val, str):
                        for line in val.splitlines():
                            debug(f"> {line}")
                    elif isinstance(val, Dynamic):
                        # Pretty print JSON with consistent indentation
                        v = val.to_dict() if isinstance(val, Dynamic) else val
                        json_lines = json.dumps(v, indent=2).splitlines()
                        debug("  ```json")
                        for line in json_lines:
                            debug(f"   {line}")
                        debug("  ```")
                    else:
                        # For other types, convert to string
                        debug(f"    {val!s}")
