import textwrap
from pathlib import Path

from could_you import prompt
from could_you.prompt import _default_agent_name

from .dir_changer import DirChanger


def test_enrich_raw_prompt_exact_match(tmp_dir: Path):
    # Setup files in a temporary directory
    (tmp_dir / "foo.md").write_text("FOO CONTENT")
    (tmp_dir / "bar.md").write_text("BAR CONTENT")
    # Single
    p = "COULD_YOU_LOAD_FILE(foo.md)"
    result = prompt.enrich_raw_prompt(p)
    assert "COULD_YOU_LOAD_FILE" not in result.text
    assert "FOO CONTENT" in result.text
    assert "BAR CONTENT" not in result.text
    assert str(tmp_dir / "foo.md") in result.text
    assert str(tmp_dir / "bar.md") not in result.text
    assert result.metadata.loaded_files == [
        prompt.LoadedFileMetadata(directive="foo.md", path=str((tmp_dir / "foo.md").absolute()), bytes=11)
    ]


def test_not_match(tmp_dir: Path):
    # Setup files in a temporary directory
    (tmp_dir / "foo.md").write_text("FOO CONTENT")
    prompts = [" COULD_YOU_LOAD_FILE(foo.md)", "COULD_YOU_LOAD_FILE(foo.md) "]
    for p in prompts:
        # Single
        result = prompt.enrich_raw_prompt(p)
        assert result.text == p
        assert result.metadata.loaded_files == []


def test_multi_line(tmp_dir: Path):
    # Setup files in a temporary directory
    (tmp_dir / "foo.md").write_text("FOO CONTENT")
    p = textwrap.dedent("""
    BEFORE
    COULD_YOU_LOAD_FILE(foo.md)
    AFTER
    """)
    result = prompt.enrich_raw_prompt(p)
    assert "BEFORE" in result.text
    assert str(tmp_dir / "foo.md") in result.text
    assert "COULD_YOU_LOAD_FILE" not in result.text
    assert "FOO CONTENT" in result.text
    assert "AFTER" in result.text
    assert result.metadata.loaded_file_count == 1
    assert result.metadata.total_loaded_bytes == 11


def test_parentheses(tmp_dir: Path):
    # Setup files in a temporary directory
    (tmp_dir / "f()().md").write_text("F()() CONTENT")
    p = "COULD_YOU_LOAD_FILE(f()().md)"
    result = prompt.enrich_raw_prompt(p)
    assert str(tmp_dir / "f()().md") in result.text
    assert "COULD_YOU_LOAD_FILE" not in result.text
    assert "F()() CONTENT" in result.text
    assert result.metadata.loaded_files == [
        prompt.LoadedFileMetadata(directive="f()().md", path=str((tmp_dir / "f()().md").absolute()), bytes=13)
    ]


def test_enrich_raw_prompt_wildcard(tmp_dir: Path):
    # Setup files in a temporary directory
    (tmp_dir / "foo.md").write_text("FOO CONTENT")
    (tmp_dir / "bar.md").write_text("BAR CONTENT")
    # Single
    p = "COULD_YOU_LOAD_FILE(*.md)"
    result = prompt.enrich_raw_prompt(p)
    assert "COULD_YOU_LOAD_FILE" not in result.text
    assert "FOO CONTENT" in result.text
    assert "BAR CONTENT" in result.text
    assert str(tmp_dir / "foo.md") in result.text
    assert str(tmp_dir / "bar.md") in result.text
    assert result.metadata.loaded_file_count == 2
    assert result.metadata.total_loaded_bytes == 22


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
        assert "FORBIDDEN" not in result.text
        assert "ALLOWED" in result.text
        assert result.metadata.loaded_files == [
            prompt.LoadedFileMetadata(directive="*.md", path=str(allowed_path.absolute()), bytes=7)
        ]

        # test 2
        result = prompt.enrich_raw_prompt("COULD_YOU_LOAD_FILE(../*.md)")
        assert result.text == ""
        assert result.metadata.loaded_files == []

        # test 3
        result = prompt.enrich_raw_prompt("COULD_YOU_LOAD_FILE(../**/*.md)")
        assert "FORBIDDEN" not in result.text
        assert "ALLOWED" in result.text
        assert result.metadata.loaded_files == [
            prompt.LoadedFileMetadata(directive="../**/*.md", path=str(allowed_path.absolute()), bytes=7)
        ]


def test_enrich_raw_prompt_uses_workspace_root_not_cwd(tmp_path: Path):
    """Globs must resolve relative to workspace_root even when cwd is a sub-directory."""
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    w_config_dir = workspace / ".could-you"
    w_config_dir.mkdir()
    memory_path = w_config_dir / "MEMORY.md"
    memory_path.write_text("MEMORY CONTENT")

    sub_dir = workspace / "some-folder"
    sub_dir.mkdir()

    # Simulate being invoked from within a sub-directory of the workspace.
    with DirChanger(sub_dir):
        result = prompt.enrich_raw_prompt(
            "COULD_YOU_LOAD_FILE(.could-you/MEMORY.md)",
            workspace_root=workspace,
        )

    assert "MEMORY CONTENT" in result.text
    assert str(memory_path) in result.text
    assert result.metadata.loaded_file_count == 1


def test_default_agent_name_uses_current_user(monkeypatch):
    monkeypatch.setattr("could_you.prompt.getpass.getuser", lambda: "alice")

    assert _default_agent_name() == "alice-borg"


def test_default_agent_name_falls_back_to_user_borg(monkeypatch):
    def raise_os_error():
        raise OSError("no user")

    monkeypatch.setattr("could_you.prompt.getpass.getuser", raise_os_error)

    assert _default_agent_name() == "usr-borg"


def test_default_prompt_loads_workspace_memory_and_root_markdown(tmp_dir: Path, monkeypatch):
    monkeypatch.setattr("could_you.prompt.getpass.getuser", lambda: "alice")
    (tmp_dir / "README.md").write_text("README CONTENT")
    w_config_dir = tmp_dir / ".could-you"
    w_config_dir.mkdir()
    memory_path = w_config_dir / "MEMORY.md"
    memory_path.write_text("MEMORY CONTENT")

    result = prompt.enrich_raw_prompt("COULD_YOU_DEFAULT_PROMPT")

    assert "Your name is alice-borg." in result.text
    assert "MEMORY CONTENT" in result.text
    assert str(memory_path) in result.text
    assert "README CONTENT" in result.text
    assert result.metadata.loaded_file_count == 2
    assert result.metadata.total_loaded_bytes == 28


def test_enrich_raw_prompt_no_directories(tmp_dir: Path):
    (tmp_dir / "foo.md").write_text("FOO CONTENT")
    bar_dir = tmp_dir / "bar.md"
    bar_dir.mkdir()
    (bar_dir / "foo2.md").write_text("FOO2 CONTENT")
    # Single
    p = "COULD_YOU_LOAD_FILE(*.md)"
    result = prompt.enrich_raw_prompt(p)
    assert "COULD_YOU_LOAD_FILE" not in result.text
    assert "FOO CONTENT" in result.text
    assert "FOO2 CONTENT" not in result.text
    assert str(tmp_dir / "foo.md") in result.text
    assert result.metadata.loaded_files == [
        prompt.LoadedFileMetadata(directive="*.md", path=str((tmp_dir / "foo.md").absolute()), bytes=11)
    ]
