import textwrap

from cattrs import Converter

from could_you.message import Message, MessageType, TextContent, TokenUsage, _print_markdown


class Printer:
    def __init__(self):
        self.lines = []

    def dummy_printer(self, string: str):
        self.lines.append(string)


def test_print_markdown_adjust_headings1():
    raw = textwrap.dedent("""
    # top level heading
    ## second level heading
    """)
    p = Printer()

    _print_markdown(p.dummy_printer, raw, 1, "text")

    assert "# text" in p.lines
    assert "## top level heading" in p.lines
    assert "### second level heading" in p.lines


def test_print_markdown_adjust_headings2():
    raw = textwrap.dedent("""
    # top level heading
    ## second level heading
    """)
    p = Printer()

    _print_markdown(p.dummy_printer, raw, 2, "text")

    assert "## text" in p.lines
    assert "### top level heading" in p.lines
    assert "#### second level heading" in p.lines


def test_print_markdown_adjust_fenced_code():
    raw = textwrap.dedent("""
    ```bash
    # this is not a heading.
    echo 'hello world'
    ```
    """)
    p = Printer()

    _print_markdown(p.dummy_printer, raw, 1, "text")

    assert "```bash" in p.lines
    assert "    # this is not a heading." in p.lines
    assert "    echo 'hello world'" in p.lines
    assert "```" in p.lines


def test_print_markdown_adjust_indented_code():
    raw = textwrap.dedent("""
    here is some text before the indented code

        # this is not a heading.
        echo 'hello world'
    """)
    p = Printer()

    _print_markdown(p.dummy_printer, raw, 1)

    assert "```" in p.lines
    assert "    # this is not a heading." in p.lines
    assert "    echo 'hello world'" in p.lines
    assert "```" in p.lines


def test_print_markdown_not_adjust_nested_headings():
    raw = textwrap.dedent("""
    # actual heading
    > # quoted heading
    """)
    p = Printer()

    _print_markdown(p.dummy_printer, raw, 1)

    assert "## actual heading" in p.lines
    assert "> # quoted heading" in p.lines


def test_print_markdown_not_adjust_nested_indented_code():
    raw = textwrap.dedent("""
    * bulleted list
      ```bash
      echo 'hello world'
      ```
    """)
    p = Printer()

    _print_markdown(p.dummy_printer, raw, 1)

    assert "* bulleted list" in p.lines
    assert "  ```bash" in p.lines
    assert "  echo 'hello world'" in p.lines
    assert "  ```" in p.lines


def test_message_token_usage_serializes_with_camel_case():
    converter = Converter(use_alias=True, omit_if_default=True)
    message = Message(
        role="assistant",
        content=[TextContent(text="hi")],
        tokenUsage=TokenUsage(inputTokens=10, outputTokens=5, totalTokens=15, tokenLimit=100),
    )

    assert converter.unstructure(message) == {
        "role": "assistant",
        "content": [{"text": "hi"}],
        "tokenUsage": {
            "inputTokens": 10,
            "outputTokens": 5,
            "totalTokens": 15,
            "tokenLimit": 100,
        },
    }


def test_message_prints_token_percent_in_heading_and_breakdown_below():
    p = Printer()
    message = Message(
        role="assistant",
        content=[TextContent(text="hi")],
        tokenUsage=TokenUsage(inputTokens=10, outputTokens=5, totalTokens=15, tokenLimit=100),
    )

    message.print(info=p.dummy_printer, debug=p.dummy_printer)

    assert "## Assistant (15% used)" in p.lines
    assert "_Token usage: input=10, output=5, total=15, limit=100_" in p.lines


def test_message_prints_token_percent_up_to_two_decimal_places():
    p = Printer()
    message = Message(
        role="assistant",
        content=[TextContent(text="hi")],
        tokenUsage=TokenUsage(inputTokens=1, outputTokens=1, totalTokens=1, tokenLimit=300),
    )

    message.print(info=p.dummy_printer, debug=p.dummy_printer)

    assert "## Assistant (0.33% used)" in p.lines


def test_message_print_headings_for_roles_and_types():
    p = Printer()

    # Normal user message
    msg_user = Message(role="user", content=[TextContent(text="hi")])
    msg_user.print(info=p.dummy_printer, debug=p.dummy_printer)

    # Assistant tool call
    msg_tool_call = Message(role="assistant", type=MessageType.TOOL_CALL, content=[TextContent(text="call")])
    msg_tool_call.print(info=p.dummy_printer, debug=p.dummy_printer)

    # Tool result
    msg_tool_result = Message(role="tool", type=MessageType.TOOL_RESULT, content=[TextContent(text="result")])
    msg_tool_result.print(info=p.dummy_printer, debug=p.dummy_printer)

    headings = [l for l in p.lines if l.startswith("## ")]

    assert "## User" in headings
    assert "## Assistant (tool call)" in headings
    assert "## Tool result" in headings
