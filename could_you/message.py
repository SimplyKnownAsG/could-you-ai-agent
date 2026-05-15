import json
from collections.abc import Callable
from enum import Enum
from typing import Any, Literal

import mistune
from attrs import define, field
from cattrs import Converter
from mistune.core import BlockState
from mistune.renderers.markdown import MarkdownRenderer

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

    def print(self, *, info=Callable[[str], None], debug=Callable[[str], None]):
        body = f"\n* **tool use id**: {self.tool_use_id}\n"
        _print_markdown(info, body, 4, f"{self.name}")
        body2 = "```json\n" + json.dumps(self.input, indent=2) + "\n```"
        _print_markdown(debug, body2, 5, "Input")


@define
class ToolUseContent(AttrsAllowAliasKeyword):
    tool_use: ToolUse = field(alias="toolUse")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def print(self, *, info=Callable[[str], None], debug=Callable[[str], None]):
        _print_markdown(info, "", 3, "Tool use")
        self.tool_use.print(info=info, debug=debug)


@define
class ToolResultInnerTextContent:
    text: str

    def print(self, *, info=Callable[[str], None], debug=Callable[[str], None]):  # noqa: ARG002
        # XXX: tool results probably are not actual markdown, probably?
        # XXX: if calling an agent as a tool, this will be less than ideal.
        if self.text.startswith("```") and self.text.rstrip().endswith("```"):
            _print_markdown(debug, self.text, 5, "Text")
        else:
            _print_markdown(debug, "    " + "\n    ".join(self.text.splitlines()), 5, "Text")


@define
class ToolResultInnerJsonContent:
    json: Any

    def print(self, *, info=Callable[[str], None], debug=Callable[[str], None]):  # noqa: ARG002
        body = "```json\n{json.dumps(self.json, indent=2)}\n```"
        _print_markdown(info, body, 5, "JSON")


ToolResultInnerContent = ToolResultInnerTextContent | ToolResultInnerJsonContent


@define
class ToolResult(AttrsAllowAliasKeyword):
    status: Literal["success", "error"]
    tool_use_id: str = field(alias="toolUseId")
    content: list[ToolResultInnerContent]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def print(self, *, info=Callable[[str], None], debug=Callable[[str], None]):
        body = "\n".join(["", f"* **status**: {self.status}", f"* **tool use id**: {self.tool_use_id}", ""])

        _print_markdown(info, body, 4, f"[{self.status}] tool result")
        for content in self.content:
            content.print(info=info, debug=debug)


@define
class ToolResultContent(AttrsAllowAliasKeyword):
    tool_result: ToolResult = field(alias="toolResult")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def print(self, *, info=Callable[[str], None], debug=Callable[[str], None]):
        _print_markdown(info, "", 3, "Tool result")
        self.tool_result.print(info=info, debug=debug)


@define
class TextContent:
    text: str
    type: Literal["text"] = field(factory=lambda: "text")

    def print(self, *, info=Callable[[str], None], debug=Callable[[str], None]):  # noqa: ARG002
        _print_markdown(info, self.text, 3, "text")


Content = TextContent | ToolUseContent | ToolResultContent


class MessageType(str, Enum):
    NORMAL = "normal"
    TOOL_CALL = "tool_call"
    TOOL_RESULT = "tool_result"


@define
class Message:
    role: Literal["user", "assistant", "tool", "system"]
    content: list[Content]
    type: MessageType = field(default=MessageType.NORMAL)

    def print(self, *, info=Callable[[str], None], debug=Callable[[str], None]):
        """Render this message as markdown, making tool use/results explicit.

        Roles/types are rendered as:
        - User normal: "## User"
        - Assistant normal: "## Assistant"
        - System: "## System"
        - Assistant tool_call: "## Assistant (tool call)"
        - Tool tool_result: "## Tool result"
        """
        if self.type is MessageType.NORMAL:
            if self.role == "user":
                heading = "User"
            elif self.role == "assistant":
                heading = "Assistant"
            elif self.role == "system":
                heading = "System"
            elif self.role == "tool":
                heading = "Tool"
            else:  # pragma: no cover - defensive fallback
                heading = self.role
        elif self.type is MessageType.TOOL_CALL:
            heading = "Assistant (tool call)"
        elif self.type is MessageType.TOOL_RESULT:
            heading = "Tool result"
        else:  # pragma: no cover - defensive fallback
            heading = f"{self.role} ({self.type.value})"

        info(f"## {heading}")
        for content in self.content:
            content.print(info=info, debug=debug)


def _print_markdown(printer: Callable[[str], None], markdown_text: str, shift: int = 1, new_title: str | None = None):
    """
    Reshift markdown headings and optionally add a new top-level heading.

    Args:
        markdown_text: The markdown content
        shift: Number of levels to increase heading depth (default 1)
        new_title: Optional new h1 heading to prepend

    Returns:
        Modified markdown with reshifted headings
    """
    # Parse markdown into AST without rendering
    md = mistune.create_markdown(renderer=None)
    tokens, state = md.parse(markdown_text)

    # Shift heading levels
    _shift_headings(tokens, shift)

    # Prepend new title if provided
    if new_title:
        tokens = [
            {
                "type": "heading",
                "children": [{"type": "text", "raw": new_title}],
                "attrs": {"level": shift},
                "style": "atx",
            },
            *tokens,
        ]

    # Render back to markdown using MarkdownRenderer
    renderer = MarkdownRenderer()
    state = BlockState()

    # XXX: a bit wasteful to build a string an split it!
    for line in renderer(tokens, state).splitlines():
        printer(f"{line}")


def _shift_headings(tokens: list[dict[str, Any]], shift: int) -> None:
    """Shift top-level headings."""
    for token in tokens:
        token_type = token["type"]

        if token_type == "heading":  # noqa: S105
            token["attrs"]["level"] += shift

        elif token_type == "block_code" and token["style"] == "fenced":  # noqa: S105
            token["raw"] = "    " + "\n    ".join(token["raw"].splitlines())

        elif token_type == "block_code" and token["style"] == "indent":  # noqa: S105
            # I don't understand why, but the MarkdownRendere transforms "indent" to "fenced"
            token["raw"] = "    " + "\n    ".join(token["raw"].splitlines())
