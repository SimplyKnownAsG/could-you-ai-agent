import textwrap
from pathlib import Path

from could_you import prompt

from .dir_changer import DirChanger


def test_enrich_raw_prompt_exact_match(tmp_dir: Path):
    # Setup files in a temporary directory
    (tmp_dir / "foo.md").write_text("FOO CONTENT")
    (tmp_dir / "bar.md").write_text("BAR CONTENT")
    # Single
    p = "COULD_YOU_LOAD_FILE(foo.md)"
    result = prompt.enrich_raw_prompt(p)
    assert "COULD_YOU_LOAD_FILE" not in result
    assert "FOO CONTENT" in result
    assert "BAR CONTENT" not in result
    assert str(tmp_dir / "foo.md") in result
    assert str(tmp_dir / "bar.md") not in result


def test_not_match(tmp_dir: Path):
    # Setup files in a temporary directory
    (tmp_dir / "foo.md").write_text("FOO CONTENT")
    prompts = [" COULD_YOU_LOAD_FILE(foo.md)", "COULD_YOU_LOAD_FILE(foo.md) "]
    for p in prompts:
        # Single
        result = prompt.enrich_raw_prompt(p)
        assert result == p


def test_multi_line(tmp_dir: Path):
    # Setup files in a temporary directory
    (tmp_dir / "foo.md").write_text("FOO CONTENT")
    p = textwrap.dedent("""
    BEFORE
    COULD_YOU_LOAD_FILE(foo.md)
    AFTER
    """)
    result = prompt.enrich_raw_prompt(p)
    assert "BEFORE" in result
    assert str(tmp_dir / "foo.md") in result
    assert "COULD_YOU_LOAD_FILE" not in result
    assert "FOO CONTENT" in result
    assert "AFTER" in result


def test_parentheses(tmp_dir: Path):
    # Setup files in a temporary directory
    (tmp_dir / "f()().md").write_text("F()() CONTENT")
    p = "COULD_YOU_LOAD_FILE(f()().md)"
    result = prompt.enrich_raw_prompt(p)
    assert str(tmp_dir / "f()().md") in result
    assert "COULD_YOU_LOAD_FILE" not in result
    assert "F()() CONTENT" in result


def test_enrich_raw_prompt_wildcard(tmp_dir: Path):
    # Setup files in a temporary directory
    (tmp_dir / "foo.md").write_text("FOO CONTENT")
    (tmp_dir / "bar.md").write_text("BAR CONTENT")
    # Single
    p = "COULD_YOU_LOAD_FILE(*.md)"
    result = prompt.enrich_raw_prompt(p)
    assert "COULD_YOU_LOAD_FILE" not in result
    assert "FOO CONTENT" in result
    assert "BAR CONTENT" in result
    assert str(tmp_dir / "foo.md") in result
    assert str(tmp_dir / "bar.md") in result


def test_enrich_raw_prompt_excludes_outside_paths(tmp_dir: Path):
    (tmp_dir / "forbiden.md").write_text("FORBIDDEN")
    allowed_base = tmp_dir / "allowed"
    allowed_base.mkdir()
    allowed_path = allowed_base / "allowed.md"
    allowed_path.write_text("ALLOWED")
    with DirChanger(allowed_base):
        # Try to glob only at allowed_base, should not pick up from subdir
        result = prompt.enrich_raw_prompt("COULD_YOU_LOAD_FILE(*.md)")
        # Should not include forbidden file (in subdir), only include file at root
        assert "FORBIDDEN" not in result
        assert "ALLOWED" in result

        # test 2
        result = prompt.enrich_raw_prompt("COULD_YOU_LOAD_FILE(../*.md)")
        assert result == ""

        # test 3
        result = prompt.enrich_raw_prompt("COULD_YOU_LOAD_FILE(../**/*.md)")
        assert "FORBIDDEN" not in result
        assert "ALLOWED" in result


def test_enrich_raw_prompt_no_directories(tmp_dir: Path):
    (tmp_dir / "foo.md").write_text("FOO CONTENT")
    bar_dir = tmp_dir / "bar.md"
    bar_dir.mkdir()
    (bar_dir / "foo2.md").write_text("FOO2 CONTENT")
    # Single
    p = "COULD_YOU_LOAD_FILE(*.md)"
    result = prompt.enrich_raw_prompt(p)
    assert "COULD_YOU_LOAD_FILE" not in result
    assert "FOO CONTENT" in result
    assert "FOO2 CONTENT" not in result
    assert str(tmp_dir / "foo.md") in result
