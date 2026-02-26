import json
from collections.abc import Callable
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
        body2 = "```\njson" + json.dumps(self.input, indent=2) + "\n```"
        _print_markdown(debug, body2, 5, "Input")


@define
class ToolUseContent:
    tool_use: ToolUse = field(alias="toolUse")

    def print(self, *, info=Callable[[str], None], debug=Callable[[str], None]):
        _print_markdown(info, "", 3, "Tool use")
        self.tool_use.print(info=info, debug=debug)


@define
class ToolResultInnerTextContent:
    text: str

    def print(self, *, info=Callable[[str], None], debug=Callable[[str], None]):  # noqa: ARG002
        _print_markdown(info, self.text, 5, "Text")


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


@define
class Message:
    role: Literal["user", "assistant"]
    content: list[Content]

    def print(self, *, info=Callable[[str], None], debug=Callable[[str], None]):
        info(f"## {self.role}")
        for content in self.content:
            content.print(info=info, debug=debug)


def _print_markdown(
    printer: Callable[[str], None], markdown_text: str, shift: int = 1, new_title: str | None = None
) -> str:
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

    for line in renderer(tokens, state).splitlines():
        printer(f"{line}")


def _shift_headings(tokens: list[dict[str, Any]], shift: int) -> None:
    """Recursively shift all heading levels by the specified amount."""
    for token in tokens:
        if token["type"] == "heading":
            token["attrs"]["level"] += shift

        # Process children if they exist
        if "children" in token and isinstance(token["children"], list):
            _shift_headings(token["children"], shift)
