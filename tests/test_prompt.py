import textwrap
from datetime import UTC, datetime
from pathlib import Path

from could_you import prompt
from could_you.prompt import _agent_name_sentence, _date_sentence, _default_agent_name

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


def test_date_sentence_format():
    # Wednesday 2026-09-04T11:49 — week starts Monday 2026-08-31
    now = datetime(2026, 9, 4, 11, 49, tzinfo=UTC)
    result = _date_sentence(now)
    assert result.startswith("The current time is 2026-09-04T11:49")
    assert "the week of Monday, August 31" in result
    assert result.endswith(".")


def test_date_sentence_monday_is_own_week():
    # Monday itself should be the week-of date
    now = datetime(2026, 8, 31, 9, 0, tzinfo=UTC)
    result = _date_sentence(now)
    assert "the week of Monday, August 31" in result


def test_date_sentence_sunday_uses_previous_monday():
    # Sunday 2026-09-06 — week started Monday 2026-08-31
    now = datetime(2026, 9, 6, 23, 59, tzinfo=UTC)
    result = _date_sentence(now)
    assert "the week of Monday, August 31" in result


def test_could_you_date_expands():
    result = prompt.enrich_raw_prompt("COULD_YOU_DATE")
    assert "The current time is" in result.text
    assert "the week of" in result.text
    assert "COULD_YOU_DATE" not in result.text


def test_could_you_date_not_match_with_whitespace():
    for p in [" COULD_YOU_DATE", "COULD_YOU_DATE "]:
        result = prompt.enrich_raw_prompt(p)
        assert result.text == p


def test_could_you_date_in_multiline():
    p = textwrap.dedent("""
    BEFORE
    COULD_YOU_DATE
    AFTER
    """)
    result = prompt.enrich_raw_prompt(p)
    assert "BEFORE" in result.text
    assert "The current time is" in result.text
    assert "COULD_YOU_DATE" not in result.text
    assert "AFTER" in result.text


def test_default_agent_name_uses_current_user(monkeypatch):
    monkeypatch.setattr("could_you.prompt.getpass.getuser", lambda: "alice")

    assert _default_agent_name() == "alice-borg"


def test_agent_name_sentence(monkeypatch):
    monkeypatch.setattr("could_you.prompt.getpass.getuser", lambda: "alice")

    assert _agent_name_sentence() == "Your name is alice-borg."


def test_could_you_agent_name_expands(monkeypatch):
    monkeypatch.setattr("could_you.prompt.getpass.getuser", lambda: "alice")

    result = prompt.enrich_raw_prompt("COULD_YOU_AGENT_NAME")

    assert result.text == "Your name is alice-borg."


def test_could_you_agent_name_not_match_with_whitespace(monkeypatch):
    monkeypatch.setattr("could_you.prompt.getpass.getuser", lambda: "alice")

    for p in [" COULD_YOU_AGENT_NAME", "COULD_YOU_AGENT_NAME "]:
        result = prompt.enrich_raw_prompt(p)
        assert result.text == p


def test_could_you_agent_name_in_multiline(monkeypatch):
    monkeypatch.setattr("could_you.prompt.getpass.getuser", lambda: "alice")

    p = textwrap.dedent("""
    BEFORE
    COULD_YOU_AGENT_NAME
    AFTER
    """)
    result = prompt.enrich_raw_prompt(p)

    assert "BEFORE" in result.text
    assert "Your name is alice-borg." in result.text
    assert "COULD_YOU_AGENT_NAME" not in result.text
    assert "AFTER" in result.text


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


# ---------------------------------------------------------------------------
# COULD_YOU_EXPAND_ENV
# ---------------------------------------------------------------------------


def test_could_you_expand_env_substitutes_value(monkeypatch):
    monkeypatch.setenv("COULD_YOU_INCIDENT_DIR", "/tmp/incidents/20260101T000000Z")

    result = prompt.enrich_raw_prompt("COULD_YOU_EXPAND_ENV(COULD_YOU_INCIDENT_DIR)")

    assert result.text == "/tmp/incidents/20260101T000000Z"


def test_could_you_expand_env_in_multiline(monkeypatch):
    monkeypatch.setenv("MY_VAR", "VALUE")

    p = textwrap.dedent("""
    BEFORE
    COULD_YOU_EXPAND_ENV(MY_VAR)
    AFTER
    """)
    result = prompt.enrich_raw_prompt(p)

    assert "BEFORE" in result.text
    assert "VALUE" in result.text
    assert "COULD_YOU_EXPAND_ENV" not in result.text
    assert "AFTER" in result.text


def test_could_you_expand_env_requires_own_line(monkeypatch):
    """Directive must occupy its own line, matching the other prompt directives."""
    monkeypatch.setenv("MY_VAR", "VALUE")

    for p in ["prefix COULD_YOU_EXPAND_ENV(MY_VAR)", "COULD_YOU_EXPAND_ENV(MY_VAR) suffix"]:
        result = prompt.enrich_raw_prompt(p)
        assert result.text == p


def test_could_you_expand_env_substitutes_marker_when_undefined(monkeypatch):
    """An unset variable yields a visible marker and a logged warning, not a raise.

    The marker makes the missing expansion visible both in logs and to the
    model that receives the prompt.
    """
    monkeypatch.delenv("DEFINITELY_NOT_SET_12345", raising=False)

    result = prompt.enrich_raw_prompt("COULD_YOU_EXPAND_ENV(DEFINITELY_NOT_SET_12345)")

    assert result.text == "<COULD_YOU_EXPAND_ENV: DEFINITELY_NOT_SET_12345 not set>"


def test_could_you_expand_env_substitutes_marker_when_empty(monkeypatch):
    """An empty-string variable is treated the same as unset."""
    monkeypatch.setenv("EMPTY_VAR", "")

    result = prompt.enrich_raw_prompt("COULD_YOU_EXPAND_ENV(EMPTY_VAR)")

    assert result.text == "<COULD_YOU_EXPAND_ENV: EMPTY_VAR not set>"


def test_could_you_expand_env_rejects_malformed_name(monkeypatch):
    """A directive argument that doesn't match the env-var-name shape is left
    as-is, like any non-matching text. We confirm the pattern is strict."""
    monkeypatch.setenv("GOOD_NAME", "ok")

    # Numeric prefix is not a valid env var name — directive should not match.
    p = "COULD_YOU_EXPAND_ENV(1BAD)"
    result = prompt.enrich_raw_prompt(p)
    assert result.text == p


def test_could_you_expand_env_multiple_in_prompt(monkeypatch):
    monkeypatch.setenv("A", "alpha")
    monkeypatch.setenv("B", "beta")

    p = textwrap.dedent("""
    COULD_YOU_EXPAND_ENV(A)
    COULD_YOU_EXPAND_ENV(B)
    """)
    result = prompt.enrich_raw_prompt(p)

    assert "alpha" in result.text
    assert "beta" in result.text
    assert "COULD_YOU_EXPAND_ENV" not in result.text
