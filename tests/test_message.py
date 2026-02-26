import textwrap

from could_you.message import _print_markdown


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
