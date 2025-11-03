import os
from pathlib import Path

from could_you import prompt


class DirChanger:
    def __init__(self, path: Path):
        self.new_path = path
        self.original = None

    def __enter__(self):
        self.original = Path.cwd()
        os.chdir(self.new_path)
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        if self.original:
            os.chdir(self.original)


def test_enrich_raw_prompt_exact_match(tmp_path):
    # Setup files in a temporary directory
    allowed_base = tmp_path
    (allowed_base / "foo.md").write_text("FOO CONTENT")
    (allowed_base / "bar.md").write_text("BAR CONTENT")
    with DirChanger(allowed_base):
        # Single
        p = "COULD_YOU_LOAD_FILE(foo.md)"
        result = prompt.enrich_raw_prompt(p)
        assert "COULD_YOU_LOAD_FILE" not in result
        assert "FOO CONTENT" in result
        assert "BAR CONTENT" not in result
        assert str(allowed_base / "foo.md") in result
        assert str(allowed_base / "bar.md") not in result


def test_not_match(tmp_path):
    # Setup files in a temporary directory
    allowed_base = tmp_path
    (allowed_base / "foo.md").write_text("FOO CONTENT")
    prompts = [" COULD_YOU_LOAD_FILE(foo.md)", "COULD_YOU_LOAD_FILE(foo.md) "]
    with DirChanger(allowed_base):
        for p in prompts:
            # Single
            result = prompt.enrich_raw_prompt(p)
            assert result == p


def test_enrich_raw_prompt_wildcard(tmp_path):
    # Setup files in a temporary directory
    allowed_base = tmp_path
    (allowed_base / "foo.md").write_text("FOO CONTENT")
    (allowed_base / "bar.md").write_text("BAR CONTENT")
    with DirChanger(allowed_base):
        # Single
        p = "COULD_YOU_LOAD_FILE(*.md)"
        result = prompt.enrich_raw_prompt(p)
        assert "COULD_YOU_LOAD_FILE" not in result
        assert "FOO CONTENT" in result
        assert "BAR CONTENT" in result
        assert str(allowed_base / "foo.md") in result
        assert str(allowed_base / "bar.md") in result


def test_enrich_raw_prompt_excludes_outside_paths(tmp_path):
    forbidden_dir = tmp_path
    (forbidden_dir / "forbiden.md").write_text("FORBIDDEN")
    allowed_base = forbidden_dir / "allowed"
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


def test_enrich_raw_prompt_no_directories(tmp_path):
    allowed_base = tmp_path
    (allowed_base / "foo.md").write_text("FOO CONTENT")
    bar_dir = allowed_base / "bar.md"
    bar_dir.mkdir()
    (bar_dir / "foo2.md").write_text("FOO2 CONTENT")
    with DirChanger(allowed_base):
        # Single
        p = "COULD_YOU_LOAD_FILE(*.md)"
        result = prompt.enrich_raw_prompt(p)
        assert "COULD_YOU_LOAD_FILE" not in result
        assert "FOO CONTENT" in result
        assert "FOO2 CONTENT" not in result
        assert str(allowed_base / "foo.md") in result
