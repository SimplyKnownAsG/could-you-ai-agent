import json
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

from could_you.__main__ import MARKER, _get_editor_input, create_parser


def test_dialogue_cli_flags_default_to_none(monkeypatch):
    parser = create_parser()
    monkeypatch.setattr(sys, "argv", ["could-you"])

    args = parser.parse_args()

    assert args.dialogue_load is None
    assert args.dialogue_store is None


def test_dialogue_cli_flags_support_short_positive_shorthands(monkeypatch):
    parser = create_parser()
    monkeypatch.setattr(sys, "argv", ["could-you", "-L", "-S"])

    args = parser.parse_args()

    assert args.dialogue_load is False
    assert args.dialogue_store is False


def test_dialogue_cli_flags_support_long_positive_overrides(monkeypatch):
    parser = create_parser()
    monkeypatch.setattr(sys, "argv", ["could-you", "--dialogue-load", "--dialogue-store"])

    args = parser.parse_args()

    assert args.dialogue_load is True
    assert args.dialogue_store is True


def test_dialogue_cli_flags_support_long_negative_overrides(monkeypatch):
    parser = create_parser()
    monkeypatch.setattr(sys, "argv", ["could-you", "--no-dialogue-load", "--no-dialogue-store"])

    args = parser.parse_args()

    assert args.dialogue_load is False
    assert args.dialogue_store is False


def test_query_flag_populates_query(monkeypatch):
    parser = create_parser()
    monkeypatch.setattr(sys, "argv", ["could-you", "--query", "hello"])

    args = parser.parse_args()

    assert args.query == "hello"


def test_config_dump_defaults_to_json(monkeypatch):
    parser = create_parser()
    monkeypatch.setattr(sys, "argv", ["could-you", "config", "dump"])

    args = parser.parse_args()

    assert args.command == "config"
    assert args.config_command == "dump"
    assert args.config_format == "json"


def test_config_dump_accepts_yaml_alias(monkeypatch):
    parser = create_parser()
    monkeypatch.setattr(sys, "argv", ["could-you", "c", "dump", "--yaml"])

    args = parser.parse_args()

    assert args.command == "config"
    assert args.config_command == "dump"
    assert args.config_format == "yaml"


def test_config_dump_rejects_multiple_output_formats(monkeypatch):
    parser = create_parser()
    monkeypatch.setattr(sys, "argv", ["could-you", "config", "dump", "--json", "--yaml"])

    with pytest.raises(SystemExit):
        parser.parse_args()


@pytest.mark.parametrize(
    ("argv", "command", "subcommand", "expected"),
    [
        (["could-you", "script", "git-commit"], "script", None, "git-commit"),
        (["could-you", "s", "git-commit"], "script", None, "git-commit"),
        (["could-you", "config", "dump"], "config", "dump", "json"),
        (["could-you", "config", "dump", "--yaml"], "config", "dump", "yaml"),
        (["could-you", "c", "dump", "--json"], "config", "dump", "json"),
        (["could-you", "workspace", "init"], "workspace", "init", None),
        (["could-you", "workspace", "sync"], "workspace", "sync", None),
        (["could-you", "ws", "sync"], "workspace", "sync", None),
        (["could-you", "memory", "archive", "topic"], "memory", "archive", "topic"),
        (["could-you", "m", "archive", "topic"], "memory", "archive", "topic"),
        (["could-you", "memory", "inspect"], "memory", "inspect", None),
        (["could-you", "memory", "status"], "memory", "inspect", None),
        (["could-you", "memory", "search", "alpha", "beta"], "memory", "search", ["alpha", "beta"]),
        (["could-you", "dialogue", "print"], "dialogue", "print", None),
        (["could-you", "permissions"], "permissions", None, None),
        (["could-you", "test", "connect", "ping"], "test", "connect", "ping"),
        (["could-you", "--query", "hello"], None, None, None),
    ],
)
def test_subcommand_parsing(monkeypatch, argv, command, subcommand, expected):
    parser = create_parser()
    monkeypatch.setattr(sys, "argv", argv)

    args = parser.parse_args()

    assert args.command == command

    if argv[1:3] == ["--query", "hello"]:
        assert args.query == "hello"
        return

    if command == "script":
        assert args.script_name == expected
    elif command == "config":
        assert args.config_command == subcommand
        assert args.config_format == expected
    elif command == "workspace":
        assert args.workspace_command == subcommand
    elif command == "memory":
        assert args.memory_command == subcommand
        if subcommand == "archive":
            assert args.topic == expected
        elif subcommand == "search":
            assert args.terms == expected
    elif command == "dialogue":
        assert args.dialogue_command == subcommand
    elif command == "test":
        assert args.test_command == subcommand
        if subcommand == "connect":
            assert args.message == expected


def _write_dialogue(w_config_dir: Path, messages: list[dict]) -> None:
    dialogue_path = w_config_dir / "dialogue.jsonl"
    with dialogue_path.open("w") as f:
        for msg in messages:
            f.write(json.dumps(msg) + "\n")


def test_get_editor_input_with_dialogue_load_true_shows_prior_dialogue(tmp_workspace, monkeypatch):
    """When dialogue_load=True (default), prior conversation should appear in query.md."""
    _write_dialogue(
        tmp_workspace,
        [
            {"role": "user", "type": "normal", "content": [{"type": "text", "text": "hello from prior run"}]},
        ],
    )

    captured_content = []

    def fake_editor_call(cmd):
        query_md = Path(cmd[1])
        captured_content.append(query_md.read_text())

    with patch("subprocess.call", side_effect=fake_editor_call):
        _get_editor_input(tmp_workspace)

    assert len(captured_content) == 1
    assert "hello from prior run" in captured_content[0]


def test_get_editor_input_with_dialogue_load_false_omits_prior_dialogue(tmp_workspace, monkeypatch):
    """When dialogue_load=False (-S flag), prior conversation should NOT appear in query.md."""
    _write_dialogue(
        tmp_workspace,
        [
            {"role": "user", "type": "normal", "content": [{"type": "text", "text": "hello from prior run"}]},
        ],
    )

    captured_content = []

    def fake_editor_call(cmd):
        query_md = Path(cmd[1])
        captured_content.append(query_md.read_text())

    with patch("subprocess.call", side_effect=fake_editor_call):
        _get_editor_input(tmp_workspace, dialogue_load=False)

    assert len(captured_content) == 1
    assert "hello from prior run" not in captured_content[0], (
        "Prior dialogue should not be shown when dialogue_load=False (-S flag)"
    )
